#!/usr/bin/env python3
"""대화 기록에서 Gate 스킬 호출 순서를 읽는다 — 훅 공용 도우미.

훅 입력의 `transcript_path`(JSONL)에서 본 대화가 부른 Gate 스킬을 순서대로 뽑는다.
  - 모델이 Skill 도구로 부른 호출: `input.skill` (플러그인 접두어 `name:gate-x` 허용)
  - 사용자가 직접 입력해 펼쳐진 `/gate-x`: `<command-name>/gate-x</command-name>`
하위 에이전트(isSidechain) 줄은 본 대화의 진행이 아니므로 뺀다. 「gate-」가 없는 줄은
해석하지 않아 큰 기록에서도 빠르다(11MB 기록 약 50ms, S1 측정).

훅이 막았거나 실패한 Skill 호출은 실행되지 않았으므로 세지 않는다(2026-11-10). 그 호출의 결과 줄은
`"is_error": true` 로 남고 「gate-」 글자가 없을 수 있어, 결과를 기다리는 호출 id 가 든 줄도 읽는다
(기다리는 호출이 없으면 더 훑지 않는다). 재현: Gate D 루프 중 /gate-e 가 막힌 뒤 마지막 Gate 가 e 로
읽혀, test-write-guard 가 새 시험의 수정을 묻지 않았다. 호출 id 가 없거나 결과가 아직 없으면 지금처럼
부른 것으로 본다.

대화 기록은 비동기로 쓰여 현재 턴의 최신 줄이 아직 없을 수 있다(공식 hooks 문서).
호출하는 훅은 이 지연을 감안해 판정 방향을 정해야 한다.

`autonomous_approved` 는 마지막 gate-a 뒤에 사용자가 「자율 레인 승인」을 직접 썼는지 본다(S7). 스킬 본문
(`isMeta`)과 대화 압축 요약(`isCompactSummary`)도 user 줄로 기록되므로 뺀다 — gate-a 본문에 이 문구가 있다.

`wrote_to` 는 본 대화의 쓰기 도구(Edit·Write·MultiEdit)와 Bash 명령이 어떤 파일에 어떤 글자를 써 넣었는지 본다(2026-10-28).

쓰는 곳: test-write-guard.py(S1), comprehension-pending-guard.py(S3a), lane-scope-guard.py(S7), gate-e-sync-guard.py(Gate D 기록),
harness_report.py(사용 보고서의 Gate 순서).
"""

import json
import re

GATE_SKILL = re.compile(r"(?:^|:)gate-([a-e])$")
GATE_COMMAND = re.compile(r"<command-name>/(?:[\w-]+:)?gate-([a-e])</command-name>")
AUTONOMOUS_APPROVAL = "자율 레인 승인"
_TAGGED = re.compile(r"<([\w-]+)[^>]*>.*?</\1>", re.S)


def _awaited(line, pending):
    """결과를 기다리는 호출 id 가 이 줄에 있는가. 기다리는 호출이 없으면 줄을 훑지 않는다."""
    return bool(pending) and any(tid in line for tid in pending)


def _settle(content, pending, failed):
    """user 줄의 도구 결과로 기다리던 호출을 정리한다. 실패(`is_error`)한 호출 id 는 failed 에 넣는다."""
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
            pending.discard(b["tool_use_id"])
            if b.get("is_error"):
                failed.add(b["tool_use_id"])


def gate_sequence(transcript_path):
    """본 대화가 부른 Gate 글자('a'~'e') 목록. 막힌 호출은 뺀다. 경로가 없거나 못 읽으면 None."""
    if not transcript_path:
        return None
    seq = []      # (Gate 글자, 호출 id — 사용자가 입력한 명령은 None)
    pending, failed = set(), set()
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "gate-" not in line and not _awaited(line, pending):
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
                                seq.append((m.group(1), block.get("id")))
                                if block.get("id"):
                                    pending.add(block["id"])
                elif event.get("type") == "user":
                    _settle(content, pending, failed)
                    texts = [content] if isinstance(content, str) else [
                        b.get("text", "") for b in (content or [])
                        if isinstance(b, dict) and b.get("type") == "text"]
                    for text in texts:
                        seq.extend((m.group(1), None) for m in GATE_COMMAND.finditer(text or ""))
    except Exception:
        return None
    return [gate for gate, tid in seq if tid is None or tid not in failed]


def last_gate(transcript_path):
    """마지막으로 부른 Gate 글자. 없거나 못 읽으면 None."""
    seq = gate_sequence(transcript_path)
    return seq[-1] if seq else None


