#!/usr/bin/env python3
"""
커밋 메시지 한국어 Conventional Commits 형식 검증 — Claude Code PreToolUse Hook.

프로토콜:
  - 입력: stdin JSON — { tool_name: "Bash", tool_input: { command }, cwd }
  - 차단: stderr 메시지 + exit 2
  - 허용: exit 0

검증 대상:
  - `git commit -m "..."` 명령에서 메시지 추출
  - 형식: 타입(범위): 한글 제목
  - 허용 타입: feat, fix, refactor, test, docs, chore, style, perf
"""

import json
import re
import sys

VALID_TYPES = {"feat", "fix", "refactor", "test", "docs", "chore", "style", "perf"}

# git commit -m "..." 또는 git commit -m '...' 패턴
COMMIT_MSG_PATTERN = re.compile(
    r"""git\s+commit\s+.*-m\s+["'](.+?)["']""",
    re.DOTALL,
)

# 한국어 Conventional Commit: 타입(범위): 한글제목
# Co-Authored-By 포함 멀티라인도 허용 (첫 줄만 검증)
CONVENTIONAL_PATTERN = re.compile(
    r"^(feat|fix|refactor|test|docs|chore|style|perf)"  # 타입
    r"(\([^)]+\))?"  # (범위) — 선택
    r":\s+"  # 구분자
    r"(.+)"  # 제목 (한글 포함)
)

# HEREDOC 패턴: git commit -m "$(cat <<'EOF' ... EOF )"
HEREDOC_PATTERN = re.compile(
    r"""git\s+commit\s+.*-m\s+"\$\(cat\s+<<'?EOF'?\s*\n(.+?)\n\s*EOF""",
    re.DOTALL,
)


def extract_commit_message(command):
    """커밋 메시지 추출 (일반 + HEREDOC 양쪽 지원)."""
    # HEREDOC 먼저 시도
    m = HEREDOC_PATTERN.search(command)
    if m:
        # 첫 줄만 추출
        return m.group(1).strip().split("\n")[0].strip()

    # 일반 -m "..." 패턴
    m = COMMIT_MSG_PATTERN.search(command)
    if m:
        msg = m.group(1).strip()
        # $(cat <<EOF 패턴이면 첫 줄만
        if "\n" in msg:
            return msg.split("\n")[0].strip()
        return msg

    return None


def validate_message(msg):
    """커밋 메시지 형식 검증. (유효하면 None, 무효하면 오류 메시지)"""
    if not msg:
        return None  # 메시지 추출 실패 시 통과 (오탐 방지)

    m = CONVENTIONAL_PATTERN.match(msg)
    if not m:
        return (
            f"커밋 메시지 형식 위반: '{msg}'\n"
            f"  올바른 형식: 타입(범위): 한글 제목\n"
            f"  허용 타입: {', '.join(sorted(VALID_TYPES))}\n"
            f"  예시: feat(school): 학교 임베딩 생성 엔드포인트 추가"
        )

    return None


def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def allow():
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    tool_name = payload.get("tool_name", "")
    if tool_name != "Bash":
        allow()

    command = payload.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        allow()

    msg = extract_commit_message(command)
    error = validate_message(msg)
    if error:
        block(f"[PROC] {error}")

    allow()


if __name__ == "__main__":
    main()
