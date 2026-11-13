#!/usr/bin/env python3
"""작업 PC 의 하네스 사용 기록 요약을 받는 서버로 보낸다 — 응답 종료 훅 + 설정·확인·수동 전송·받기 (2026-11-10).

왜: 실제 작업은 이 엔진을 고치는 곳과 다른 PC 에서 돈다. 하네스를 고칠 근거(DECISION_LOG 예측)는 그 PC 의 대화 기록에만
있고, 기록은 30일 뒤 지워진다. 보고서를 손으로 만들어 복사하는 단계가 빠지면 근거가 사라진다.

무엇을: `harness_report.py` 가 만드는 세션 행(최근 30일 전체 — 받는 쪽이 같은 세션을 한 번만 센다)과 보낸 이유·엔진 버전
        한 파일. 대화 원문과 코드는 보내지 않는다. 행에는 프로젝트 이름·PC 의 폴더 이름·알림 문구가 들어 있다.
        엔진 버전마다 이 PC 에서 처음 본 시각과, 행마다 세션 시작 때의 엔진 버전도 붙인다(받는 쪽이 갱신 뒤 세션을 가른다).
        보내기 전에 다른 훅의 알림 문구와 folder 칸을 빼고, 엔진 알림의 경로·파일 이름을 지운다(`shareable`).
어디로: 설정 파일의 주소 하나(`[사용자@]호스트[:폴더]`, 폴더 기본 `harness-inbox`). 그 PC 의 SSH 설정과 키를 그대로 쓴다
        (`ssh`·`scp`, 암호를 묻지 않는 방식). 포트·키가 따로 필요하면 `~/.ssh/config` 의 Host 별칭을 주소로 쓴다.
        주소는 PC 의 사용자 폴더(`~/.claude/harness-feedback/`)에만 있고 저장소에는 없다.
빼는 것: 설정 파일의 `exclude` 패턴(`~/.claude/projects` 의 폴더 이름이나 프로젝트 이름, glob·대소문자 무시)에 맞는 세션은
        모으지 않는다 — 판정·전송·status 모두에서 빠진다. 훅은 걸린 프로젝트와 상관없이 그 PC 의 대화 기록 전체를 읽는다.
언제: 응답이 끝날 때마다 훅으로 불리지만, 마지막 판정 뒤 6시간이 지났을 때만 판정한다(나머지는 시각 파일 하나만 보고 끝).
      마지막으로 보낸 뒤 ① 새로 난 하네스 내부 오류(엔진 훅의 실행 오류·새 문맥 검토 스크립트 실패) 1건 이상 ② 바뀐 세션 10개 이상
      ③ 14일이 지났고 바뀐 세션 1개 이상 — 이면 보낸다. 판정과 전송은 떼어 낸 프로세스가 해서 응답을 기다리게 하지 않는다.
      실패하면 기록만 남기고 다음 판정 때 다시 보낸다. 설정이 없으면 아무것도 하지 않는다.

사용:
  python3 harness-feedback-sync.py setup <주소>       주소를 저장하고 접속·폴더 쓰기를 시험한다
  python3 harness-feedback-sync.py status             설정·마지막 판정과 전송·지금의 조건
  python3 harness-feedback-sync.py send [--dry-run]   조건과 상관없이 지금 보낸다
  python3 harness-feedback-sync.py exclude [패턴...] [--remove 패턴...]   보내지 않을 프로젝트 — 인자 없으면 목록
  python3 harness-feedback-sync.py receive [--inbox 폴더] [--out 폴더]   받는 서버에서 — 받은 파일로 보고서를 만든다
  (인자 없이)                                          응답 종료 훅
"""

