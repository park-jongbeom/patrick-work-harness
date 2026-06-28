#!/usr/bin/env python3
"""
Gate 워크플로 결정적 강제 — Claude Code PreToolUse Hook.

harness_runtime_charter.md §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

원본: gate-guard.py (Cursor Agent Hook) → Claude Code PreToolUse 훅으로 포팅.

프로토콜:
  - 입력: stdin JSON — { tool_name, tool_input: {command?, file_path?}, cwd }
  - 차단: stderr 메시지 + exit 2
  - 허용: exit 0

대상 도구:
  - Edit / Write:  Gate A 미승인 시 코드 편집 차단
  - Bash:          Gate D 미도달 시 테스트 명령 차단
"""

import json
import os
import re
import sys

# CURRENT_SESSION.md 탐색 경로 (우선순위순)
# R-4-2-a: CLAUDE_PROJECT_DIR 존재 시 선두 삽입, 절대경로는 폴백으로 유지
_proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
SESSION_SEARCH_DIRS = (
    [_proj_dir, os.environ.get("HARNESS_ROOT_DIR", ".")] if _proj_dir else [os.environ.get("HARNESS_ROOT_DIR", ".")]
)

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
    r'\.claude/',
    r'\.cursor/',
    r'plans/',
    r'docs/',
    r'tasks/',
    r'\.github/',
    r'CURRENT_SESSION',
    r'SESSION_INDEX',
    r'WORKLOG',
    r'HARNESS_EVOLUTION',
    r'\.md$',
]


def find_session_file(cwd):
    """CURRENT_SESSION.md를 여러 경로에서 탐색.

    정본은 리포 루트(`{repo}/CURRENT_SESSION.md`)이므로 루트 후보를 먼저 검사한다.
    구 `plans/current_work/` 위치는 레거시 폴백 — 과거 stale 파일이 잔존할 수 있어 후순위.
    """
    candidates = []

    # 1순위: 리포 루트 CURRENT_SESSION.md (정본 위치)
    if cwd:
        candidates.append(os.path.join(cwd, "CURRENT_SESSION.md"))
    for base in SESSION_SEARCH_DIRS:
        candidates.append(os.path.join(base, "CURRENT_SESSION.md"))

    # 2순위(레거시): plans/current_work/ (구 위치 — stale 잔존 가능, 후순위)
    if cwd:
        candidates.append(
            os.path.join(cwd, "..", "plans", "current_work", "CURRENT_SESSION.md")
        )
        candidates.append(
            os.path.join(cwd, "plans", "current_work", "CURRENT_SESSION.md")
        )
    for base in SESSION_SEARCH_DIRS:
        candidates.append(
            os.path.join(base, "plans", "current_work", "CURRENT_SESSION.md")
        )

    for path in candidates:
        resolved = os.path.realpath(path)
        if os.path.isfile(resolved):
            return resolved
    return None


