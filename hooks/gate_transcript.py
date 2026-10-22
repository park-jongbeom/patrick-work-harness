#!/usr/bin/env python3
"""대화 기록에서 Gate 스킬 호출 순서를 읽는다 — 훅 공용 도우미.

훅 입력의 `transcript_path`(JSONL)에서 본 대화가 부른 Gate 스킬을 순서대로 뽑는다.
  - 모델이 Skill 도구로 부른 호출: `input.skill` (플러그인 접두어 `name:gate-x` 허용)
  - 사용자가 직접 입력해 펼쳐진 `/gate-x`: `<command-name>/gate-x</command-name>`
하위 에이전트(isSidechain) 줄은 본 대화의 진행이 아니므로 뺀다. 「gate-」가 없는 줄은
해석하지 않아 큰 기록에서도 빠르다(11MB 기록 약 50ms, S1 측정).

대화 기록은 비동기로 쓰여 현재 턴의 최신 줄이 아직 없을 수 있다(공식 hooks 문서).
호출하는 훅은 이 지연을 감안해 판정 방향을 정해야 한다.

쓰는 곳: test-write-guard.py(S1), comprehension-pending-guard.py(S3a).
"""

import json
import re

GATE_SKILL = re.compile(r"(?:^|:)gate-([a-e])$")
GATE_COMMAND = re.compile(r"<command-name>/(?:[\w-]+:)?gate-([a-e])</command-name>")


def gate_sequence(transcript_path):
    """본 대화가 부른 Gate 글자('a'~'e') 목록. 경로가 없거나 못 읽으면 None."""
    if not transcript_path:
        return None
    seq = []
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
                                seq.append(m.group(1))
                elif event.get("type") == "user":
                    texts = [content] if isinstance(content, str) else [
                        b.get("text", "") for b in (content or [])
                        if isinstance(b, dict) and b.get("type") == "text"]
                    for text in texts:
                        seq.extend(m.group(1) for m in GATE_COMMAND.finditer(text or ""))
    except Exception:
        return None
    return seq


def last_gate(transcript_path):
    """마지막으로 부른 Gate 글자. 없거나 못 읽으면 None."""
    seq = gate_sequence(transcript_path)
    return seq[-1] if seq else None