import datetime
import fnmatch
import glob
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME_DIR = os.environ.get("HARNESS_FEEDBACK_HOME") or os.path.join(os.path.expanduser("~"), ".claude", "harness-feedback")
PROJECTS_DIR = os.environ.get("HARNESS_FEEDBACK_PROJECTS") or os.path.join(os.path.expanduser("~"), ".claude", "projects")
INBOX_DIR = os.path.join(os.path.expanduser("~"), "harness-inbox")
CHECK_EVERY_H = 6
SESSIONS_DUE, DAYS_DUE, KEEP_DAYS = 10, 14, 30
TIMEOUT_S = 120
ADDRESS = re.compile(r"^(?P<host>(?:[\w.-]+@)?[\w.-]+)(?::(?P<dir>[^\s'\"]*))?$")


# ── 상태 ──────────────────────────────────────────────────────────────

def _path(name):
    return os.path.join(HOME_DIR, name)


def _load(name):
    try:
        with open(_path(name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(name, data):
    os.makedirs(HOME_DIR, exist_ok=True)
    tmp = _path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(name))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _log(text):
    try:
        os.makedirs(HOME_DIR, exist_ok=True)
        with open(_path("send.log"), "a", encoding="utf-8") as f:
            f.write(f"{_iso(_now())} {text}\n")
    except OSError:
        pass


def split_address(address):
    """`[사용자@]호스트[:폴더]` → (호스트, 폴더). 형식이 아니면 None. `~/` 는 떼어 낸다 — 원격 홈 기준 상대 경로다."""
    m = ADDRESS.match((address or "").strip())
    if not m or "://" in address:                   # URL 형식(ssh://…)은 받지 않는다 — 포트는 ~/.ssh/config 의 별칭으로
        return None
    folder = (m.group("dir") or "harness-inbox").strip()
    folder = folder[2:] if folder.startswith("~/") else folder
    return m.group("host"), (folder.rstrip("/") or "harness-inbox")


# ── 판정 ──────────────────────────────────────────────────────────────

def excluded(row, patterns):
    """설정의 제외 패턴에 맞는 세션인가 — `~/.claude/projects` 의 폴더 이름이나 프로젝트 이름(작업 폴더 끝 이름)을 본다.
    윈도 폴더 이름은 대소문자가 섞여 오므로 무시한다."""
    names = [(row.get(k) or "").lower() for k in ("folder", "project")]
    return any(n and fnmatch.fnmatchcase(n, p.lower()) for p in patterns for n in names)


def collect_rows(now=None, with_excluded=False):
    """최근 30일 세션 행. 제외 패턴에 맞는 행은 여기서 뺀다 — 판정도 전송도 그 세션을 모른다(2026-11-13: 다른 일의 고객
    프로젝트 세션이 하네스를 쓰는 프로젝트의 훅을 타고 같이 나갔다). `with_excluded` → (남은 행, 뺀 행 수)."""
    import harness_report as hr

    since = ((now or _now()) - datetime.timedelta(days=KEEP_DAYS)).date().isoformat()
    rows = hr.collect(PROJECTS_DIR, since=since)["sessions"]
    patterns = _load("config.json").get("exclude") or []
    kept = [r for r in rows if not excluded(r, patterns)]
    return (kept, len(rows) - len(kept)) if with_excluded else kept


def harness_errors(row):
    """세션 하나의 하네스 내부 오류 — 엔진 훅의 실행 오류와 새 문맥 검토 스크립트의 「실패」."""
    import harness_report as hr

    hook = sum(g.get("error", 0) for name, g in (row.get("guards") or {}).items() if name in hr.ENGINE_HOOKS)
    return hook + (row.get("fresh_review") or {}).get("failed", 0)


def due(rows, state, now):
    """→ (보낼 이유 또는 None, 바뀐 세션 수). 바뀐 세션 = 마지막으로 보낸 뒤 새로 생기거나 마지막 활동이 늘어난 세션.
    오류는 마지막 전송 뒤 새로 난 것만 센다 — 세션 누적으로 세면 오류가 한 번 난 세션을 이어 쓰는 동안 6시간마다
    같은 오류로 다시 보냈다(2026-11-10)."""
    sent, sent_errors = state.get("sent") or {}, state.get("sent_errors") or {}
    changed = [r for r in rows if (r.get("last") or "") > sent.get(r.get("session"), "")]
    errors = sum(max(0, harness_errors(r) - sent_errors.get(r.get("session"), 0)) for r in changed)
    if errors:
        return f"내부 오류 {errors}건", len(changed)
    if len(changed) >= SESSIONS_DUE:
        return f"바뀐 세션 {len(changed)}개", len(changed)
    base = _parse(state.get("last_sent") or state.get("set_up") or "")
    if base and changed and (now - base).days >= DAYS_DUE:
        return f"마지막 전송 뒤 {(now - base).days}일", len(changed)
    return None, len(changed)


# ── 전송 ──────────────────────────────────────────────────────────────

def _ssh_opts():
    return ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def _run(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S,
                           stdin=subprocess.DEVNULL, cwd=cwd)
        return p.returncode == 0, (p.stderr or p.stdout or "").strip()[:300]
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"


def _engine_version():
    for d in (os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), ".claude-plugin"), HERE):
        try:
            with open(os.path.join(d, "plugin.json"), encoding="utf-8") as f:
                return json.load(f).get("version") or "?"
        except (OSError, ValueError):
            continue
    return "?"


