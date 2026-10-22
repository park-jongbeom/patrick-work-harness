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

「지금 계획의 질문인가」(S3a, 2026-10-22): 파서는 문서의 첫 Gate B 블록만 본다. 그 질문이 이전
계획의 것이면 새 계획이 Gate B 없이 gate-c 로 갈 때 잘못 막힌다. 그래서 대화 기록(훅 입력
`transcript_path`)에서 마지막 gate-a 뒤에 gate-b 가 없으면 문서의 미답 질문은 이전 계획의 것으로
보고 막지 않는다 — 대신 한 줄로 알린다. 대화 기록에 Gate 호출이 하나도 없거나(새 대화에서 이어
하는 경우) 읽을 수 없으면 예전처럼 막는다. 대화 기록 지연(최신 줄 누락)은 gate-b 를 못 보는 쪽으로만
작용하는데, gate-b 는 질문을 쓰고 사용자 답을 기다린 턴 뒤라 실제로는 기록돼 있다.

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


def question_is_from_earlier_plan(transcript_path):
    """마지막 gate-a 뒤에 gate-b 가 없으면 True. 판정할 기록이 없으면 False(막는 쪽)."""
    from gate_transcript import gate_sequence

    seq = gate_sequence(transcript_path)
    if not seq or "a" not in seq:
        return False
    last_a = len(seq) - 1 - seq[::-1].index("a")
    return "b" not in seq[last_a + 1:]


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

    try:
        stale = question_is_from_earlier_plan(payload.get("transcript_path"))
    except Exception:
        stale = False
    if stale:
        print(json.dumps({"systemMessage": (
            f"[이해도] 문서에 이전 계획의 미답 질문이 남아 있습니다({', '.join(pending)}). "
            f"이번 계획은 Gate B 없이 /{skill} 로 진행하므로 막지 않습니다 — 필요하면 /gate-b 로 새 질문을 받으세요."
        )}, ensure_ascii=False))
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
