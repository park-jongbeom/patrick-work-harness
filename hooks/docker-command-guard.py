#!/usr/bin/env python3
"""
docker 오명령 결정적 차단 — Claude Code PreToolUse(Bash) Hook.

HARNESS-REVIEW-2 (2026-06-21): CLAUDE.md 다이어트 — 「결정적 규칙 → 훅」 전환.
CLAUDE.md §Build·Test의 docker 주의사항(prose)을 기계 강제로 이관한다.
규칙 정본·정본 명령 표 → CLAUDE.md §Build·Test / CLAUDE_DETAIL.md §Docker Execution Commands.

프로토콜 (claude-gate-guard.py 계승):
  - 입력: stdin JSON — { tool_name, tool_input: {command?}, cwd }
  - 차단: stderr 교정 메시지 + exit 2 (Claude 가 정본 명령으로 재시도)
  - 허용: exit 0
  - 방어 원칙: 비-Bash·비-docker·정본 명령·파싱 실패·예외는 무조건 exit 0 (오탐 차단 금지)

차단 대상 (3종, CLAUDE.md L79-85):
  1. `docker exec -it …`            — Claude Code 는 TTY 없음 (-it/-ti/-i+-t 금지)
  2. `docker exec … ga-api-platform …` — 컨테이너명 부재
  3. `docker exec … ga-matching-api … gradlew/gradle …` — JRE only, Gradle 없음
"""

import json
import re
import sys

# ── 차단 패턴 ──
# 1) TTY 플래그: docker exec 에 -it / -ti / (-i 와 -t 동시)
_TTY_IT = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-(?:it|ti)\b")
_TTY_I = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-i\b")
_TTY_T = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-t\b")
# 2) 부재 컨테이너 ga-api-platform (exec 뒤 플래그·플래그값 토큰 허용 후 컨테이너명)
#    `\s+ga-api-platform` 으로 공백 직후(컨테이너 위치)만 매칭 → `/ga-api-platform` 경로 오탐 회피
_WRONG_GA_API = re.compile(r"\bdocker\s+exec\b(?:\s+\S+)*?\s+ga-api-platform\b")
# 3) ga-matching-api + gradle (런타임 컨테이너에 Gradle 명령)
_WRONG_MATCHING_GRADLE = re.compile(
    r"\bdocker\s+exec\b[^\n]*\bga-matching-api\b[^\n]*\bgradlew?\b"
)

# 정본 명령 안내 (교정 메시지)
_CANON = (
    "  정본 명령 (CLAUDE.md §Build·Test):\n"
    "    - react-web-ga      : docker exec react-web-ga npm test -- --run\n"
    "    - college-crawler   : docker exec college-crawler-local pytest tests/\n"
    "    - ga-api-platform   : sg docker -c \"docker compose -f "
    "/media/ubuntu/data120g/ga-api-platform/docker-compose-test.yml run --rm ga-test\"\n"
    "  ※ TTY 금지(-it) · 호스트 직접 실행 금지 · 권한 오류 시 sg docker -c \"...\" 우회"
)


def allow():
    sys.exit(0)


def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def has_tty_flag(cmd):
    if _TTY_IT.search(cmd):
        return True
    return bool(_TTY_I.search(cmd) and _TTY_T.search(cmd))


def violation(cmd):
    """차단 사유 문자열 반환, 위반 없으면 None."""
    if "docker" not in cmd:
        return None
    if has_tty_flag(cmd):
        return "docker exec 에 -it/TTY 플래그 — Claude Code 는 TTY 없음."
    if _WRONG_GA_API.search(cmd):
        return "컨테이너명 'ga-api-platform' 부재 — 존재하지 않는 컨테이너."
    if _WRONG_MATCHING_GRADLE.search(cmd):
        return "'ga-matching-api' 는 런타임 전용(JRE only)·Gradle 없음 — gradlew 실행 불가."
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    if payload.get("tool_name") != "Bash":
        allow()

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        allow()

    reason = violation(command)
    if reason is None:
        allow()

    block(
        f"[DOCKER-GUARD] 틀린 docker 명령 차단\n"
        f"  사유: {reason}\n"
        f"  명령: {command}\n"
        f"{_CANON}"
    )


if __name__ == "__main__":
    main()