def note_version(state, now):
    """이 PC 에서 엔진 버전을 처음 본 시각을 적는다 → 새로 적었으면 True. 받는 쪽이 「갱신 뒤 세션」을 가르는 근거다 —
    결정일로 가르면 갱신 전 세션이 섞였다(2026-11-10). 처음 본 시각은 갱신 뒤 첫 응답 종료라 실제 갱신보다 조금 늦다."""
    version = _engine_version()
    seen = state.setdefault("versions_seen", {})
    if version == "?" or version in seen:
        return False
    seen[version] = _iso(now)
    return True


def engine_at(first, seen):
    """세션이 시작할 때 이미 깔려 있던 엔진 버전 — 시작보다 먼저 처음 본 버전 중 가장 늦은 것. 모르면 None."""
    best = None
    for version, t in (seen or {}).items():
        if (t or "")[:19] <= (first or "")[:19] and (best is None or t > seen[best]):
            best = version
    return best


#: 보내기 전에 지우는 것 — 받은 행의 알림 문구에 고객 문서 이름이, folder 칸에 PC 사용자·고객 폴더 이름이 실려 왔다(2026-11-10).
#: 이 PC 의 로컬 보고서는 그대로 두고 받는 서버로 가는 행에서만 지운다. 하네스 문서 이름은 판단에 쓰여 남긴다.
PATH_TOKEN = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s\\/,;()\[\]「」『』\"'`]+){2,}[\\/]?")
FILE_TOKEN = re.compile(r"[^\s\\/,;:()\[\]{}<>「」『』\"'`]+\.(?:md|markdown|txt|docx?|xlsx?|pptx?|pdf|hwpx?|csv|json|ya?ml|"
                        r"py|ts|tsx|js|jsx|kt|java|sql|html?|png|jpe?g)\b", re.I)
KEPT_NAMES = {"CURRENT_SESSION.md", "SESSION_INDEX.md", "00_MASTER_PLAN.md", "CLAUDE.md", "WORKLOG.md", "DECISION_LOG.md",
              "session-dashboard.html", "harness-answers.yml"}


def redact(text):
    """경로는 `<경로>`, 하네스가 아는 이름이 아닌 파일 이름은 `<파일>` 로."""
    import harness_report as hr

    text = PATH_TOKEN.sub("<경로>", text or "")
    return FILE_TOKEN.sub(lambda m: m.group(0) if m.group(0) in KEPT_NAMES | hr.ENGINE_HOOKS else "<파일>", text)


