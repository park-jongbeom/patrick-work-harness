#!/usr/bin/env python3
"""
00_MASTER_PLAN.md 인덱스 신선도 강제 — Claude Code Stop Hook.

harness_runtime_charter §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

배경 (HARNESS-STALE-GUARD-1, 2026-05-22):
  PLAN-SYNC-11/12/13/14가 모두 "인덱스 스테일 정정" 전용 세션으로 소모됐다.
  근본 원인: 00_MASTER_PLAN.md L7 status/§4 「현재」 라인은 정책상(CLAUDE.md)
  세션 단위 갱신 대상이 아니어서 매 세션 자동으로 낡는다. Gate E·/audit·기존
  훅 중 어느 것도 이 drift를 탐지하지 않았다.
  본 훅이 응답 종료 시점에 인덱스 L7 신선도를 검사해 drift 발생 즉시 차단한다.

프로토콜 (Claude Code Stop Hook):
  - 입력: stdin JSON — { session_id, ... }
  - 차단: stderr 메시지 + exit 2 (Claude가 종료를 멈추고 계속 작업)
  - 허용: exit 0

차단 조건 (2중 AND):
  (1) CURRENT_SESSION.md 헤더 '**세션 ID**' 추출 성공
  (2) 00_MASTER_PLAN.md L7 status: 첫 세션 ID 토큰이 (1)과 다름

파서 복구 (HARNESS-GATE-A-GUARD-1, 2026-06-03):
  기존 (1)은 SESSION_INDEX.md YAML `sessions:` 블록을 정규식으로 찾았으나,
  인덱스 구조 변경(세션 목록 YAML → 마크다운 표 이동)으로 항상 None 반환 →
  파싱 실패 → 무조건 허용으로 빠져 가드가 no-op 무력화됐다. 현재 세션의 단일
  진실원인 CURRENT_SESSION.md 헤더 '**세션 ID**' 를 정본으로 전환.

방어 원칙: 파일 부재·파싱 실패·예외는 무조건 exit 0 (오탐 차단 금지).
무한 루프 방지: 세션별 연속 차단 횟수를 임시 파일에 기록, MAX 초과 시 exit 0.
"""

import json
import os
import re
import sys
import tempfile

# 한글 systemMessage 를 Windows cp949 stdout 에서도 내보내도록 고정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 정본 절대경로 — R-4-2-b: 3단 우선순위 (① MASTER_PLAN_GUARD_BASE[테스트] → ② CLAUDE_PROJECT_DIR → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
BASE_DIR = (
    os.environ.get("MASTER_PLAN_GUARD_BASE")
    or (_proj if _proj else None)
    or os.environ.get("CLAUDE_PROJECT_DIR", ".")
)
CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")
DEFAULT_MASTER_PLAN = "00_MASTER_PLAN.md"


def _answer(raw, key):
    """harness-answers.yml 의 최상위 문자열 값 하나. 따옴표·줄 끝 주석을 뗀다. 없으면 ""."""
    m = re.search(rf"^{key}:[ \t]*(.*)$", raw, re.M)
    if not m:
        return ""
    value = re.sub(r"\s+#.*$", "", m.group(1)).strip()
    return value[1:-1].strip() if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def master_plan_path(base_dir=BASE_DIR):
    """인덱스 문서 경로. 단일 계획 문서(plan_tier 1)면 None — 인덱스가 없다.

    파일 이름을 00_MASTER_PLAN.md 로 고정해 `master_plan_file` 을 다르게 둔 프로젝트에서 가드가 조용히 꺼져 있었다
    (2026-11-05 점검). 설정이 없거나 채우지 않은 자리표시(`${…}`·`<…>`)면 기본 이름을 쓴다.
    """
    try:
        with open(os.path.join(base_dir, ".claude", "harness-answers.yml"), encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        raw = ""
    if _answer(raw, "plan_tier") == "1":
        return None
    name = _answer(raw, "master_plan_file")
    if not name or "${" in name or name.startswith("<"):
        name = DEFAULT_MASTER_PLAN
    return name if os.path.isabs(name) else os.path.join(base_dir, name)

# 연속 차단 한도 (무한 루프 방지)
MAX_BLOCKS = 3


def notify(message):
    """사용자에게 보이는 비차단 알림 — stdout systemMessage JSON(exit 0 훅의 stderr 는
    사용자·Claude 어디에도 전달되지 않는다. 공식 hooks 문서 「exit code 0」)."""
    try:
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
    except (TypeError, ValueError):
        print(message, file=sys.stderr)


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


def current_session_id(cur_text):
    """
    CURRENT_SESSION.md 헤더 '**세션 ID**' 의 세션 ID 추출.

    HARNESS-GATE-A-GUARD-1(2026-06-03) 파서 복구:
      기존 SESSION_INDEX.md YAML `sessions:` 블록 의존은 인덱스 구조 변경
      (세션 목록이 YAML → 마크다운 표로 이동)으로 항상 None 을 반환,
      가드가 no-op 무력화됐다. 현재 세션의 단일 진실원은 CURRENT_SESSION.md
      헤더이므로 그 '**세션 ID**' 값을 정본으로 삼는다.
      gate-a-sync-guard.py / gate-e-sync-guard.py current_session_state() 와 동일 패턴.

    폴백 1단 (HARNESS-WIN-PORT-2, 2026-07-27):
      '**세션 ID**' 필드가 없는 세션(관행상 '## {세션ID}' 헤딩만 기록)에서
      파싱 실패 → 방어원칙(exit 0)으로 조용히 통과해 인덱스 stale을 놓치는
      사례 실측(HARNESS-LOOP-TIER-1, L7 status 20일 미정정). 기존 패턴은
      그대로 두고, 실패 시에만 최상단 '## {세션ID}' 헤딩으로 재시도한다.

    폴백 2단 (FIX-B-STALE-GUARD-PARSER-1, 2026-07-27):
      1단 폴백('## {세션ID}' 헤딩)이 완료 세션의 잔존 본문 소제목
      (예: '## Gate A 계획')을 세션 ID로 오인해 'Gate'만 캡처하는 오탐
      실측(HARNESS-WIN-PORT-3-a Gate E·doc-cleanup 응답에서 반복 재현).
      DASHBOARD-INTENT-1(gate-a)이 항상 기록하는
      '> **세션 주제**: {세션ID} — ...' 필드가 세션 ID를 담은 더 신뢰
      가능한 정본이므로, '## {세션ID}' 헤딩보다 먼저 시도한다.
    """
    m_id = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z0-9][\w\-]*)", cur_text)
    if m_id:
        return m_id.group(1)
    m_topic = re.search(r"\*\*세션 주제\*\*:\s*([A-Za-z0-9][\w\-]*)", cur_text)
    if m_topic:
        return m_topic.group(1)
    m_heading = re.search(r"^##\s+([A-Za-z0-9][\w\-]*)", cur_text, re.M)
    if m_heading:
        return m_heading.group(1)
    return None


