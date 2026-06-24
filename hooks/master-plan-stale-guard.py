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

# 정본 절대경로 — R-4-2-b: 3단 우선순위 (① MASTER_PLAN_GUARD_BASE[테스트] → ② CLAUDE_PROJECT_DIR → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
BASE_DIR = (
    os.environ.get("MASTER_PLAN_GUARD_BASE")
    or (_proj if _proj else None)
    or os.environ.get("CLAUDE_PROJECT_DIR", ".")
)
CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")
MASTER_PLAN = os.path.join(BASE_DIR, "00_MASTER_PLAN.md")

# 연속 차단 한도 (무한 루프 방지)
MAX_BLOCKS = 3


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
    """
    m_id = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z0-9][\w\-]*)", cur_text)
    if not m_id:
        return None
    return m_id.group(1)


def master_plan_first_session_id(plan_text):
    """
    00_MASTER_PLAN.md L7 YAML status: 값의 첫 세션 ID 토큰 추출.
    형식: status: "<세션ID> <설명>..."
    첫 토큰이 영문자로 시작하는 세션 ID (예: PLAN-SYNC-14, HARNESS-STALE-GUARD-1).
    """
    m = re.search(r'^status:\s*"([^"]+)"', plan_text, re.M)
    if not m:
        return None
    status_value = m.group(1).strip()
    # 첫 단어(공백 전)가 세션 ID — 영문자+숫자+하이픈으로만 구성
    m_tok = re.match(r"([A-Za-z][A-Za-z0-9\-]*)", status_value)
    if not m_tok:
        return None
    return m_tok.group(1)


def counter_path(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".master-plan-stale-guard-{safe}.count")


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
    plan_text = read_text(MASTER_PLAN)
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

    if attempts > MAX_BLOCKS:
        print(
            f"[MASTER-PLAN-STALE] ⚠️ {MAX_BLOCKS}회 연속 차단에도 미해소 — 강제 종료 허용.\n"
            f"  00_MASTER_PLAN.md L7 status 를 수동으로 갱신하세요.",
            file=sys.stderr,
        )
        clear_counter(cpath)
        allow()

    block(
        f"[MASTER-PLAN-STALE] 인덱스 스테일 감지 — 00_MASTER_PLAN.md L7 갱신 필요 "
        f"({attempts}/{MAX_BLOCKS})\n"
        f"  CURRENT_SESSION.md 현재 세션 : '{cur_id}'\n"
        f"  00_MASTER_PLAN.md L7 status : '{plan_id}' (불일치)\n"
        f"  조치: 00_MASTER_PLAN.md YAML 헤더 L7 status: 를\n"
        f"    \"{cur_id} <현재 작업 설명>...\" 으로 갱신하세요.\n"
        f"  §4 「현재」 라인도 함께 갱신하면 완전한 동기화가 됩니다.\n"
        f"  ※ PLAN-SYNC 청소 세션 없이 이 응답 턴에서 직접 수정 가능합니다."
    )


if __name__ == "__main__":
    main()