def shareable(row):
    """받는 서버로 보낼 행 — 다른 훅의 알림 문구는 빼고(훅 이름과 횟수는 남긴다), 엔진 훅 알림과 새 문맥 검토 첫 줄의
    경로·파일 이름을 지우고, folder 칸(PC 의 전체 경로를 이름으로 바꾼 것)을 비운다. 프로젝트 이름은 남긴다."""
    import harness_report as hr

    out = {**row, "folder": ""}
    notice = dict(row.get("max_repeat_notice") or {})
    if notice.get("text"):
        engine = notice.get("owner") in hr.ENGINE_HOOKS
        notice["text"] = redact(notice["text"]) if engine else ""
        out["max_repeat_notice"] = notice
    fresh = row.get("fresh_review")
    if fresh and fresh.get("unknown_heads"):
        out["fresh_review"] = {**fresh, "unknown_heads": [redact(h) for h in fresh["unknown_heads"]]}
    return out


def segment_rows(rows, seen):
    """갱신 전에 열어 갱신 뒤에도 이어 쓴 대화의 「갱신 뒤 부분」 행 — 받는 쪽 예측표가 이것으로 센다(2026-11-12). 실패해도
    전송은 계속한다(부분 행만 빠진다)."""
    import harness_report as hr

    out = []
    for r in rows:
        if not (r.get("folder") and r.get("session")):
            continue
        try:
            for seg in hr.version_segments(os.path.join(PROJECTS_DIR, r["folder"], r["session"] + ".jsonl"), r, seen):
                out.append({**shareable(seg), "engine_at_start": seg["segment"]})
        except Exception as e:  # 낯선 기록 하나가 전송 전체를 멈추면 안 된다
            _log(f"부분 행 실패 {r.get('session')}: {type(e).__name__}")
    return out


def send(rows, reason, address, dry_run=False, now=None):
    """세션 행을 한 파일로 보낸다 → (성공, 한 줄 설명). 성공하면 상태의 마지막 전송과 보낸 세션을 바꾼다."""
    now = now or _now()
    target = split_address(address)
    if not target:
        return False, f"주소 형식이 아니다: {address!r} — `[사용자@]호스트[:폴더]`"
    host, folder = target
    pc = re.sub(r"[^\w.-]", "_", socket.gethostname() or "pc")[:40]
    name = f"{pc}-{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    probe = _load("state.json")
    note_version(probe, now)                        # 훅이 아직 한 번도 안 돈 수동 전송에서도 지금 버전이 들어간다
    seen = probe["versions_seen"]
    rows = [{**shareable(r), "engine_at_start": engine_at(r.get("first"), seen)} for r in rows] + segment_rows(rows, seen)
    meta = {"_meta": {"pc": pc, "sent_at": _iso(now), "reason": reason, "engine_version": _engine_version(),
                      "versions_seen": seen, "sessions": len(rows), "keep_days": KEEP_DAYS}}
    summary = f"{reason} · 세션 {len(rows)}개 → {host}:{folder}/{name}"
    if dry_run:
        return True, "보낼 예정(--dry-run): " + summary
    ssh, scp = shutil.which("ssh"), shutil.which("scp")
    if not (ssh and scp):
        return False, "ssh·scp 를 찾지 못했다 — 이 PC 에 OpenSSH 클라이언트가 있어야 한다"
    tmp = tempfile.mkdtemp(prefix="harness-feedback-")
    try:
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        ok, err = _run([ssh, *_ssh_opts(), host, f"mkdir -p {shlex.quote(folder)}"])
        if ok:
            # 파일 이름만 넘긴다 — 윈도의 `C:\…` 경로는 scp 가 `C` 라는 호스트로 읽을 수 있다
            ok, err = _run([scp, *_ssh_opts(), "-q", name, f"{host}:{folder}/"], cwd=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not ok:
        return False, f"실패 — {summary} — {err}"
    state = _load("state.json")
    note_version(state, now)
    state["last_sent"] = _iso(now)
    state["sent"] = {r.get("session"): r.get("last") or "" for r in rows if r.get("session")}
    errors = {r.get("session"): harness_errors(r) for r in rows if r.get("session")}
    state["sent_errors"] = {s: n for s, n in errors.items() if n}
    _save("state.json", state)
    return True, "보냄 — " + summary


# ── 훅과 뒤쪽 판정 ─────────────────────────────────────────────────────

def _spawn_check():
    args = [sys.executable, os.path.abspath(__file__), "_check"]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)


