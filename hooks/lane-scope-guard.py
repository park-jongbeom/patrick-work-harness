#!/usr/bin/env python3
"""자율 레인 범위 가드 — 자율 레인 세션이 계획 범위를 벗어나면 사람에게 넘긴다 (S7, 2026-10-22).

자율 레인은 사람 정지 없이 구현·검증한다(gate-a §0-Lane). 그 대신 범위를 이 훅이 결정적으로 지킨다.

켜지는 조건: 대화 기록에서 마지막 gate-a 뒤에 사용자가 「자율 레인 승인」을 썼을 때
(`gate_transcript.autonomous_approved`). 그 밖에는 아무것도 하지 않는다 — 검토 레인의 작업을
막지 않는다.

두 시점을 본다.
  ① 쓰기 전 (PreToolUse Edit|Write|MultiEdit|NotebookEdit): 대상이 보호 경로면 `ask`.
     PostToolUse 는 되돌리지 못하므로 쓰기 전에 묻는다.
  ② Gate E 진입 (PreToolUse Skill gate-e · UserPromptExpansion /gate-e): 기준 커밋부터의 실제
     변경(커밋 + 작업 트리 + 새 파일, 이름 바꾸기는 양쪽 경로)을 계획과 대조한다. 하나라도 어기면
     거부하고 `continue: false` 로 세션을 멈춘다. Bash 로 쓴 변경은 ①에 안 보이므로 여기서 잡는다.

극성: 다른 가드와 달리 **fail-closed** 다. 승인은 있는데 레인 판정을 못 읽거나, git·설정을 확인할 수
없으면 막는다. 해제 카운터(몇 번 뒤 통과)는 두지 않는다 — 안전 승격이 세 번 뒤 조용히 풀리면 안 된다.

설정은 기준 커밋의 `.claude/harness-answers.yml` 에서 읽는다(`git show`). 실행 중인 세션이 작업
트리에서 자기 정책을 풀지 못하게 하려는 것이다. 키·기본값·근거 → skills/SKILL_DETAIL.md §Lane Routing.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.abspath(
    os.environ.get("LANE_SCOPE_GUARD_BASE") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
)

#: 기본 보호 경로. `/` 가 없으면 파일 이름에, 있으면 저장소 경로에 맞춘다(SKILL_DETAIL §Lane Routing).
DEFAULT_PROTECTED = (
    # 의존성 매니페스트·잠금 파일
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "requirements*.txt",
    "pyproject.toml", "poetry.lock", "Pipfile", "Pipfile.lock", "setup.py", "setup.cfg",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile", "Gemfile.lock",
    "composer.json", "composer.lock", "pom.xml", "build.gradle", "build.gradle.kts", "*.csproj",
    # 스키마·마이그레이션
    "*/migrations/*", "*/migrate/*", "*/alembic/*", "*.sql", "schema.prisma",
    # 인증·보안
    "*/auth/*", "*/security/*",
    # CI·훅·Claude 설정·비밀
    "/.github/*", "/.gitlab-ci.yml", "Jenkinsfile", "/.circleci/*", "/.husky/*", "/.git/hooks/*",
    "/.claude/*", ".env*",
)
#: Gate 절차가 스스로 쓰는 문서 — 계획에 없어도 된다.
SESSION_DOCS = ("CURRENT_SESSION.md", "SESSION_INDEX.md", "session-dashboard.html")
DOC_PATH_KEYS = ("archive_path", "worklog_path", "learning_path", "process_evolution_path",
                 "error_topics_path", "master_plan_file", "detail_plan_file", "single_plan_file")
#: 키가 없을 때 훅이 실제로 쓰는 기본 경로 (comprehension-ledger-stale-guard · skill-usage-auto).
#: 빠뜨리면 하네스가 스스로 쓴 기록이 「계획 밖 파일」로 잡힌다(S8c 실사용에서 발견).
DOC_PATH_DEFAULTS = {"learning_path": "plans/learning", "process_evolution_path": "plans/process_evolution"}
LIMIT_DEFAULTS = {"max_files": 5, "max_lines": 200, "hard_max_lines": 400}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


class Unverifiable(Exception):
    """확인할 수 없음 — fail-closed 로 막는다."""


def git(*args):
    proc = subprocess.run(["git", "-C", BASE_DIR, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout


def _scalar(value):
    return value.split(" #", 1)[0].strip().strip("'\"")


def lane_settings(text):
    """`autonomous_lane:` 블록 → dict. 블록이 없으면 enabled=False. 숫자가 틀리면 Unverifiable."""
    out = dict(LIMIT_DEFAULTS, enabled=False, protected_paths=[])
    # 키 줄 뒤의 주석(`autonomous_lane:  # 설명`)도 정상 YAML 이다 — 못 읽으면 레인이 꺼진 것으로 보인다
    m = re.search(r"^autonomous_lane:[ \t]*(?:#[^\n]*)?\n((?:[ \t]+[^\n]*\n?|[ \t]*\n)*)", text or "", re.M)
    if not m:
        return out
    key = None
    for line in m.group(1).splitlines():
        item = re.match(r"^\s+-\s+(.+)$", line)
        if item and key == "protected_paths":
            out["protected_paths"].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"^\s+([\w-]+):\s*(.*)$", line)
        if not kv:
            continue
        key, value = kv.group(1), _scalar(kv.group(2))
        if key == "enabled":
            out["enabled"] = value.lower() == "true"
        elif key in LIMIT_DEFAULTS:
            if not value.isdigit():
                raise Unverifiable(f"autonomous_lane.{key} 가 숫자가 아님: {value}")
            out[key] = int(value)
        elif key == "protected_paths" and value.startswith("["):
            out["protected_paths"] += [_scalar(v) for v in value.strip("[]").split(",") if v.strip()]
    return out


def doc_paths(text):
    """harness-answers.yml 의 문서 경로들(저장소 상대). 저장소 밖 경로는 버린다."""
    out = []
    for key in DOC_PATH_KEYS:
        m = re.search(rf"^{key}:\s*(.+)$", text or "", re.M)
        value = _scalar(m.group(1)) if m else DOC_PATH_DEFAULTS.get(key, "")
        if not value or value.startswith("<"):
            continue
        if os.path.isabs(value):
            rel = os.path.relpath(value, BASE_DIR)
            if rel.startswith(".."):
                continue
            value = rel
        out.append(value.strip("/"))
    return out


def is_protected(path, patterns):
    name = path.rsplit("/", 1)[-1]
    for pat in patterns:
        if "/" in pat:
            full = pat if pat.startswith(("/", "*")) else "*/" + pat
            if fnmatch.fnmatch("/" + path, full):
                return True
        elif fnmatch.fnmatch(name, pat):
            return True
    return False


def existed_at(base, path):
    return git("cat-file", "-e", f"{base}:{path}")[0] == 0


def read_session():
    try:
        with open(os.path.join(BASE_DIR, "CURRENT_SESSION.md"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_plan():
    from session_dashboard_parsers import parse_lane_decision

    return parse_lane_decision(read_session())


def gate_d_recorded(content):
    """Gate D 블록에 `self-debug N회`·`FIX-B N건` 표지가 있는가 — 자율 레인도 Gate D 는 생략하지 않는다.

    대화 기록이 아니라 세션 문서로 본다. 대화 기록은 현재 턴의 최신 줄이 늦게 쓰일 수 있고, 일괄로 C→D→E 를
    한 턴에 돌면 바로 그 경우다. 표지는 error-topics 가드도 읽으므로 빠지면 그쪽도 조용히 꺼진다.
    """
    from session_dashboard_parsers import _gate_block

    block = _gate_block(content, "D")[1]
    return bool(re.search(r"self-debug\s*\d+", block) and re.search(r"FIX-B\s*\d+\s*건", block))


def answers_at(base):
    rc, text = git("show", f"{base}:.claude/harness-answers.yml")
    return text if rc == 0 else ""


def scope_violations(plan):
    """Gate E 진입 전 대조. 반환: (위반 목록, 요약 한 줄)."""
    from report_facts import category, changed_files, changed_lines

    if plan["lane"] != "자율":
        return ["레인 판정을 자율로 읽지 못함 — " + "; ".join(plan["reasons"])], ""
    base = plan["base_commit"]
    if git("rev-parse", "--git-dir")[0] != 0:
        raise Unverifiable("git 저장소가 아님")
    if git("cat-file", "-e", f"{base}^{{commit}}")[0] != 0:
        return [f"기준 커밋 {base} 이 저장소에 없음"], ""
    if git("merge-base", "--is-ancestor", base, "HEAD")[0] != 0:
        return [f"기준 커밋 {base} 이 HEAD 의 조상이 아님 — 이력이 다시 쓰였다"], ""
    answers = answers_at(base)
    cfg = lane_settings(answers)
    if not cfg["enabled"]:
        return [f"기준 커밋 {base} 의 .claude/harness-answers.yml 에 autonomous_lane.enabled: true 가 없음"], ""
    protected = DEFAULT_PROTECTED + tuple(cfg["protected_paths"])
    exempt = list(SESSION_DOCS) + doc_paths(answers)
    planned = {p.lstrip("./") if p.startswith("./") else p for p in plan["files"]}

    try:
        changes = changed_files(BASE_DIR, base, both_sides=True)
        lines = changed_lines(BASE_DIR, base)
    except Exception as e:
        raise Unverifiable(f"변경 목록을 못 읽음: {e}")

    problems, counted, modules, total_lines = [], set(), set(), 0
    for status, path in changes:
        if any(path == d or path.startswith(d + "/") for d in exempt):
            continue
        is_test = category(path) == "tests"
        if is_protected(path, protected):
            problems.append(f"보호 경로 변경: {path}")
        if is_test and status != "A" and existed_at(base, path):
            problems.append(f"기존 시험 변경: {path}")
        if path not in planned:
            problems.append(f"계획 밖 파일: {path}")
        total_lines += lines.get(path, 0)
        if not (is_test and status == "A"):
            counted.add(path)
        if not is_test:
            modules.add(path.split("/", 1)[0] if "/" in path else "(루트)")
    if len(counted) > cfg["max_files"]:
        problems.append(f"파일 {len(counted)}개 — 한도 {cfg['max_files']}개(새 시험 제외)")
    if total_lines > cfg["hard_max_lines"]:
        problems.append(f"변경 {total_lines}줄 — 상한 {cfg['hard_max_lines']}줄")
    if len(modules) > 1:
        problems.append(f"최상위 모듈 {len(modules)}개: {', '.join(sorted(modules))}")
    summary = (f"파일 {len(counted)}/{cfg['max_files']}, 줄 {total_lines}/{cfg['hard_max_lines']}, "
               f"기준 커밋 {base}")
    return problems, summary


def stop_reason(problems):
    return ("자율 레인 범위를 벗어나 Gate E 기록을 멈춥니다 — 사람 확인이 필요합니다.\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n  변경을 계획 범위로 되돌린 뒤 다시 /gate-e 를 부르거나, 새 /gate-a 로 검토 레인 계획을 세우세요.")


def on_gate_e(event):
    plan = read_plan()
    try:
        problems, summary = scope_violations(plan)
    except Unverifiable as e:
        problems, summary = [f"확인 불가 — {e}"], ""
    except Exception as e:  # 예상 못 한 실패도 막는 쪽
        problems, summary = [f"확인 불가 — {type(e).__name__}: {e}"], ""
    d_missing = "Gate D 기록 없음 — CURRENT_SESSION.md 에 `## Gate D` 블록과 `self-debug N회`·`FIX-B N건` 표지가 없다"
    has_d = gate_d_recorded(read_session())
    if not problems and has_d:
        print(json.dumps({"systemMessage": f"[레인] 자율 레인 범위 확인 통과 ({summary})"},
                         ensure_ascii=False))
        return 0
    if not problems:
        # 범위는 지켰고 Gate D 만 건너뛴 경우 — 세션을 멈추지 않고 되돌려 보낸다
        reason = (f"[레인] {d_missing}. 자율 레인도 Gate D 는 생략하지 않는다 — 먼저 /gate-d 로 시험을 돌리고 결과를 "
                  f"기록한 뒤 /gate-e 를 다시 부르세요.")
        if event == "UserPromptExpansion":
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        else:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}, ensure_ascii=False))
        return 0
    if not has_d:
        problems = problems + [d_missing]
    reason = stop_reason(problems)
    if event == "UserPromptExpansion":
        out = {"decision": "block", "reason": reason}
    else:
        out = {"continue": False, "stopReason": reason, "hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": reason}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def on_edit(tool_input):
    target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not target:
        return 0
    rel = os.path.relpath(os.path.abspath(os.path.join(BASE_DIR, target)), BASE_DIR).replace(os.sep, "/")
    if rel.startswith(".."):
        return 0
    plan = read_plan()
    base = plan["base_commit"] or "HEAD"
    try:
        extra = lane_settings(answers_at(base))["protected_paths"]
    except Unverifiable:
        extra = []
    from report_facts import category

    why = ""
    if is_protected(rel, DEFAULT_PROTECTED + tuple(extra)):
        why = "보호 경로를"
    elif category(rel) == "tests" and existed_at(base, rel):
        why = "기준 커밋에 있던 시험을"
    if not why:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": (
            f"[레인] 자율 레인에서 {why} 고치려 합니다: {rel}. 자율 레인은 이 경로를 바꾸지 않습니다 — "
            f"정말 필요하면 허용하되, Gate E 에서 범위 위반으로 멈추고 검토 레인으로 넘어갑니다."),
    }}, ensure_ascii=False))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name", "")
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if event == "UserPromptExpansion":
        target = "gate-e" if str(payload.get("command_name", "")).split(":")[-1].lstrip("/") == "gate-e" else ""
    elif event == "PreToolUse" and tool == "Skill":
        target = "gate-e" if str(tool_input.get("skill", "")).split(":")[-1] == "gate-e" else ""
    elif event == "PreToolUse" and tool in EDIT_TOOLS:
        target = "edit"
    else:
        return 0
    if not target:
        return 0

    from gate_transcript import autonomous_approved

    if not autonomous_approved(payload.get("transcript_path")):
        return 0
    return on_gate_e(event) if target == "gate-e" else on_edit(tool_input)


if __name__ == "__main__":
    sys.exit(main())
