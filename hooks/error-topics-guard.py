#!/usr/bin/env python3
"""
error_topics 적재 강제 — Claude Code Stop Hook.

harness_runtime_charter §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

배경 (HARNESS-STALE-GUARD-2, 2026-05-22):
  error_topics 적재가 순수 markdown 가이드라인(error-log/gate-e SKILL Step 0)에
  의존 → 모델 자율 판단으로 일상적 누락. 확정 사례: FIX-B-SPOTLESS-3(2026-05-22
  CI 빌드 블로커)가 어느 error_topics/*.md 에도 미적재.
  본 훅이 응답 종료 시점에 "오류 흔적이 있는 ✅E 완료 세션인데 작업 코드 저장소
  error_topics 에 해당 세션 ID 가 미등장"인 drift 를 탐지해 차단한다.

프로토콜 (Claude Code Stop Hook):
  - 입력: stdin JSON — { session_id, ... }
  - 차단: stderr 메시지 + exit 2 (Claude 가 종료를 멈추고 계속 작업)
  - 허용: exit 0

차단 조건 (3중 AND):
  (1) CURRENT_SESSION.md 현재 상태가 ✅E (완료 세션만 검사 — 진행 중 오탐 방지)
  (2) 오류 흔적 존재:
        세션 ID 가 "FIX-B" prefix OR
        CURRENT_SESSION/SESSION_INDEX 본문에 "self-debug N회"(N≥1) OR
        "FIX-B N건"(N≥1)
  (3) 세션 ID 가 작업 코드 저장소 error_topics/*.md 어디에도 미등장

방어 원칙 (fail-open): 파일 부재·파싱 실패·예외·코드 저장소 부재는
  무조건 exit 0 (오탐 차단 금지).
무한 루프 방지: 세션별 연속 차단 횟수를 임시 파일에 기록, MAX 초과 시 exit 0.
"""

import glob
import json
import os
import re
import sys

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# 정본 절대경로 — R-4-2-b: 3단 우선순위 (① custom env[테스트] → ② CLAUDE_PROJECT_DIR 파생 → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
BASE_DIR = (
    os.environ.get("ERROR_TOPICS_GUARD_BASE")
    or (_proj if _proj else None)
    or os.environ.get("CLAUDE_PROJECT_DIR", ".")
)
# 코드 저장소 루트 — R-4-2-b: 3단 우선순위 (CLAUDE_PROJECT_DIR 부모 파생)
REPO_ROOT = (
    os.environ.get("ERROR_TOPICS_GUARD_REPO_ROOT")
    or (str(os.path.dirname(_proj)) if _proj else None)
    or os.environ.get("HARNESS_ROOT_DIR", ".")
)

CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")
SESSION_INDEX = os.path.join(BASE_DIR, "SESSION_INDEX.md")

# 연속 차단 한도 (무한 루프 방지)
MAX_BLOCKS = 3