def master_plan_first_session_id(plan_text):
    """
    00_MASTER_PLAN.md L7 YAML status: 값의 첫 세션 ID 토큰 추출.
    형식: status: "<세션ID> <설명>..."
    첫 토큰이 영문자로 시작하는 세션 ID (예: PLAN-SYNC-14, HARNESS-STALE-GUARD-1). 영문자 시작은 완료 표기
    (`✅E …`)를 ID 로 읽지 않기 위해 둔다. 밑줄은 허용한다 — 빼면 FEAT_LOGIN-1 이 FEAT 로 잘려 같은 세션을
    막았다(2026-11-05 재현). 현재 세션 쪽(`current_session_id`)과 같은 문자 집합이다.
    """
    m = re.search(r'^status:\s*"([^"]+)"', plan_text, re.M)
    if not m:
        return None
    status_value = m.group(1).strip()
    # 첫 단어(공백 전)가 세션 ID — 영문자로 시작, 영문자·숫자·밑줄·하이픈
    m_tok = re.match(r"([A-Za-z][\w\-]*)", status_value)
    if not m_tok:
        return None
    return m_tok.group(1)


def counter_path(session_id):
    """
    FIX-B-STALE-GUARD-PARSER-1(2026-07-27): 하드코딩 '/tmp' 은 Windows Python
    에서 'D:\\tmp' (부재 경로) 로 해석되어 카운터 쓰기가 매번 조용히 실패,
    MAX_BLOCKS 무한루프 방지가 무력화되는 버그 실측(Gate D 검증 중 발견).
    tempfile.gettempdir() 로 OS별 실제 임시 디렉터리를 사용한다.
    """
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join(tempfile.gettempdir(), f".master-plan-stale-guard-{safe}.count")


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
    plan_path = master_plan_path()
    plan_text = read_text(plan_path) if plan_path else None
    plan_name = os.path.basename(plan_path or DEFAULT_MASTER_PLAN)
    if cur_text is None or plan_text is None:
        clear_counter(cpath)
        allow()

    # ── 파싱 (실패 시 검증 불가 → 허용) ──
    cur_id = current_session_id(cur_text)
    plan_id = master_plan_first_session_id(plan_text)
    if not cur_id or not plan_id:
        clear_counter(cpath)
        allow()

    # ── 일치 → 허용 ──
    if cur_id == plan_id:
        clear_counter(cpath)
        allow()

    # ── 불일치 — 무한 루프 방지 ──
    attempts = read_counter(cpath) + 1
    write_counter(cpath, attempts)

    if attempts > MAX_BLOCKS:      # 카운터를 지우면 다시 3회 막는다 — 조건이 풀릴 때 위에서 지운다
        if attempts == MAX_BLOCKS + 1:
            notify(
                f"[MASTER-PLAN-STALE] ⚠️ {MAX_BLOCKS}회 연속 차단에도 미해소 — 강제 종료 허용.\n"
                f"  {plan_name} L7 status 를 수동으로 갱신하세요."
            )
        allow()

    block(
        f"[MASTER-PLAN-STALE] 인덱스 스테일 감지 — {plan_name} L7 갱신 필요 "
        f"({attempts}/{MAX_BLOCKS})\n"
        f"  CURRENT_SESSION.md 현재 세션 : '{cur_id}'\n"
        f"  {plan_name} L7 status : '{plan_id}' (불일치)\n"
        f"  조치: {plan_name} YAML 헤더 L7 status: 를\n"
        f"    \"{cur_id} <현재 작업 설명>...\" 으로 갱신하세요.\n"
        f"  §4 「현재」 라인도 함께 갱신하면 완전한 동기화가 됩니다.\n"
        f"  ※ PLAN-SYNC 청소 세션 없이 이 응답 턴에서 직접 수정 가능합니다."
    )


if __name__ == "__main__":
    main()
