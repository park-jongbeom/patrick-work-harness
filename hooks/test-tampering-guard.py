#!/usr/bin/env python3
"""
test-tampering-guard.py
Gate B→C transition: Detect test file modifications that signal reward-hacking.

Patterns detected:
  A: @Disabled annotation introduced
  B: Assertion count decreased (lines removed)
  C: Mock scope reduction (marked by specific strings)
  D: CI config change — split in two (2026-09-23):
       exec files (docker-compose, workflows, Dockerfile) → block
       dependency files (package.json, build.gradle.kts, pytest.ini)
         → warn only when a declaration is removed, not on pure additions

Usage: PreToolUse hook or manual invocation before Gate C re-run
  $ python3 test-tampering-guard.py --check-diff

Returns:
  0 = all clear (continue)
  1 = warning (reward-hacking pattern found, ask user to confirm)
  2 = error (CI config changed, block)
"""

import json
import os
import sys
import subprocess
import re

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


def get_git_diff_tests():
    """Get git diff for tests/ — working tree + staged (Gate C stages edits)."""
    # pathspec must follow `--` (the prior `["git","diff","tests/","--unified=0"]`
    # put the pathspec before the option → git rc=128, empty stdout, A/B/C dead).
    working = _run_git_diff(["--unified=0", "--", "tests/"])
    staged = _run_git_diff(["--cached", "--unified=0", "--", "tests/"])
    return working + "\n" + staged


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

    print("🔍 Gate B→C Transition: Checking for test-tampering patterns...\n")

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

    # Output
    if not tamper_violations and not ci_violations:
        print("✅ No test-tampering patterns detected. Safe to proceed with Gate C.\n")
        return 0

    # 🔴 HARNESS-CROSSCHECK-FIX-1-a-5 (2026-09-24): 사유를 **stderr** 로 낸다.
    #    exit 2 로 차단할 때 Claude 에게 전달되는 것은 stderr 이고, stdout 은
    #    사용자 로그로만 남는다. 이전에는 전부 stdout 이라 **차단은 되는데 왜
    #    막혔는지는 안 보이는** 상태였다 — 막힌 쪽이 고칠 수가 없다.
    out = sys.stderr
    print("⚠️  REWARD-HACKING PATTERNS DETECTED:\n", file=out)
    for pattern, desc in tamper_violations + ci_violations:
        print(f"  {pattern}: {desc}", file=out)
    print("\n💡 Guidance:", file=out)
    print("  - Pattern A/B/C in tests/: Likely reward-hacking. Revert and re-implement.", file=out)
    print("  - Pattern D (CI config): May be legitimate if Gate A approved. Confirm intent.", file=out)
    print("  - Pattern D (dependency): Adding a dependency is fine and not reported;", file=out)
    print("    this fired because a declaration was removed or rewritten.\n", file=out)

    # return-code contract (docstring): CI config change blocks, tampering warns.
    if ci_violations:
        return 2
    return 1


if __name__ == "__main__":
    exit(main())