def hook():
    """응답 종료 훅. 설정이 없거나 6시간이 안 지났으면 바로 끝난다. 무엇이든 실패해도 exit 0, 출력 없음."""
    try:
        if not _load("config.json").get("address"):
            return 0
        state, now = _load("state.json"), _now()
        noted = note_version(state, now)            # 판정은 6시간마다지만 갱신 시각은 그때그때 적는다
        last = _parse(state.get("last_check") or "")
        if last and (now - last).total_seconds() < CHECK_EVERY_H * 3600:
            if noted:
                _save("state.json", state)
            return 0
        state["last_check"] = _iso(now)            # 떼어 내기 전에 적는다 — 동시에 끝난 응답들이 여러 번 띄우지 않게
        _save("state.json", state)
        if os.environ.get("HARNESS_FEEDBACK_FOREGROUND"):      # 시험용 — 떼어 내지 않고 그 자리에서 판정한다
            return background_check()
        _spawn_check()
    except Exception as e:                          # 응답을 막지 않는다 — 기록만 남긴다
        _log(f"훅 오류 — {type(e).__name__}: {e}")
    return 0


def background_check():
    lock = _path("lock")
    try:
        os.makedirs(HOME_DIR, exist_ok=True)
        if os.path.exists(lock) and _now().timestamp() - os.path.getmtime(lock) > 3600:
            os.remove(lock)                         # 한 시간 넘은 잠금은 죽은 프로세스의 것이다
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except OSError:
        return 0
    try:
        address = _load("config.json").get("address")
        now = _now()
        rows = collect_rows(now)
        reason, changed = due(rows, _load("state.json"), now)
        if reason:
            ok, line = send(rows, reason, address, now=now)
            _log(line)
        else:
            _log(f"판정 — 보낼 조건 아님(바뀐 세션 {changed}개)")
    except Exception as e:
        _log(f"판정 오류 — {type(e).__name__}: {e}")
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    return 0


# ── 명령 ──────────────────────────────────────────────────────────────

def cmd_setup(address):
    target = split_address(address)
    if not target:
        print(f"주소 형식이 아니다: {address!r} — `[사용자@]호스트[:폴더]` (예: me@server:harness-inbox)")
        return 2
    host, folder = target
    config = _load("config.json")
    config["address"] = f"{host}:{folder}"
    _save("config.json", config)
    state = _load("state.json")
    state.setdefault("set_up", _iso(_now()))
    _save("state.json", state)
    ssh = shutil.which("ssh")
    if not ssh:
        print(f"저장함 — {host}:{folder}. 다만 ssh 를 찾지 못해 접속은 시험하지 못했다.")
        return 1
    ok, err = _run([ssh, *_ssh_opts(), host, f"mkdir -p {shlex.quote(folder)} && test -w {shlex.quote(folder)}"])
    print(f"저장함 — {host}:{folder}. 접속·폴더 쓰기 시험: " + ("통과" if ok else f"실패 — {err}"))
    return 0 if ok else 1


def cmd_status():
    config, state, now = _load("config.json"), _load("state.json"), _now()
    print(f"주소: {config.get('address') or '없음 — setup 이 필요하다'}")
    print(f"마지막 판정: {state.get('last_check') or '없음'} · 마지막 전송: {state.get('last_sent') or '없음'}")
    rows, dropped = collect_rows(now, with_excluded=True)
    patterns = config.get("exclude") or []
    print(f"보내지 않는 프로젝트: {', '.join(patterns) if patterns else '없음'}" + (f" (세션 {dropped}개 뺌)" if patterns else ""))
    reason, changed = due(rows, state, now)
    print(f"바뀐 세션 {changed}개 · 지금 보낼 조건: {reason or '아님'}")
    try:
        with open(_path("send.log"), encoding="utf-8") as f:
            tail = f.read().splitlines()[-3:]
        print("최근 기록:\n" + "\n".join("  " + t for t in tail))
    except OSError:
        pass
    return 0


