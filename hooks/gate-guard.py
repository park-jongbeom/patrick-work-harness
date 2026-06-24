#!/usr/bin/env python3
"""
Gate 워크플로 결정적 강제 — Cursor Agent Hook 스크립트.

harness_runtime_charter.md §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

지원 이벤트:
  - beforeFileEdit:      Gate A 미승인 시 코드 편집 차단
  - beforeShellExecution: Gate C/D 미도달 시 테스트 명령 차단
  - sessionStart:        현재 Gate 상태를 에이전트 컨텍스트에 주입

사용법:
  .cursor/hooks.json 에서 참조:
  { "command": "python3 ../plans/hooks/gate-guard.py" }

입력: stdin JSON (Cursor hook payload)
출력: stdout JSON (allow/block 결정) + exit code
  - exit 0: 허용
  - exit 1: 차단 (사유 표시)
"""

import json
import os
import re
import sys

SESSION_PATHS = [
    os.path.join(os.getcwd(), "..", "plans", "current_work", "CURRENT_SESSION.md"),
    os.path.join(os.getcwd(), "plans", "current_work", "CURRENT_SESSION.md"),
]

TEST_CMD_PATTERNS = [
    r'\bnpm\s+test\b',
    r'\bnpx\s+vitest\b',
    r'\bvitest\b',
    r'\bpytest\b',
    r'\bgradlew\s+(clean)?test\b',
    r'\bgradlew\s+.*\btest\b',
    r'\bdocker\s+exec\s+.*\b(npm\s+test|pytest|gradlew\s+.*test)\b',
]

# 편집 차단에서 제외할 경로 (프로세스 문서, IDE 설정 등)
EXEMPT_PATH_PATTERNS = [
    r'\.cursor/',
    r'plans/',
    r'docs/',
    r'tasks/',
    r'\.github/',
    r'CURRENT_SESSION',
    r'WORKLOG',
    r'HARNESS_EVOLUTION',
    r'\.md$',
]


def find_session_file():
    for path in SESSION_PATHS:
        resolved = os.path.realpath(path)
        if os.path.isfile(resolved):
            return resolved
    return None


def read_session(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def parse_gate_status(content):
    """
    대시보드에서 현재 Gate 상태 파싱.
    Returns: (gate_letter, status_emoji, description)
    """
    # 패턴 1: > **현재 Gate**: ✅E (세션 완료)  /  ⏸A — 승인 대기
    m = re.search(
        r'\*\*현재 Gate\*\*:\s*(✅|⏸|☐)?\s*([A-E])\s*[\-—]?\s*(.*?)$',
        content, re.MULTILINE,
    )
    if m:
        return m.group(2), m.group(1) or "", m.group(3).strip()

    # 패턴 2: Gate 진행 행 — ✅A → ✅B → ⏸C → ☐D → ☐E
    m = re.search(r'\*\*Gate 진행\*\*\s*\|\s*(.+?)\s*\|', content)
    if m:
        progress = m.group(1).strip()
        paused = re.search(r'⏸\s*([A-E])', progress)
        if paused:
            return paused.group(1), "⏸", "대기"
        done = re.findall(r'✅\s*([A-E])', progress)
        if done:
            return done[-1], "✅", "완료"

    return None, None, None


def is_gate_a_blocked(content):
    """Gate A가 승인 대기(⏸) 상태인지 확인."""
    gate, emoji, _ = parse_gate_status(content)
    if gate == "A" and emoji == "⏸":
        return True
    for pattern in [r'Gate\s*A.*승인\s*대기', r'Gate\s*A.*사용자\s*확인\s*전']:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def is_test_phase_blocked(content):
    """
    테스트 명령 실행 가능 여부 확인.
    Gate D(검증) 단계에 도달하지 않았으면 차단.
    Gate B 완료 직후(⏸C)이면 테스트 차단.
    """
    gate, emoji, _ = parse_gate_status(content)
    if gate is None:
        return False
    if gate in ("D", "E"):
        return False
    if gate == "C" and emoji == "✅":
        return False
    # Gate A, B, 또는 ⏸C 상태에서는 테스트 차단
    if gate in ("A", "B") or (gate == "C" and emoji == "⏸"):
        return True
    return False


def is_test_command(command):
    for pattern in TEST_CMD_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def is_exempt_path(file_path):
    for pattern in EXEMPT_PATH_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def block(reason):
    result = {"decision": "block", "reason": reason}
    json.dump(result, sys.stdout)
    sys.exit(1)


def allow():
    sys.exit(0)


def inject_context(content):
    """sessionStart: 현재 Gate 상태를 에이전트 컨텍스트에 주입."""
    gate, emoji, desc = parse_gate_status(content)
    if gate:
        ctx = f"[Gate 상태] 현재 Gate {gate} ({emoji}{desc})"
        result = {"additionalContext": ctx}
        json.dump(result, sys.stdout)
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    session_file = find_session_file()
    if not session_file:
        allow()

    content = read_session(session_file)
    if not content:
        allow()

    hook_event = os.environ.get("CURSOR_HOOK_EVENT", "")

    # beforeFileEdit — Gate A 미승인 시 코드 편집 차단
    if hook_event == "beforeFileEdit" or "file_path" in payload:
        file_path = payload.get("file_path", "")
        if is_exempt_path(file_path):
            allow()
        if is_gate_a_blocked(content):
            block(f"Gate A 승인 대기 — 코드 수정 차단됨. "
                  f"CURRENT_SESSION.md에서 Gate A 승인 후 재시도하세요. "
                  f"(대상: {file_path})")

    # beforeShellExecution — Gate C/D 미도달 시 테스트 차단
    if hook_event == "beforeShellExecution" or "command" in payload:
        command = payload.get("command", "")
        if is_test_command(command) and is_test_phase_blocked(content):
            gate, emoji, desc = parse_gate_status(content)
            block(f"Gate {gate}({emoji}) 상태에서 테스트 명령 차단됨. "
                  f"Gate D(검증) 단계에서 실행하세요. "
                  f"(명령: {command})")

    # sessionStart — Gate 상태 컨텍스트 주입
    if hook_event == "sessionStart" or payload.get("source") in ("startup", "resume"):
        inject_context(content)

    allow()


if __name__ == "__main__":
    main()