def read_session(path):
    """세션 파일 읽기 (상단 100줄만 — 대시보드 파싱용)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 100:
                    break
                lines.append(line)
            return "".join(lines)
    except Exception:
        return None


def parse_gate_status(content):
    """
    대시보드에서 현재 Gate 상태 파싱.
    Returns: (gate_letter, status_emoji, description)

    실 CURRENT_SESSION.md는 표 포맷(`| 현재 Gate | **A (승인 대기)** |`,
    `| Gate 진행 | A✅ → B✅ → C⏸ → ... |`)을 쓴다. 구 헤더 포맷
    (`> **현재 Gate**: ⏸A`, `**Gate 진행**| ✅A → ...`)도 하위호환 유지.
    """
    # 패턴 1 (구·하위호환): > **현재 Gate**: ⏸A — 승인 대기
    m = re.search(
        r'\*\*현재 Gate\*\*:\s*(✅|⏸|☐)?\s*([A-E])\s*[\-—]?\s*(.*?)$',
        content,
        re.MULTILINE,
    )
    if m:
        return m.group(2), m.group(1) or "", m.group(3).strip()

    # 패턴 2 (신·정본): 표 셀 | 현재 Gate | **A (승인 대기)** | / | **✅E 완료** |
    m = re.search(
        r'현재 Gate\s*\|\s*\*{0,2}\s*(✅|⏸|☐)?\s*([A-E])\s*([^|*]*?)\s*\*{0,2}\s*\|',
        content,
    )
    if m:
        emoji = m.group(1) or ""
        letter = m.group(2)
        desc = m.group(3).strip()
        if not emoji and "대기" in desc:
            emoji = "⏸"
        return letter, emoji, desc

    # 패턴 3 (신·정본): 표 행 | Gate 진행 | A✅ → B✅ → C⏸ → D☐ → E☐ |
    #   글자→이모지(A✅)·구 이모지→글자(✅A) 모두 허용. ⏸=현재, 없으면 마지막 ✅.
    m = re.search(r'Gate 진행\s*\*{0,2}\s*\|\s*(.+?)\s*\|', content)
    if m:
        progress = m.group(1)
        paused = re.search(r'([A-E])\s*⏸|⏸\s*([A-E])', progress)
        if paused:
            return (paused.group(1) or paused.group(2)), "⏸", "대기"
        done = re.findall(r'([A-E])\s*✅|✅\s*([A-E])', progress)
        if done:
            return (done[-1][0] or done[-1][1]), "✅", "완료"

    # 패턴 4 (폴백): > **현재 상태**: A (승인 대기) / ✅E 완료
    m = re.search(
        r'\*\*현재 상태\*\*:\s*(✅|⏸|☐)?\s*([A-E])\s*([^\n]*)',
        content,
    )
    if m:
        emoji = m.group(1) or ""
        letter = m.group(2)
        desc = m.group(3).strip()
        if not emoji and "대기" in desc:
            emoji = "⏸"
        return letter, emoji, desc

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
    Gate D(검증) 또는 Gate C 완료(✅) 이후에만 허용.
    """
    gate, emoji, _ = parse_gate_status(content)
    if gate is None:
        return False
    # Gate D, E: 허용
    if gate in ("D", "E"):
        return False
    # Gate C 완료: 허용 (D 진입 직전)
    if gate == "C" and emoji == "✅":
        return False
    # Gate A, B, ⏸C: 차단
    if gate in ("A", "B") or (gate == "C" and emoji == "⏸"):
        return True
    return False


def is_test_command(command):
    """테스트 명령인지 판별."""
    for pattern in TEST_CMD_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def is_exempt_path(file_path):
    """편집 차단 제외 경로인지 판별."""
    for pattern in EXEMPT_PATH_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def block(reason):
    """도구 호출 차단 — stderr + exit 2."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def allow():
    """도구 호출 허용 — exit 0."""
    sys.exit(0)


def main():
    # stdin JSON 파싱
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    cwd = payload.get("cwd", os.getcwd())

    # 세션 파일 탐색
    session_file = find_session_file(cwd)
    if not session_file:
        allow()

    content = read_session(session_file)
    if not content:
        allow()

    # ── Edit / Write: Gate A 미승인 시 코드 편집 차단 ──
    if tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if is_exempt_path(file_path):
            allow()
        if is_gate_a_blocked(content):
            gate, emoji, desc = parse_gate_status(content)
            block(
                f"[PROC] Gate A 승인 대기 — 코드 수정 차단\n"
                f"  대상: {file_path}\n"
                f"  상태: Gate {gate} ({emoji}{desc})\n"
                f"  조치: CURRENT_SESSION.md에서 Gate A 승인 후 재시도"
            )

    # ── Bash: Gate D 미도달 시 테스트 명령 차단 ──
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if is_test_command(command) and is_test_phase_blocked(content):
            gate, emoji, desc = parse_gate_status(content)
            block(
                f"[PROC] Gate D 미도달 — 테스트 명령 차단\n"
                f"  명령: {command}\n"
                f"  상태: Gate {gate} ({emoji}{desc})\n"
                f"  조치: Gate C(테스트 계획) 완료 후 Gate D에서 실행"
            )

    allow()


if __name__ == "__main__":
    main()
