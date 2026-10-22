#!/usr/bin/env python3
"""
test-tampering-guard.py
Stop hook (runs at the end of every response): detect test/CI changes that signal reward-hacking.

Two scopes (S2, 2026-10-22 — the guard used to see only uncommitted changes under `tests/`):
  ① uncommitted (working tree + staged): every test file by the report_facts test-path rule,
     not just `tests/`. Tampering warns, an exec CI file change blocks — as before.
  ② this session's commits: base = the last commit before the transcript's first timestamp.
     Changes committed since then are checked with the same patterns but only WARN, and the
     same findings are reported once per session (they stay in history; repeating them every
     response would only teach the user to ignore the message). Skipped without a transcript.

Patterns detected:
  A: @Disabled annotation introduced
  B: Assertion count decreased (lines removed)
  C: Mock scope reduction (marked by specific strings)
  D: CI config change — split in two (2026-09-23):
       exec files (docker-compose, workflows, Dockerfile) → block
       dependency files (package.json, build.gradle.kts, pytest.ini)
         → warn only when a declaration is removed, not on pure additions

Usage: wired on Stop (hooks.json). Manual run: `python3 test-tampering-guard.py </dev/null`

Returns:
  0 = all clear (continue)
  0 + stdout JSON = warning (reward-hacking pattern found — systemMessage for the user,
      additionalContext for Claude; exit 1 was invisible to both)
  2 = error (CI config changed, block)
"""

import hashlib
import json
import os
import sys
import subprocess
import re
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # 시험 경로 판정은 report_facts·test-write-guard 와 같은 규칙을 쓴다
    from report_facts import category as _category
except Exception:  # 단독 배포 대비 — 같은 정규식
    _TEST_RE = re.compile(
        r"(^|/)(tests?|__tests__)/|(^|/)src/test/|(^|/)test_[^/]+$|_test\.[^/]+$|\.(test|spec)\.[^/]+$")

    def _category(path):
        return "tests" if _TEST_RE.search(path) else "code"

# Windows cp949 콘솔 UnicodeEncodeError 방지 (Python 3.7+)
# stdout 기본 errors 는 strict 라 비ASCII 출력 시 exit 1 로 죽는다
# (stderr 는 backslashreplace 라 무관). 본 훅은 PreToolUse
# reward-hacking 검출기 — 크래시 = 가드 무력화.
# HARNESS-SYNC-RECONCILE-2-b (2026-08-07)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# R-4-2-b: 3단 우선순위 (① custom env → ② CLAUDE_PROJECT_DIR → ③ 폴백)
#
# 🔴 HARNESS-CROSSCHECK-FIX-1-a-5 (2026-09-24): ②에서 `.parent` 를 걷어냈다.
#    `CLAUDE_PROJECT_DIR` 은 **프로젝트 루트 자체**인데 그 부모를 기준으로 삼아,
#    `git diff` 가 정작 검사해야 할 저장소 밖(또는 상위 저장소)을 보고 있었다.
#    변조를 잡는 가드가 엉뚱한 곳을 보면 **조용히 0건**을 돌려준다 —
#    「변조 없음」과 「안 봤음」이 구분되지 않는 형태라 가장 위험하다.
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
_REPO_ROOT = (
    os.environ.get("TEST_TAMPERING_GUARD_REPO_ROOT")
    or _proj
    or os.environ.get("HARNESS_ROOT_DIR", ".")
)


