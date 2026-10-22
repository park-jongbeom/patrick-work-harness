#!/usr/bin/env python3
"""
Gate D(검증) 중 시험 파일 쓰기는 사용자에게 묻는다 — Claude Code PreToolUse(Edit|Write|MultiEdit|NotebookEdit) Hook.

왜: gate-d 2-B 루프는 「시험 파일은 읽기 전용, 통과를 위한 시험 수정 금지(R-2-G)」를 **문장**으로
정했고, 사후 감시는 Stop 시점 test-tampering 가드뿐이었다. 시험 변조는 실재한다 — ImpossibleBench
(arXiv:2510.20270)에서 Claude 계열 모델의 부정행위 79% 이상이 시험 수정이었고, 피드백 라운드가
늘수록 부정행위도 늘었다. 공식 skills 문서는 「매번 지켜야 할 규칙은 훅으로」라고 한다.

동작: 지금이 Gate D 이고 대상 경로가 시험 파일이면 `permissionDecision: "ask"` 로 사용자 확인을
받는다. 「지금이 Gate D」는 두 신호 중 하나로 판정한다.
  ① 대화 기록(훅 입력 `transcript_path`)에서 마지막으로 부른 Gate 스킬이 gate-d.
  ② `CURRENT_SESSION.md` 의 현재 상태가 D 로 시작.
①을 더한 이유(S1, 2026-10-22): gate-d 는 루프가 끝난 뒤 Step 6 에서야 상태를 「D (확인 대기)」로
쓴다. 루프 동안 상태는 gate-c 가 남긴 「C (확인 대기)」라, ②만으로는 지켜야 할 루프에서 가드가
꺼졌다. 대화 기록은 비동기로 쓰여 현재 턴의 최신 줄이 아직 없을 수 있으므로(공식 hooks 문서)
②를 함께 유지한다 — 신호를 더하기만 하므로 보호가 줄어드는 경우는 없다. 막지(deny) 않는 이유: 명세와 시험이 실제로
충돌하는 정당한 수정도 있다 — 그때는 사용자가 사유를 보고 승인한다(「명세·시험 충돌」 신고 경로).
시험 경로 판정은 report_facts.category 와 같은 규칙을 쓴다.

방어 원칙: 문서 부재·파싱 실패·예외·Gate D 아님은 모두 통과(fail-open).
"""

import json
import os
import re
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


GATE_SKILL = re.compile(r"(?:^|:)gate-([a-e])$")
GATE_COMMAND = re.compile(r"<command-name>/(?:[\w-]+:)?gate-([a-e])</command-name>")


def last_gate(transcript_path):
    """대화 기록에서 마지막으로 부른 Gate 글자('a'~'e'). 못 찾거나 못 읽으면 None.

    Skill 도구 호출(`input.skill`, 플러그인 접두어 허용)과 `/gate-x` 직접 입력을 모두 본다.
    하위 에이전트(isSidechain) 줄은 본 대화의 진행이 아니므로 뺀다. 「gate-」가 없는 줄은
    해석하지 않아 큰 기록에서도 빠르다.
    """
    if not transcript_path:
        return None
    found = None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "gate-" not in line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if not isinstance(event, dict) or event.get("isSidechain"):
                    continue
                content = (event.get("message") or {}).get("content")
                if event.get("type") == "assistant" and isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use" \
                                and block.get("name") == "Skill":
                            m = GATE_SKILL.search(str((block.get("input") or {}).get("skill", "")))
                            if m:
                                found = m.group(1)
                elif event.get("type") == "user":
                    texts = [content] if isinstance(content, str) else [
                        b.get("text", "") for b in (content or [])
                        if isinstance(b, dict) and b.get("type") == "text"]
                    for text in texts:
                        for m in GATE_COMMAND.finditer(text or ""):
                            found = m.group(1)
    except Exception:
        return None
    return found


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
        if not target or not is_test_path(target):
            return 0
        if last_gate(payload.get("transcript_path")) != "d" and not in_gate_d():
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
