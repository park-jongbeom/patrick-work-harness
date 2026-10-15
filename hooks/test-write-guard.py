#!/usr/bin/env python3
"""
Gate D(검증) 중 시험 파일 쓰기는 사용자에게 묻는다 — Claude Code PreToolUse(Edit|Write|MultiEdit|NotebookEdit) Hook.

왜: gate-d 2-B 루프는 「시험 파일은 읽기 전용, 통과를 위한 시험 수정 금지(R-2-G)」를 **문장**으로
정했고, 사후 감시는 Stop 시점 test-tampering 가드뿐이었다. 시험 변조는 실재한다 — ImpossibleBench
(arXiv:2510.20270)에서 Claude 계열 모델의 부정행위 79% 이상이 시험 수정이었고, 피드백 라운드가
늘수록 부정행위도 늘었다. 공식 skills 문서는 「매번 지켜야 할 규칙은 훅으로」라고 한다.

동작: `CURRENT_SESSION.md` 의 현재 상태가 Gate D 이고 대상 경로가 시험 파일이면
`permissionDecision: "ask"` 로 사용자 확인을 받는다. 막지(deny) 않는 이유: 명세와 시험이 실제로
충돌하는 정당한 수정도 있다 — 그때는 사용자가 사유를 보고 승인한다(「명세·시험 충돌」 신고 경로).
시험 경로 판정은 report_facts.category 와 같은 규칙을 쓴다.

방어 원칙: 문서 부재·파싱 실패·예외·Gate D 아님은 모두 통과(fail-open).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = (
    os.environ.get("TEST_WRITE_GUARD_BASE")
    or os.environ.get("CLAUDE_PROJECT_DIR")
    or "."
)
CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def in_gate_d(path=CURRENT_SESSION):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        from session_dashboard_parsers import parse_current_session

        status = (parse_current_session(content).get("status") or "").strip()
        return status.startswith("D")
    except Exception:
        return False


def is_test_path(path, base=BASE_DIR):
    from report_facts import category

    rel = os.path.relpath(path, base) if os.path.isabs(path) else path
    return category(rel.replace(os.sep, "/")) == "tests"


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in WRITE_TOOLS:
        return 0
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    try:
        if not target or not is_test_path(target) or not in_gate_d():
            return 0
    except Exception:
        return 0
    reason = (
        f"Gate D(검증) 중 시험 파일 수정: {target}\n"
        "검증 루프에서 통과를 위해 시험을 고치는 것은 금지다(gate-d R-2-G). 시험 강화는 Gate C 산출물이다.\n"
        "명세와 시험이 실제로 충돌해 고쳐야 하는 경우만 승인하세요 — 그 사유를 결과 보고의 FIX-B 로 남깁니다."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
