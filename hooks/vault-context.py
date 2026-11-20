#!/usr/bin/env python3
"""SessionStart 훅 — 세션을 열거나 대화가 압축될 때 옵시디언 볼트 발췌를 Claude 맥락에 넣는다 (2026-11-20).

왜: 볼트는 결정 경위·남은 일·데일리를 쌓는 곳인데 Gate 절차에는 볼트를 읽는 단계가 없다. 한 제품 프로젝트는 CLAUDE.md 에
    규칙만 두었을 때 세션 다섯 개가 볼트를 한 번도 열지 않아(2026-11-10) 이 발췌 훅을 그 저장소에 만들었다. 그 훅을
    옮겨 경로·노트·절을 설정으로 바꿨다(HARNESS-VAULT-REF-2).

설정: 프로젝트 `.claude/harness-answers.yml` 의 `vault_ref:` 블록. 없거나 `enabled` 가 참이 아니면 아무것도 출력하지 않는다.
  vault_ref:
    enabled: true
    vault_paths:                      # 볼트 폴더 후보 — 처음 있는 폴더. 환경변수 VAULT_REF_PATH 가 먼저
      - "D:/vault"
    hub: "20 Notes/허브.md"           # 이 노트를 링크하는 노트(백링크) 목록을 낸다 — 볼트 기준 상대 경로, .md 까지
    sections:                         # "노트 경로 :: 머리" — 머리가 # 면 제목 절, > 면 인용 블록, 그 밖은 빈 줄 앞까지
      - "20 Notes/허브.md :: > 📍 **지금 상태"
    daily_dir: "10 Journal"           # 그 아래 <연도>/YYYY-MM-DD.md (기본값)
    daily_head: "### 소절"            # 최근 데일리의 소절 — 또는
    daily_tag: "#태그"                # 최근 데일리에서 이 태그가 든 줄 (# 로 시작하는 값은 따옴표로 감싼다)

출력(표준 출력이 그대로 맥락에 들어간다 — Claude Code 상한 10,000글자): 머리(볼트 경로·마지막 커밋 시각·읽는 규칙) → 지정 절
→ 데일리 → 백링크. 절마다 글자 한도를 두어 전체 8,000글자 아래. `90 Private` 아래는 열지도 목록에 넣지도 않는다.
볼트는 읽기만 하고, 무슨 일이 있어도 exit 0 — 세션을 막지 않는다. 출력은 Windows(cp949 기본)에서도 UTF-8 로 고정한다.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

MARK = "[볼트 발췌 — vault-context]"
CUT = "…(잘림 — 전문은 볼트 노트)"
LINE_MAX = 400
TOTAL_MAX = 8000
LIMIT_HEADER, LIMIT_SECTION, LIMIT_DAILY, LIMIT_LINKS = 600, 1600, 2400, 800
DAILY_LOOKBACK = 7
LINKS_MAX = 15
DAILY_DIR = "10 Journal"
PRIVATE = "90 Private"
#: 백링크 훑기에서 빼는 첫 폴더 — 원본 볼트 구조의 값에 개인 영역을 더했다(데일리 폴더는 설정값으로 따로 뺀다)
SKIP_TOP = {"50 Scrum", ".obsidian", ".trash", "_templates", ".git", PRIVATE}
DAILY_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
TRUE = {"true", "yes", "on", "1"}


def _scalar(value):
    """YAML 값 하나 — 따옴표 안은 그대로, 밖은 ` #` 뒤 주석을 뗀다. `#` 로 시작하는 맨 값은 주석(YAML 과 같다)."""
    v = value.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[1:end] if end > 0 else v[1:]
    if v.startswith("#"):
        return ""
    return re.split(r"\s+#", v, 1)[0].strip()


def load_config(project):
    """`vault_ref:` 블록 → dict. 블록이 없으면 None. 들여쓴 `키: 값`, `키:` 아래 `- 항목`, `[a, b]` 를 읽는다."""
    try:
        text = (Path(project) / ".claude" / "harness-answers.yml").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^vault_ref:[ \t]*(?:#[^\n]*)?\n((?:[ \t]+[^\n]*\n?|[ \t]*\n)*)", text, re.M)
    if not m:
        return None
    cfg, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and key:
            cfg.setdefault(key, [])
            if isinstance(cfg[key], list):
                cfg[key].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"^\s+([A-Za-z_]+):(.*)$", line)
        if not kv:
            continue
        key, raw = kv.group(1), kv.group(2).strip()
        if raw.startswith("["):
            cfg[key] = [_scalar(x) for x in raw.strip("[]").split(",") if x.strip()]
        elif raw and not raw.startswith("#"):
            cfg[key] = _scalar(raw)
        else:
            cfg[key] = []
    return cfg


def as_list(value):
    return [v for v in (value if isinstance(value, list) else [value]) if v]


def project_dir():
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.environ["CLAUDE_PROJECT_DIR"]
    if not sys.stdin.isatty():
        try:
            cwd = (json.loads(sys.stdin.read() or "{}") or {}).get("cwd")
            if cwd:
                return cwd
        except (ValueError, AttributeError):
            pass
    return os.getcwd()


def modified(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()


def clip(text: str, limit: int) -> str:
    """줄마다 LINE_MAX 글자, 절 전체 limit 글자. 넘으면 절 끝에 CUT 한 번."""
    lines = [l if len(l) <= LINE_MAX else l[:LINE_MAX - 1] + "…" for l in text.split("\n")]
    out, size = [], 0
    for l in lines:
        if size + len(l) + 1 > limit - len(CUT) - 1:
            out.append(CUT)
            return "\n".join(out)
        out.append(l)
        size += len(l) + 1
    return "\n".join(out)


def section(text: str, head: str):
    """head 로 시작하는 줄부터 — 제목(#)이면 같은 수준 이상의 다음 제목 앞까지, 인용(>)이면 이어지는 > 줄,
    그 밖은 빈 줄 앞까지. 없으면 None."""
    lines = text.split("\n")
    level = len(head) - len(head.lstrip("#"))
    for i, l in enumerate(lines):
        if not l.startswith(head):
            continue
        out = [l]
        for m in lines[i + 1:]:
            if level:
                mm = re.match(r"^(#{1,6}) ", m)
                if mm and len(mm.group(1)) <= level:
                    break
            elif head.startswith(">"):
                if not m.startswith(">"):
                    break
            elif not m.strip():
                break
            out.append(m)
        return "\n".join(out).rstrip()
    return None


def private(rel: str) -> bool:
    return rel.replace("\\", "/").split("/", 1)[0] == PRIVATE


def pick_vault(cfg):
    """(볼트 Path, 본 후보 목록). 환경변수 VAULT_REF_PATH 를 먼저, 그다음 설정 후보 — 처음 있는 폴더."""
    candidates = as_list(os.environ.get("VAULT_REF_PATH")) + as_list(cfg.get("vault_paths"))
    for c in candidates:
        p = Path(os.path.expanduser(c))
        if p.is_dir():
            return p, candidates
    return None, candidates


def last_commit(vault: Path, today: date) -> str:
    """머리에 붙일 볼트의 마지막 커밋 — 죽은 사본을 골랐으면 여기서 보인다."""
    if not (vault / ".git").exists():
        return "마지막 커밋 확인 불가(git 저장소 아님)"
    try:
        r = subprocess.run(["git", "-C", str(vault), "log", "-1", "--format=%ci"], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=3)
        stamp = r.stdout.strip()
        if r.returncode or not stamp:
            return "마지막 커밋 확인 불가(git 기록 없음)"
        return f"마지막 커밋 {stamp} ({(today - date.fromisoformat(stamp[:10])).days}일 전)"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "마지막 커밋 확인 불가"


def section_parts(vault: Path, cfg):
    parts = []
    for spec in as_list(cfg.get("sections")):
        rel, _, head = spec.partition(" :: ")
        rel, head = rel.strip(), head.strip()
        label = head.lstrip("#> ").replace("**", "").strip() or "(머리 없음)"
        if private(rel):
            parts.append(f"## 「{label}」 — {rel}\n(읽지 않음 — 개인 영역 {PRIVATE})")
            continue
        p = vault / rel
        if not p.is_file():
            parts.append(f"## 「{label}」 — {rel}\n(없음 — 노트 없음)")
            continue
        body = section(p.read_text(encoding="utf-8"), head) if head else None
        title = f"## 「{label}」 — {rel} (수정 {modified(p)})"
        parts.append(title + "\n" + (clip(body, LIMIT_SECTION) if body else "(없음 — 절 없음)"))
    return parts


def daily_part(vault: Path, cfg, today: date):
    head, tag = cfg.get("daily_head") or "", cfg.get("daily_tag") or ""
    if not head and not tag:
        return None
    folder_name = cfg.get("daily_dir") or DAILY_DIR
    want = f"「{head.lstrip('# ')}」 절" if head else f"태그 {tag} 줄"
    tag_re = re.compile(r"(?<!\S)" + re.escape(tag) + r"(?![\w-])") if tag else None
    files = []
    for year in (today.year, today.year - 1):
        folder = vault / folder_name / str(year)
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            m = DAILY_NAME.match(f.name)
            if not m:
                continue
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if d <= today:
                files.append((d, f))
    files.sort(reverse=True)
    for d, f in files[:DAILY_LOOKBACK]:
        text = f.read_text(encoding="utf-8")
        body = section(text, head) if head else "\n".join(l for l in text.split("\n") if tag_re.search(l)) or None
        if body:
            rel = f.relative_to(vault).as_posix()
            return f"## 최근 데일리 {want} — {rel} (수정 {modified(f)})\n" + clip(body, LIMIT_DAILY)
    return f"## 최근 데일리\n(없음 — 최근 {DAILY_LOOKBACK}개 데일리에 {want} 없음)"


def links_part(vault: Path, cfg):
    hub = cfg.get("hub") or ""
    if not hub:
        return None
    name = Path(hub).stem
    link = re.compile(r"\[\[" + re.escape(name) + r"(\||#|\]\])")
    skip = SKIP_TOP | {cfg.get("daily_dir") or DAILY_DIR}
    found = []
    for root, dirs, files in os.walk(vault):
        if Path(root) == vault:
            dirs[:] = [d for d in dirs if d not in skip]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            p = Path(root) / fname
            rel = p.relative_to(vault).as_posix()
            if rel == hub or private(rel):
                continue
            try:
                if link.search(p.read_text(encoding="utf-8", errors="ignore")):
                    found.append((p.stat().st_mtime, rel, p))
            except OSError:
                continue
    found.sort(reverse=True)
    head = f"## 허브 [[{name}]] 를 링크하는 노트 — {len(found)}개 중 최근 수정 {min(len(found), LINKS_MAX)}개"
    body = "\n".join(f"- {rel} (수정 {modified(p)})" for _, rel, p in found[:LINKS_MAX]) or "(없음)"
    return head + "\n" + clip(body, LIMIT_LINKS)


def build(cfg, today: date) -> str:
    vault, candidates = pick_vault(cfg)
    if vault is None:
        return f"{MARK} 볼트 발췌 없음 — 볼트 폴더 없음(후보 {candidates or '없음'}, 환경변수 VAULT_REF_PATH 로 덮어쓸 수 있다)"
    header = clip("\n".join([
        f"{MARK} 세션 시작 · 압축 때 하네스가 넣는 옵시디언 볼트 발췌 — 설정은 .claude/harness-answers.yml 의 vault_ref.",
        f"볼트: {vault.as_posix()} — {last_commit(vault, today)}. 업무 방향 · 판단 · 경위를 쌓는 곳이고, 코드 · 세션 상태의 정본은 저장소다.",
        "규칙: 계획 · 결정 · 경위 판단 전에 볼트에서 주제 키워드로 노트를 찾아 읽는다. 아래 발췌는 절 안의 「YYYY-MM-DD 기준」 "
        "날짜를 먼저 보고(파일 수정일은 같은 노트의 다른 곳을 고쳐도 바뀐다) 커밋 시각과 함께, 낡았거나 저장소 기록과 "
        "어긋나면 근거로 쓰지 않는다.",
    ]), LIMIT_HEADER)
    parts = [header, *section_parts(vault, cfg), daily_part(vault, cfg, today), links_part(vault, cfg)]
    out = "\n\n".join(p for p in parts if p)
    if len(out) > TOTAL_MAX:
        out = out[:TOTAL_MAX - len(CUT) - 1] + "\n" + CUT
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows 기본 cp949 에서 한글·「—」가 깨지지 않게
    try:
        cfg = load_config(project_dir())
    except Exception:
        return 0
    if not cfg or str(cfg.get("enabled", "")).strip().lower() not in TRUE:
        return 0                                    # 꺼진 프로젝트는 맥락에 아무것도 넣지 않는다
    try:
        print(build(cfg, date.today()))
    except Exception as e:                          # 세션을 막지 않는다
        print(f"{MARK} 볼트 발췌 실패 — {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
