#!/usr/bin/env python3
"""
이해도 질문이 답을 기다리는 동안 gate-c·gate-d·gate-e 진입을 막는다 — Claude Code Hook.

왜: gate-b 는 질문 대기 중 「구현」「진행」은 답도 스킵도 아니라고 **문장으로** 정했다
(v1.7.0). 문장은 모델이 따를 수도 안 따를 수도 있다. 공식 skills 문서는 「매번 지켜야 할
규칙은 훅으로 옮겨라」고 하고, 실사용에서 질문이 「구현」 한마디로 넘어간 일이 점검에서
3회 지적됐다. 이 훅이 그 규칙을 결정적으로 지킨다.

두 경로를 다 본다(공식 hooks 문서 UserPromptExpansion 절):
  - 사용자가 `/gate-c` 를 직접 입력 → UserPromptExpansion (PreToolUse 를 거치지 않는다)
  - 모델이 Skill 도구로 gate-c 를 부름 → PreToolUse(matcher "Skill"), tool_input.skill

판정: `CURRENT_SESSION.md` Gate B 블록의 `### 질문 N` 중 평가가 자리표시(「(답변 후 기록)」)
뿐인 것이 있으면 막는다. 답하거나 「스킵」을 명시해 평가가 적히면 풀린다.
파서는 대시보드와 같은 `session_dashboard_parsers.parse_comprehension` 을 쓴다.

방어 원칙: 파일 부재·파싱 실패·예외는 모두 허용(fail-open). 이 훅이 고장 나서 작업을
멈추게 하면 안 된다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = (
    os.environ.get("COMPREHENSION_PENDING_GUARD_BASE")
    or os.environ.get("CLAUDE_PROJECT_DIR")
    or "."
)
CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")

#: 질문이 대기 중이면 들어가면 안 되는 Gate 스킬(플러그인 접두어는 떼고 본다).
GUARDED = {"gate-c", "gate-d", "gate-e"}


def skill_name(raw):
    """`patrick-work-harness:gate-c` · `/gate-c` · `gate-c` → `gate-c`."""
    name = (raw or "").strip().lstrip("/").split()[0] if (raw or "").strip() else ""
    return name.rsplit(":", 1)[-1]


def pending_questions(path=CURRENT_SESSION):
    """평가가 아직 없는 질문 제목 목록. 읽을 수 없으면 빈 목록(fail-open)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        from session_dashboard_parsers import parse_comprehension

        questions = parse_comprehension(content).get("questions", [])
        return [q.get("title", "질문") for q in questions if not q.get("evaluated")]
    except Exception:
        return []


def reason_text(skill, pending):
    return (
        f"이해도 질문이 답을 기다리고 있어 /{skill} 단계를 시작하지 않습니다 — "
        f"{', '.join(pending)}. 질문에 답하거나, 답하지 않고 넘어가려면 「스킵」이라고 "
        f"명시해 주세요(gate-b 가 평가를 기록하면 풀립니다)."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    event = payload.get("hook_event_name", "")
    if event == "UserPromptExpansion":
        skill = skill_name(payload.get("command_name"))
    elif event == "PreToolUse" and payload.get("tool_name") == "Skill":
        skill = skill_name((payload.get("tool_input") or {}).get("skill"))
    else:
        return 0
    if skill not in GUARDED:
        return 0

    pending = pending_questions()
    if not pending:
        return 0

    reason = reason_text(skill, pending)
    if event == "UserPromptExpansion":
        out = {"decision": "block", "reason": reason}
    else:
        out = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
