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
import os
import re
import sys

VALID_TYPES = {"feat", "fix", "refactor", "test", "docs", "chore", "style", "perf"}

# git commit -m "..." 또는 git commit -m '...' 패턴 — `-am`·`-qam` 처럼 붙여 쓴 옵션도 (2026-10-29)
COMMIT_MSG_PATTERN = re.compile(
    r"""git\s+commit\s+.*?(?<![\w-])-[a-zA-Z]*m\s+["'](.+?)["']""",
    re.DOTALL,
)

# git commit -F - <<'EOF' … EOF (표준 입력의 heredoc) — 2026-10-29 대조 검증에서 이 형식이 검사 없이 통과하는 것을 찾았다
FILE_HEREDOC_PATTERN = re.compile(
    r"""git\s+commit\s+.*?(?:-[a-zA-Z]*F\s*-|--file[=\s]-)\s*<<-?\s*['"]?(\w+)['"]?[^\n]*\n(.*?)\n\s*\1\b""",
    re.DOTALL,
)

# git commit -F <파일> / --file=<파일>
FILE_PATH_PATTERN = re.compile(r"""git\s+commit\s+.*?(?:-[a-zA-Z]*F\s*|--file[=\s])(?!-)(['"]?)([^\s'"]+)\1""")

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
    r"""git\s+commit\s+.*?(?<![\w-])-[a-zA-Z]*m\s+"\$\(cat\s+<<'?EOF'?\s*\n(.+?)\n\s*EOF""",
    re.DOTALL,
)


# `git commit` 이 명령 위치(줄 처음·&&·;·|·( 뒤)에 있을 때만 커밋으로 본다 — 파이썬 문자열·echo 인자 안의 문구는 아니다 (2026-10-29)
COMMAND_POSITION = re.compile(r"(?:^|[;&|(])[ \t]*(?:[A-Z_][A-Z0-9_]*=[^\s'\"()]*[ \t]+)*git\s+commit\b", re.M)
ANY_HEREDOC = re.compile(r"""<<-?\s*['"]?(\w+)['"]?[^\n]*\n(.*?)\n[ \t]*\1\b""", re.DOTALL)


def _drop_foreign_heredocs(command):
    """커밋이 아닌 명령(예: `python3 - <<'EOF'`)의 heredoc 본문을 지운다 — 그 안의 문구는 명령이 아니라 데이터다.
    `git commit -F - <<'EOF'` 처럼 여는 줄이 커밋인 heredoc 은 그대로 둔다."""
    out, last = [], 0
    for m in ANY_HEREDOC.finditer(command):
        line = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
        if COMMAND_POSITION.search(line):
            continue
        out.append(command[last:m.start(2)])
        last = m.end(2)
    out.append(command[last:])
    return "".join(out)


def extract_commit_message(command, cwd=None):
    """명령 위치의 `git commit` 마다 메시지를 찾는다. 첫 번째로 찾은 메시지의 첫 줄을 돌려준다."""
    command = _drop_foreign_heredocs(command)
    for m in COMMAND_POSITION.finditer(command):
        msg = _extract_from(command[m.start():].lstrip(";&|( \t\n"), cwd)
        if msg:
            return msg
    return None


def _extract_from(command, cwd=None):
    """커밋 메시지 추출 — -m "…", -m "$(cat <<EOF …)", -F - heredoc, -F <파일>. 첫 줄만 돌려준다."""
    # HEREDOC 먼저 시도
    m = HEREDOC_PATTERN.search(command)
    if m:
        # 첫 줄만 추출
        return m.group(1).strip().split("\n")[0].strip()

    m = FILE_HEREDOC_PATTERN.search(command)
    if m:
        return m.group(2).strip().split("\n")[0].strip()

    m = FILE_PATH_PATTERN.search(command)
    if m:
        path = os.path.join(cwd or os.getcwd(), os.path.expanduser(m.group(2)))
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip().split("\n")[0].strip()
        except OSError:
            return None   # 읽지 못하면 판정 불가 → 통과

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

    msg = extract_commit_message(command, payload.get("cwd"))
    error = validate_message(msg)
    if error:
        block(f"[PROC] {error}")

    allow()


if __name__ == "__main__":
    main()
