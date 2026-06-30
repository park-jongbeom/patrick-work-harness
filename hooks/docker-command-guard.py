#!/usr/bin/env python3
"""
docker 오명령 결정적 차단 — Claude Code PreToolUse(Bash) Hook.

차단 대상 (2종 고정 + 1종 프로젝트 설정):
  1. `docker exec -it …`          — Claude Code 는 TTY 없음 (-it/-ti/-i+-t 금지)
  2. 프로젝트 설정: `docker_blocked_containers` 목록의 컨테이너명
     — harness-answers.yml 에 `docker_blocked_containers` 리스트로 정의
     — 미설정 시 fail-open (프로젝트 독립 동작 보장)

설정 방법 (.claude/harness-answers.yml):
  docker_blocked_containers:
    - name: "my-api-platform"     # 존재하지 않는 컨테이너명 (exec 대상 금지)
      reason: "컨테이너 부재"
    - name: "my-runtime-api"
      gradle: true                 # gradle/gradlew 명령도 차단 (JRE only 컨테이너)
      reason: "런타임 전용, Gradle 없음"

프로토콜 (claude-gate-guard.py 계승):
  - 입력: stdin JSON — { tool_name, tool_input: {command?}, cwd }
  - 차단: stderr 교정 메시지 + exit 2 (Claude 가 정본 명령으로 재시도)
  - 허용: exit 0
  - 방어 원칙: 비-Bash·비-docker·정본 명령·파싱 실패·예외는 무조건 exit 0 (오탐 차단 금지)
"""

import json
import os
import re
import sys

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ── TTY 차단 패턴 (고정, 모든 프로젝트 공통) ──
_TTY_IT = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-(?:it|ti)\b")
_TTY_I = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-i\b")
_TTY_T = re.compile(r"\bdocker\s+exec\b[^\n]*?\s-t\b")


def _find_answers_yml():
    """harness-answers.yml 경로 탐색 (CLAUDE_PROJECT_DIR → cwd)."""
    candidates = []
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        candidates.append(os.path.join(proj, ".claude", "harness-answers.yml"))
    candidates.append(os.path.join(os.getcwd(), ".claude", "harness-answers.yml"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_blocked_containers():
    """harness-answers.yml 에서 docker_blocked_containers 로드. 실패 시 빈 리스트."""
    path = _find_answers_yml()
    if not path:
        return []
    try:
        if _YAML_AVAILABLE:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            # yaml 미설치 시 간단 파싱 (리스트 항목 추출)
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = _simple_parse_blocked(raw)
        return data.get("docker_blocked_containers") or []
    except Exception:
        return []


def _simple_parse_blocked(text):
    """PyYAML 미설치 대비 간이 파서 — docker_blocked_containers 섹션만 추출."""
    result = []
    in_section = False
    current = {}
    for line in text.splitlines():
        if re.match(r"^docker_blocked_containers\s*:", line):
            in_section = True
            continue
        if in_section:
            if re.match(r"^\S", line) and not line.strip().startswith("-"):
                break
            m_name = re.match(r"^\s+-\s+name\s*:\s*[\"']?(.+?)[\"']?\s*$", line)
            m_reason = re.match(r"^\s+reason\s*:\s*[\"']?(.+?)[\"']?\s*$", line)
            m_gradle = re.match(r"^\s+gradle\s*:\s*(true|false)\s*$", line)
            m_new = re.match(r"^\s+-\s+name\s*:", line)
            if m_new and current:
                result.append(current)
                current = {}
            if m_name:
                if current:
                    result.append(current)
                current = {"name": m_name.group(1).strip()}
            elif m_reason and current:
                current["reason"] = m_reason.group(1).strip()
            elif m_gradle and current:
                current["gradle"] = m_gradle.group(1) == "true"
    if current:
        result.append(current)
    return {"docker_blocked_containers": result}


def _build_container_patterns(containers):
    """blocked_containers 설정에서 regex 패턴 목록 생성."""
    patterns = []
    for entry in containers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "").strip()
        if not name:
            continue
        reason = entry.get("reason", f"컨테이너 '{name}' 설정 차단")
        gradle_only = entry.get("gradle", False)
        escaped = re.escape(name)
        if gradle_only:
            pat = re.compile(
                r"\bdocker\s+exec\b[^\n]*\b" + escaped + r"\b[^\n]*\bgradlew?\b"
            )
        else:
            pat = re.compile(
                r"\bdocker\s+exec\b(?:\s+\S+)*?\s+" + escaped + r"\b"
            )
        patterns.append((pat, reason))
    return patterns


def allow():
    sys.exit(0)


def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def has_tty_flag(cmd):
    if _TTY_IT.search(cmd):
        return True
    return bool(_TTY_I.search(cmd) and _TTY_T.search(cmd))


def violation(cmd, container_patterns):
    """차단 사유 문자열 반환, 위반 없으면 None."""
    if "docker" not in cmd:
        return None
    if has_tty_flag(cmd):
        return "docker exec 에 -it/TTY 플래그 — Claude Code 는 TTY 없음."
    for pat, reason in container_patterns:
        if pat.search(cmd):
            return reason
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

    container_patterns = _build_container_patterns(_load_blocked_containers())
    reason = violation(command, container_patterns)
    if reason is None:
        allow()

    canon = (
        "  정본 명령은 .claude/harness-answers.yml → docker_blocked_containers 설정을 확인하고\n"
        "  CLAUDE.md §Build·Test 의 canonical 명령을 사용하세요.\n"
        "  ※ TTY 금지(-it) · 호스트 직접 실행 금지"
    )
    block(
        f"[DOCKER-GUARD] 틀린 docker 명령 차단\n"
        f"  사유: {reason}\n"
        f"  명령: {command}\n"
        f"{canon}"
    )


if __name__ == "__main__":
    main()
