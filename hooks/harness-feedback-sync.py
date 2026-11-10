#!/usr/bin/env python3
"""작업 PC 의 하네스 사용 기록 요약을 받는 서버로 보낸다 — 응답 종료 훅 + 설정·확인·수동 전송·받기 (2026-11-10).

왜: 실제 작업은 이 엔진을 고치는 곳과 다른 PC 에서 돈다. 하네스를 고칠 근거(DECISION_LOG 예측)는 그 PC 의 대화 기록에만
있고, 기록은 30일 뒤 지워진다. 보고서를 손으로 만들어 복사하는 단계가 빠지면 근거가 사라진다.

무엇을: `harness_report.py` 가 만드는 세션 행(최근 30일 전체 — 받는 쪽이 같은 세션을 한 번만 센다)과 보낸 이유·엔진 버전
        한 파일. 대화 원문과 코드는 보내지 않는다. 행에는 프로젝트 이름·PC 의 폴더 이름·알림 문구가 들어 있다.
어디로: 설정 파일의 주소 하나(`[사용자@]호스트[:폴더]`, 폴더 기본 `harness-inbox`). 그 PC 의 SSH 설정과 키를 그대로 쓴다
        (`ssh`·`scp`, 암호를 묻지 않는 방식). 포트·키가 따로 필요하면 `~/.ssh/config` 의 Host 별칭을 주소로 쓴다.
        주소는 PC 의 사용자 폴더(`~/.claude/harness-feedback/`)에만 있고 저장소에는 없다.
언제: 응답이 끝날 때마다 훅으로 불리지만, 마지막 판정 뒤 6시간이 지났을 때만 판정한다(나머지는 시각 파일 하나만 보고 끝).
      마지막으로 보낸 뒤 ① 하네스 내부 오류(엔진 훅의 실행 오류·새 문맥 검토 스크립트 실패) 1건 이상 ② 바뀐 세션 10개 이상
      ③ 14일이 지났고 바뀐 세션 1개 이상 — 이면 보낸다. 판정과 전송은 떼어 낸 프로세스가 해서 응답을 기다리게 하지 않는다.
      실패하면 기록만 남기고 다음 판정 때 다시 보낸다. 설정이 없으면 아무것도 하지 않는다.

사용:
  python3 harness-feedback-sync.py setup <주소>       주소를 저장하고 접속·폴더 쓰기를 시험한다
  python3 harness-feedback-sync.py status             설정·마지막 판정과 전송·지금의 조건
  python3 harness-feedback-sync.py send [--dry-run]   조건과 상관없이 지금 보낸다
  python3 harness-feedback-sync.py receive [--inbox 폴더] [--out 폴더]   받는 서버에서 — 받은 파일로 보고서를 만든다
  (인자 없이)                                          응답 종료 훅
"""

import datetime
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

def collect_rows(now=None):
    import harness_report as hr

    since = ((now or _now()) - datetime.timedelta(days=KEEP_DAYS)).date().isoformat()
    return hr.collect(PROJECTS_DIR, since=since)["sessions"]


def harness_errors(row):
    """세션 하나의 하네스 내부 오류 — 엔진 훅의 실행 오류와 새 문맥 검토 스크립트의 「실패」."""
    import harness_report as hr

    hook = sum(g.get("error", 0) for name, g in (row.get("guards") or {}).items() if name in hr.ENGINE_HOOKS)
    return hook + (row.get("fresh_review") or {}).get("failed", 0)


def due(rows, state, now):
    """→ (보낼 이유 또는 None, 바뀐 세션 수). 바뀐 세션 = 마지막으로 보낸 뒤 새로 생기거나 마지막 활동이 늘어난 세션."""
    sent = state.get("sent") or {}
    changed = [r for r in rows if (r.get("last") or "") > sent.get(r.get("session"), "")]
    errors = sum(harness_errors(r) for r in changed)
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


def send(rows, reason, address, dry_run=False, now=None):
    """세션 행을 한 파일로 보낸다 → (성공, 한 줄 설명). 성공하면 상태의 마지막 전송과 보낸 세션을 바꾼다."""
    now = now or _now()
    target = split_address(address)
    if not target:
        return False, f"주소 형식이 아니다: {address!r} — `[사용자@]호스트[:폴더]`"
    host, folder = target
    pc = re.sub(r"[^\w.-]", "_", socket.gethostname() or "pc")[:40]
    name = f"{pc}-{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    meta = {"_meta": {"pc": pc, "sent_at": _iso(now), "reason": reason, "engine_version": _engine_version(),
                      "sessions": len(rows), "keep_days": KEEP_DAYS}}
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
    state["last_sent"] = _iso(now)
    state["sent"] = {r.get("session"): r.get("last") or "" for r in rows if r.get("session")}
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
        last = _parse(state.get("last_check") or "")
        if last and (now - last).total_seconds() < CHECK_EVERY_H * 3600:
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
    reason, changed = due(collect_rows(now), state, now)
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
            print(f"{pc}: 마지막 전송 {m.get('sent_at')} · {m.get('reason')} · 엔진 {m.get('engine_version')}")
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
    if cmd == "receive":
        opts = dict(zip(rest[::2], rest[1::2]))
        return cmd_receive(opts.get("--inbox", INBOX_DIR), opts.get("--out", ""))
    print(__doc__.split("사용:")[1].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