def _find_answers_yml():
    """harness-answers.yml 경로 탐색 (BASE_DIR → CLAUDE_PROJECT_DIR → cwd)."""
    candidates = [
        os.path.join(BASE_DIR, ".claude", "harness-answers.yml"),
        os.path.join(os.getcwd(), ".claude", "harness-answers.yml"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_code_repos():
    """harness-answers.yml → code_repos 로드. 미설정/실패 시 빈 리스트(fail-open)."""
    # 테스트 우선 env 오버라이드 지원
    env_override = os.environ.get("ERROR_TOPICS_CODE_REPOS")
    if env_override:
        return [r.strip() for r in env_override.split(",") if r.strip()]

    path = _find_answers_yml()
    if not path:
        return []
    try:
        if _YAML_AVAILABLE:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = _simple_parse_code_repos(f.read())
        repos = data.get("code_repos") or []
        return [str(r) for r in repos if r]
    except Exception:
        return []


def _simple_parse_code_repos(text):
    """PyYAML 미설치 대비 간이 파서 — code_repos 리스트만 추출."""
    result = []
    in_section = False
    for line in text.splitlines():
        if re.match(r"^code_repos\s*:", line):
            in_section = True
            continue
        if in_section:
            if re.match(r"^\S", line) and not line.strip().startswith("-"):
                break
            m = re.match(r"^\s+-\s+[\"']?(.+?)[\"']?\s*$", line)
            if m:
                result.append(m.group(1).strip())
    return {"code_repos": result}


def allow():
    """응답 종료 허용 — exit 0."""
    sys.exit(0)


def block(reason):
    """응답 종료 차단 — stderr + exit 2."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def current_session_id_and_done(cur_text):
    """
    CURRENT_SESSION.md 에서 (세션 ID, ✅E 여부) 추출.
    gate-e-sync-guard.py 와 동일 패턴.
    형식: "> **세션 ID**: <ID>" + "> **현재 상태**: ✅E ..." 또는 대시보드 "현재 Gate".
    """
    m_id = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z][A-Za-z0-9\-]*)", cur_text)
    sid = m_id.group(1) if m_id else None
    # ✅E 여부: "현재 상태" 라인 또는 대시보드 "현재 Gate" 셀에 ✅E 등장
    done = bool(re.search(r"현재 상태\*\*:\s*✅\s*E", cur_text)) or bool(
        re.search(r"현재 Gate\s*\|\s*\*\*✅\s*E", cur_text)
    )
    return sid, done


def has_error_trace(session_id, *texts):
    """
    오류 흔적 판정:
      (a) 세션 ID 가 "FIX-B" 로 시작 OR
      (b) 본문에 "self-debug N회"(N≥1) OR "FIX-B N건"(N≥1)
    "self-debug 0" / "FIX-B/DEP 0" / "FIX-B 0건" 은 흔적 아님.
    """
    if session_id and session_id.upper().startswith("FIX-B"):
        return True
    blob = "\n".join(t for t in texts if t)
    # self-debug N회/N (N≥1)
    for m in re.finditer(r"self-debug\s*(\d+)", blob):
        if int(m.group(1)) >= 1:
            return True
    # FIX-B N건 (N≥1) — "FIX-B/DEP 0" 은 매칭 안 됨 (숫자 앞에 "건" 또는 공백+숫자)
    for m in re.finditer(r"FIX-B\s*(\d+)\s*건", blob):
        if int(m.group(1)) >= 1:
            return True
    return False


def strip_history(line):
    """priority_note/next_action 메가라인에서 현재 세션 세그먼트(head)만 반환.

    '이전:'·'직전:' 마커 이후는 과거 세션 이력 → 현재 세션 오류 흔적 판정에서 제외.
    HARNESS-ERRTOPICS-SCOPE-2: SCOPE-1의 라인 단위 스코핑이 다세션을 한 줄에 담은
    메가라인(priority_note/next_action)에서 무력화 → head 절단으로 현재 세션 부분만 본다.
    """
    m = re.search(r"이전:|직전:", line)
    return line[: m.start()] if m else line


def detect_code_repos(cur_text):
    """
    CURRENT_SESSION.md '| 저장소 | ... |' 행에서 코드 저장소 토큰 추출.
    harness-answers.yml → code_repos 설정 기준으로 필터링.
    설정 없거나 문서 전용(plans 등)만 있으면 빈 리스트 → 검사 제외(fail-open).
    """
    code_repos = _load_code_repos()
    if not code_repos:
        return []
    m = re.search(r"\|\s*저장소\s*\|\s*([^\|]+)\|", cur_text)
    if not m:
        return []
    repos_field = m.group(1)
    return [r for r in code_repos if r in repos_field]


def session_id_logged(session_id, repos):
    """
    세션 ID 가 주어진 코드 저장소들의 error_topics/*.md 어딘가에 등장하는지.
    하나라도 등장하면 True (적재됨).
    """
    for repo in repos:
        topics_dir = os.path.join(REPO_ROOT, repo, "docs", "rules", "error_topics")
        for path in glob.glob(os.path.join(topics_dir, "*.md")):
            text = read_text(path)
            if text and session_id in text:
                return True
    return False


def counter_path(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".error-topics-guard-{safe}.count")


def read_counter(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0


def write_counter(path, value):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(value))
    except Exception:
        pass


def clear_counter(path):
    try:
        os.remove(path)
    except OSError:
        pass


def main():
    # ── stdin payload (실패해도 진행 — exit 0 폴백) ──
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # ── 무한 루프 1차 방어: Stop 훅 재발동 중이면 즉시 통과 (공식 BP) ──
    # 이미 Stop 훅으로 인해 재발동된 호출이면 차단하지 않는다 (Issue #55754).
    # 런타임이 stop_hook_active 미제공 시 .get() falsy → 아래 카운터 2차 방어로 폴백.
    if payload.get("stop_hook_active"):
        allow()

    cpath = counter_path(payload.get("session_id", ""))

    # ── 문서 로드 (부재 시 검증 불가 → 허용) ──
    cur_text = read_text(CURRENT_SESSION)
    if cur_text is None:
        clear_counter(cpath)
        allow()
    idx_text = read_text(SESSION_INDEX) or ""

    # ── 세션 ID·완료 여부 (파싱 실패 시 허용) ──
    sid, done = current_session_id_and_done(cur_text)
    if not sid:
        clear_counter(cpath)
        allow()

    # ── (1) ✅E 완료 세션만 검사 ──
    if not done:
        clear_counter(cpath)
        allow()

    # ── (2) 오류 흔적 없으면 허용 ──
    # idx_text(SESSION_INDEX.md)는 전체 세션 이력을 담으므로, 현재 세션 ID 가
    # 포함된 라인으로 한정한다. 전역 스캔 시 직전 완료 세션들의 "self-debug N회"
    # 가 현재 세션 것으로 오인되어 오탐 차단된다 (HARNESS-ERRTOPICS-SCOPE-1).
    # 단, priority_note/next_action 은 현재 세션 + "이전:" 과거 이력을 한 줄에
    # 담은 메가라인이라 라인 한정이 무력화된다. strip_history 로 현재 세션 head
    # 만 남기고, head 에 sid 가 있는 라인만 채택한다 (HARNESS-ERRTOPICS-SCOPE-2).
    idx_sid_lines = "\n".join(
        seg
        for ln in idx_text.splitlines()
        for seg in (strip_history(ln),)
        if sid in seg
    )
    if not has_error_trace(sid, cur_text, idx_sid_lines):
        clear_counter(cpath)
        allow()

    # ── 작업 코드 저장소 식별 (문서 전용 세션 → 검사 제외) ──
    repos = detect_code_repos(cur_text)
    if not repos:
        clear_counter(cpath)
        allow()

    # ── (3) 적재 검사 (이미 등장 → 허용) ──
    if session_id_logged(sid, repos):
        clear_counter(cpath)
        allow()

    # ── 미적재 — 무한 루프 방지 ──
    attempts = read_counter(cpath) + 1
    write_counter(cpath, attempts)

    if attempts > MAX_BLOCKS:
        print(
            f"[ERROR-TOPICS] ⚠️ {MAX_BLOCKS}회 연속 차단에도 미해소 — 강제 종료 허용.\n"
            f"  {repos} error_topics 에 '{sid}' 오류 케이스를 수동 적재하세요.",
            file=sys.stderr,
        )
        clear_counter(cpath)
        allow()

    repo_hint = " · ".join(
        f"{r}/docs/rules/error_topics/" for r in repos
    )
    block(
        f"[ERROR-TOPICS] 오류 케이스 미적재 감지 — error_topics 적재 필요 "
        f"({attempts}/{MAX_BLOCKS})\n"
        f"  세션 '{sid}' 는 오류 흔적(self-debug/FIX-B)이 있으나\n"
        f"  작업 저장소 error_topics/*.md 어디에도 등장하지 않습니다.\n"
        f"  조치: 아래 경로의 적절한 주제 파일(testing.md·gate_process.md 등)에\n"
        f"    '## [YYYY-MM-DD] {sid} — 한줄 요약' 섹션을 append 하세요.\n"
        f"    대상: {repo_hint}\n"
        f"  ※ /error-log Skill 로 적재하거나 이 응답 턴에서 직접 작성 가능합니다.\n"
        f"  ※ 재활용 가치 없는 1회성 실수면 적재 후에도 무관 — MAX {MAX_BLOCKS}회 후 자동 해제됩니다."
    )


if __name__ == "__main__":
    main()