def _is_git_repo(repo_root):
    """Check once whether repo_root is inside a git work tree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0


_IS_GIT_REPO = _is_git_repo(_REPO_ROOT)


def _run_git_diff(extra_args):
    """Run `git diff <extra_args>` with a returncode guard.

    Returns stdout on success. On git error (rc != 0) or timeout, prints a
    warning to **stderr** (never stdout — stdout feeds the diff parsers) and
    returns "". This removes the silent fail-open that previously masked the
    pathspec-before-option bug. When repo_root is not a git work tree at all
    (e.g. a Markdown-only workspace), fails silently — that is an expected
    environment, not a tool error worth surfacing every run.
    """
    if not _IS_GIT_REPO:
        return ""
    try:
        result = subprocess.run(
            ["git", "diff"] + extra_args,
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
    except subprocess.TimeoutExpired:
        print("⚠️  git diff timed out", file=sys.stderr)
        return ""
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        stderr_lines = result.stderr.strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else f"rc={result.returncode}"
        print(f"⚠️  git diff failed ({detail}) — args={extra_args}", file=sys.stderr)
        return ""
    return result.stdout


def _test_paths(name_only_args):
    """`git diff --name-only <args>` 결과 중 시험 파일만."""
    out = _run_git_diff(["--name-only"] + name_only_args)
    return sorted({p.strip() for p in out.splitlines()
                   if p.strip() and _category(p.strip()) == "tests"})


def get_git_diff_tests():
    """Uncommitted test diff — working tree + staged (Gate C stages edits).

    Test files are found by the shared test-path rule, not only under `tests/`
    (S2: hooks/test_*.py, *.test.ts, src/test/... used to pass unseen).
    """
    # pathspec must follow `--` (the prior `["git","diff","tests/","--unified=0"]`
    # put the pathspec before the option → git rc=128, empty stdout, A/B/C dead).
    working_paths = _test_paths([])
    staged_paths = _test_paths(["--cached"])
    working = _run_git_diff(["--unified=0", "--"] + working_paths) if working_paths else ""
    staged = _run_git_diff(["--cached", "--unified=0", "--"] + staged_paths) if staged_paths else ""
    return working + "\n" + staged


def session_base(transcript_path):
    """The last commit before this session started, or None.

    Session start = the first timestamp in the transcript. Rewritten commits (rebase/amend)
    get new committer dates and so count as this session's — that only widens the check.
    """
    if not transcript_path or not _IS_GIT_REPO:
        return None
    start = None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
                if m:
                    start = m.group(1)
                    break
    except OSError:
        return None
    if not start:
        return None
    try:
        result = subprocess.run(["git", "rev-list", "-1", f"--before={start}", "HEAD"],
                                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def session_commit_findings(base):
    """Patterns A–D over `base..HEAD` (this session's commits). Warnings only."""
    findings = []
    paths = _test_paths([base, "HEAD"])
    diff = _run_git_diff(["--unified=0", base, "HEAD", "--"] + paths) if paths else ""
    if detect_pattern_a(diff):
        findings.append(("Pattern A", "@Disabled annotation introduced"))
    has_b, count = detect_pattern_b(diff)
    if has_b:
        findings.append(("Pattern B", f"Assertion lines decreased by {count}"))
    if detect_pattern_c(diff):
        findings.append(("Pattern C", "Mock scope reduction detected (real→in-memory)"))
    for pattern in CI_EXEC_PATTERNS:
        if _run_git_diff([base, "HEAD", "--", pattern]).strip():
            findings.append(("Pattern D", f"CI config changed: {pattern}"))
    for pattern in DEP_DECL_PATTERNS:
        d = _run_git_diff([base, "HEAD", "--", pattern])
        if d.strip() and not is_add_only(d):
            findings.append(("Pattern D", f"Dependency declaration removed/rewritten: {pattern}"))
    return [(p, f"[이번 세션 커밋 {base[:7]}..HEAD] {d}") for p, d in findings]


def _state_path(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    base_dir = os.environ.get("TEST_TAMPERING_GUARD_STATE_DIR") or tempfile.gettempdir()
    return os.path.join(base_dir, f".test-tampering-guard-{safe}.seen")


def first_time_this_session(session_id, findings):
    """True when these session-commit findings were not reported yet in this session."""
    digest = hashlib.sha1(json.dumps(sorted(findings), ensure_ascii=False).encode()).hexdigest()
    path = _state_path(session_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read().strip() == digest:
                return False
    except OSError:
        pass
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(digest)
    except OSError:
        pass
    return True


# Pattern D splits into two groups (HARNESS-CROSSCHECK-FIX-1-a-3, 2026-09-23).
#
# CI_EXEC: files that decide *how tests run*. Any change here can silence a
#   failing suite, so it always blocks (exit 2) — the original behaviour.
# DEP_DECL: files that mostly declare *dependencies*. Adding a library is
#   routine work, not tampering; blocking it made the guard fire on ordinary
#   commits. These only warn, and only when the change is not purely additive.
CI_EXEC_PATTERNS = [
    "docker-compose*.yml",
    ".github/workflows/*.yml",
    "Dockerfile",
]
DEP_DECL_PATTERNS = [
    "build.gradle.kts",
    "package.json",
    "pytest.ini",
]


def _collect_diffs(patterns):
    """Return [(pattern, diff)] for patterns that have a non-empty diff."""
    diffs = []
    for pattern in patterns:
        combined = _run_git_diff(["--", pattern]) + _run_git_diff(["--cached", "--", pattern])
        if combined.strip():
            diffs.append((pattern, combined))
    return diffs


def get_git_diff_ci_config():
    """Get git diff for execution-critical CI files — working tree + staged."""
    return _collect_diffs(CI_EXEC_PATTERNS)


def get_git_diff_dep_decl():
    """Get git diff for dependency-declaration files — working tree + staged."""
    return _collect_diffs(DEP_DECL_PATTERNS)


def detect_pattern_a(diff):
    """Pattern A: @Disabled annotation introduced."""
    if re.search(r'^\+.*@Disabled', diff, re.MULTILINE):
        return True
    return False


def detect_pattern_b(diff):
    """Pattern B: Assertion count decreased."""
    # Count removed assertion lines
    removed_asserts = len(re.findall(r'^-.*assert', diff, re.MULTILINE | re.IGNORECASE))
    added_asserts = len(re.findall(r'^\+.*assert', diff, re.MULTILINE | re.IGNORECASE))

    if removed_asserts > added_asserts:
        return True, removed_asserts - added_asserts
    return False, 0


def detect_pattern_c(diff):
    """Pattern C: Mock scope reduction markers."""
    mock_markers = [
        "mock",
        "Mock",
        "InMemory",
        "Testcontainers",
        "mockito"
    ]

    removed_lines = re.findall(r'^-.*', diff, re.MULTILINE)
    for line in removed_lines:
        for marker in mock_markers:
            if marker in line and "database" in line.lower():
                return True
    return False


def is_add_only(diff):
    """True when a dependency-declaration diff only *adds* things.

    Why this is not just "no removed lines": JSON has no trailing comma, so
    appending one key rewrites the previous line too —

        -    "foo": "1.0.0"          ← rewritten only to gain a comma
        +    "foo": "1.0.0",
        +    "bar": "2.0.0"

    A line-level test therefore flags almost every honest dependency bump
    (this is exactly why the first attempt was rolled back on 2026-09-14).
    We compare *keys* instead: if every removed key also appears among the
    added keys, nothing was actually dropped.

    Falls back to the line-level answer when no key is recognisable, so
    non-JSON formats (build.gradle.kts, pytest.ini) keep their old behaviour —
    those were re-measured and never had the comma problem.
    """
    removed_lines = [l for l in diff.splitlines()
                     if l.startswith("-") and not l.startswith("---")]
    if not removed_lines:
        return True

    key_re = re.compile(r'^\s*[+-]\s*"([^"]+)"\s*:')
    removed_keys = {m.group(1) for l in removed_lines if (m := key_re.match(l))}
    if not removed_keys:
        # Nothing key-shaped was removed, yet lines disappeared → not additive.
        return False

    added_keys = {m.group(1) for l in diff.splitlines()
                  if l.startswith("+") and not l.startswith("+++")
                  and (m := key_re.match(l))}
    return removed_keys <= added_keys


def read_hook_input():
    """Stop 훅 페이로드를 읽는다. 비대화형 호출(시험·CLI)에서는 빈 dict.

    HARNESS-CROSSCHECK-FIX-1-a-5 (2026-09-24): 이 훅은 Stop 에 배선돼 있으면서
    stdin 을 전혀 읽지 않았다. 그래서 `stop_hook_active` 를 볼 수 없었고,
    차단(exit 2) 뒤 재개된 응답에서 같은 진단이 다시 걸려 **무한 반복**이 된다.
    """
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def main():
    hook_input = read_hook_input()

    # 🔴 반복 방지 — 이미 이 훅 때문에 멈췄다 재개한 응답이면 다시 막지 않는다.
    if hook_input.get("stop_hook_active"):
        return 0

    # 진행 표시는 두지 않는다 — stdout 은 결과 JSON 한 개만 담아야 파싱되고, exit 0 의
    # stderr 는 아무에게도 보이지 않는다(비저장소에서 stderr 무출력 계약도 유지).

    # Get diffs
    test_diff = get_git_diff_tests()
    ci_diffs = get_git_diff_ci_config()
    dep_diffs = get_git_diff_dep_decl()

    # A/B/C (test tampering) → warning (return 1); D (CI config) → block (return 2)
    tamper_violations = []
    ci_violations = []

    # Pattern A: @Disabled
    if detect_pattern_a(test_diff):
        tamper_violations.append(("Pattern A", "@Disabled annotation introduced"))

    # Pattern B: Assertion count decreased
    has_pattern_b, count = detect_pattern_b(test_diff)
    if has_pattern_b:
        tamper_violations.append(("Pattern B", f"Assertion lines decreased by {count}"))

    # Pattern C: Mock scope reduction
    if detect_pattern_c(test_diff):
        tamper_violations.append(("Pattern C", "Mock scope reduction detected (real→in-memory)"))

    # Pattern D (exec): CI config changed → always block
    for filename, diff in ci_diffs:
        ci_violations.append(("Pattern D", f"CI config changed: {filename}"))

    # Pattern D (deps): dependency declaration changed → warn only when a
    # declaration was actually removed. Pure additions are ordinary work.
    for filename, diff in dep_diffs:
        if not is_add_only(diff):
            tamper_violations.append(
                ("Pattern D", f"Dependency declaration removed/rewritten: {filename}"))

    # ② this session's commits — warn once per session, never block
    base = session_base(hook_input.get("transcript_path"))
    if base:
        committed = session_commit_findings(base)
        if committed and first_time_this_session(hook_input.get("session_id", ""), committed):
            tamper_violations += committed

    # Output
    if not tamper_violations and not ci_violations:
        return 0

    # 🔴 HARNESS-CROSSCHECK-FIX-1-a-5 (2026-09-24): 사유를 **stderr** 로 낸다.
    #    exit 2 로 차단할 때 Claude 에게 전달되는 것은 stderr 이고, stdout 은
    #    사용자 로그로만 남는다. 이전에는 전부 stdout 이라 **차단은 되는데 왜
    #    막혔는지는 안 보이는** 상태였다 — 막힌 쪽이 고칠 수가 없다.
    lines = ["⚠️  REWARD-HACKING PATTERNS DETECTED:", ""]
    lines += [f"  {pattern}: {desc}" for pattern, desc in tamper_violations + ci_violations]
    lines += [
        "",
        "💡 Guidance:",
        "  - Pattern A/B/C in test files: Likely reward-hacking. Revert and re-implement.",
        "  - [이번 세션 커밋]: already committed in this session — shown once; review the commit.",
        "  - Pattern D (CI config): May be legitimate if Gate A approved. Confirm intent.",
        "  - Pattern D (dependency): Adding a dependency is fine and not reported;",
        "    this fired because a declaration was removed or rewritten.",
    ]
    report = "\n".join(lines)

    # return-code contract (docstring): CI config change blocks, tampering warns.
    if ci_violations:
        print(report, file=sys.stderr)  # exit 2 — Claude 가 차단 사유로 받는다
        return 2
    # 경고는 exit 0 + JSON. 예전 exit 1 은 공식 문서상 「비차단 오류」라 사용자에겐
    # stderr 첫 줄만, Claude 에겐 아무것도 가지 않았다(2026-10-15 대조 확인).
    # systemMessage = 사용자에게 전문, additionalContext = Claude 가 되돌릴지 판단.
    # 재개된 응답은 위 stop_hook_active 검사로 다시 잡지 않는다(반복 방지).
    print(json.dumps({
        "systemMessage": report,
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": report},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    exit(main())