def _user_texts(event):
    content = (event.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    return [b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text"]


def autonomous_approved(transcript_path):
    """마지막 gate-a 뒤에 사용자가 「자율 레인 승인」을 썼으면 True. 못 읽거나 없으면 False."""
    if not transcript_path:
        return False
    approved = False
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "gate-" not in line and AUTONOMOUS_APPROVAL not in line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if not isinstance(event, dict) or event.get("isSidechain"):
                    continue
                if event.get("type") == "assistant":
                    for block in (event.get("message") or {}).get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "tool_use" \
                                and block.get("name") == "Skill":
                            m = GATE_SKILL.search(str((block.get("input") or {}).get("skill", "")))
                            if m and m.group(1) == "a":
                                approved = False
                elif event.get("type") == "user":
                    for text in _user_texts(event):
                        if any(m.group(1) == "a" for m in GATE_COMMAND.finditer(text or "")):
                            approved = False
                        elif not (event.get("isMeta") or event.get("isCompactSummary")) \
                                and AUTONOMOUS_APPROVAL in _TAGGED.sub("", text or ""):
                            approved = True
    except Exception:
        return False
    return approved


WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}
#: Bash 명령이 파일을 쓰는 표지. 읽기만 한 `grep "✅E" CURRENT_SESSION.md` 를 쓴 것으로 보면 ✅E 없이 끝낸 대화처럼
#: 잡힌다(2026-11-05 재현). `2>/dev/null`·`2>&1` 은 쓰기가 아니다.
SHELL_WRITE = re.compile(r"""(?<![0-9&])>>?\s*(?![&\s]|/dev/null)|\btee\b|\bsed\s+-i|<<|\.write\(|write_text\(|open\([^)\n]*['"][wa]""")


def _written_texts(name, inp):
    if name in WRITE_TOOLS:
        texts = [inp.get("new_string"), inp.get("content")] + [e.get("new_string") for e in inp.get("edits") or []
                                                               if isinstance(e, dict)]
        return inp.get("file_path") or "", [t for t in texts if isinstance(t, str)]
    if name == "Bash":
        cmd = inp.get("command") if isinstance(inp.get("command"), str) else ""
        return (cmd, [cmd]) if SHELL_WRITE.search(cmd) else ("", [])
    return "", []


def wrote_to(transcript_path, filename, pattern):
    """본 대화가 `filename` 에 `pattern`(정규식)에 맞는 글자를 써 넣었는가. 경로가 없거나 못 읽으면 None.

    쓰기 도구는 대상 경로가 `filename` 으로 끝나야 하고, Bash 는 명령에 `filename` 과 글자가 함께 있어야 한다(heredoc).
    하위 에이전트 줄은 뺀다. 현재 턴의 최신 줄은 아직 없을 수 있다 — 호출부는 None·False 를 통과로 다룬다.
    """
    if not transcript_path:
        return None
    rx = re.compile(pattern)
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if filename not in line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if event.get("type") != "assistant" or event.get("isSidechain"):
                    continue
                for block in (event.get("message") or {}).get("content") or []:
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    target, texts = _written_texts(block.get("name"), block.get("input") or {})
                    if block.get("name") in WRITE_TOOLS and not target.endswith(filename):
                        continue
                    if filename in target and any(rx.search(t) for t in texts):
                        return True
    except OSError:
        return None
    return False


def invoked(transcript_path, skill):
    """본 대화가 스킬 `skill` 을 불렀는가(Skill 도구 또는 사용자가 입력한 `/skill`). 막힌 호출은 부른 것이 아니다.
    못 읽으면 None."""
    if not transcript_path:
        return None
    rx = re.compile(r"<command-name>/(?:[\w-]+:)?" + re.escape(skill) + r"</command-name>")
    calls = []    # 결과와 짝지을 Skill 호출 id
    pending, failed = set(), set()
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if skill not in line and not _awaited(line, pending):
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if not isinstance(event, dict) or event.get("isSidechain"):
                    continue
                content = (event.get("message") or {}).get("content")
                if event.get("type") == "assistant":
                    for block in content or []:
                        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill" \
                                and str((block.get("input") or {}).get("skill", "")).split(":")[-1] == skill:
                            if not block.get("id"):
                                return True
                            calls.append(block["id"])
                            pending.add(block["id"])
                elif event.get("type") == "user":
                    _settle(content, pending, failed)
                    if not event.get("isMeta") and skill in line and rx.search(json.dumps(content, ensure_ascii=False)):
                        return True
    except OSError:
        return None
    return any(tid not in failed for tid in calls)