def cmd_send(dry_run=False):
    address = _load("config.json").get("address")
    if not address:
        print("주소가 없다 — 먼저 setup <주소>")
        return 2
    ok, line = send(collect_rows(), "직접 실행", address, dry_run=dry_run)
    if not dry_run:
        _log(line)
    print(line)
    return 0 if ok else 1


def cmd_exclude(args):
    """보내지 않을 프로젝트 패턴을 더하거나(`exclude 패턴…`) 빼고(`--remove 패턴…`) 목록을 보인다. 주소가 없어도 저장한다 —
    전송을 켜기 전에 먼저 빼 둘 수 있어야 한다."""
    config = _load("config.json")
    patterns = list(config.get("exclude") or [])
    remove = "--remove" in args
    for p in (a.strip() for a in args if a != "--remove"):
        if not p:
            continue
        if remove and p in patterns:
            patterns.remove(p)
        elif not remove and p not in patterns:
            patterns.append(p)
    if args:
        config["exclude"] = patterns
        _save("config.json", config)
    rows, dropped = collect_rows(with_excluded=True)
    print(f"보내지 않는 프로젝트: {', '.join(patterns) if patterns else '없음'} · 최근 {KEEP_DAYS}일 세션 {dropped}개 뺌, "
          f"{len(rows)}개 보냄 대상")
    return 0


def cmd_receive(inbox=INBOX_DIR, out=""):
    """받는 서버에서: 받은 파일을 모아 harness_report 로 보고서를 만든다. 같은 세션은 마지막 활동이 늦은 행만 남는다."""
    import harness_report as hr

    files = sorted(glob.glob(os.path.join(inbox, "*.jsonl")))
    if not files:
        print(f"받은 파일이 없다: {inbox}")
        return 1
    tmp = tempfile.mkdtemp(prefix="harness-inbox-")
    try:
        cleaned, metas = [], {}
        for path in files:                         # 첫 줄의 보낸 정보는 세션 행이 아니다 — 떼어 내고 읽힌다
            with open(path, encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            rows = [ln for ln in lines if not ln.lstrip().startswith('{"_meta"')]
            for ln in lines:
                if ln.lstrip().startswith('{"_meta"'):
                    meta = json.loads(ln)["_meta"]
                    if meta.get("sent_at", "") >= metas.get(meta.get("pc"), {}).get("sent_at", ""):
                        metas[meta.get("pc")] = meta
            dst = os.path.join(tmp, os.path.basename(path))
            with open(dst, "w", encoding="utf-8") as f:
                f.writelines(rows)
            cleaned.append(dst)
        for pc, m in sorted(metas.items()):
            seen = ", ".join(f"{v} {t}" for v, t in sorted((m.get("versions_seen") or {}).items(), key=lambda x: x[1]))
            print(f"{pc}: 마지막 전송 {m.get('sent_at')} · {m.get('reason')} · 엔진 {m.get('engine_version')}"
                  + (f" · 처음 본 시각 {seen}" if seen else ""))
        args = [a for p in cleaned for a in ("--sessions", p)]
        return hr.main(args + (["--out", out] if out else []))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return hook()
    cmd, rest = argv[0], argv[1:]
    if cmd == "_check":
        return background_check()
    if cmd == "setup" and rest:
        return cmd_setup(rest[0])
    if cmd == "status":
        return cmd_status()
    if cmd == "send":
        return cmd_send(dry_run="--dry-run" in rest)
    if cmd == "exclude":
        return cmd_exclude(rest)
    if cmd == "receive":
        opts = dict(zip(rest[::2], rest[1::2]))
        return cmd_receive(opts.get("--inbox", INBOX_DIR), opts.get("--out", ""))
    print(__doc__.split("사용:")[1].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
