#!/usr/bin/env python3
"""
test-tampering-guard.py
Gate B→C transition: Detect test file modifications that signal reward-hacking.

Patterns detected:
  A: @Disabled annotation introduced
  B: Assertion count decreased (lines removed)
  C: Mock scope reduction (marked by specific strings)
  D: CI config change (docker-compose, workflows, build files)

Usage: PreToolUse hook or manual invocation before Gate C re-run
  $ python3 test-tampering-guard.py --check-diff

Returns:
  0 = all clear (continue)
  1 = warning (reward-hacking pattern found, ask user to confirm)
  2 = error (CI config changed, block)
"""

import os
import sys
import subprocess
import re
from pathlib import Path

# R-4-2-b: 3단 우선순위 (① custom env → ② CLAUDE_PROJECT_DIR 파생 → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
_REPO_ROOT = (
    os.environ.get("TEST_TAMPERING_GUARD_REPO_ROOT")
    or (str(Path(_proj).parent) if _proj else None)
    or os.environ.get("HARNESS_ROOT_DIR", ".")
)


def _run_git_diff(extra_args):
    """Run `git diff <extra_args>` with a returncode guard.

    Returns stdout on success. On git error (rc != 0) or timeout, prints a
    warning to **stderr** (never stdout — stdout feeds the diff parsers) and
    returns "". This removes the silent fail-open that previously masked the
    pathspec-before-option bug.
    """
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


def get_git_diff_ci_config():
    """Get git diff for CI config files — working tree + staged."""
    ci_patterns = [
        "docker-compose*.yml",
        ".github/workflows/*.yml",
        "build.gradle.kts",
        "package.json",
        "pytest.ini",
        "Dockerfile"
    ]
    diffs = []
    for pattern in ci_patterns:
        combined = _run_git_diff(["--", pattern]) + _run_git_diff(["--cached", "--", pattern])
        if combined.strip():
            diffs.append((pattern, combined))
    return diffs


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


def main():
    print("🔍 Gate B→C Transition: Checking for test-tampering patterns...\n")

    # Get diffs
    test_diff = get_git_diff_tests()
    ci_diffs = get_git_diff_ci_config()

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

    # Pattern D: CI config changed
    if ci_diffs:
        for filename, diff in ci_diffs:
            ci_violations.append(("Pattern D", f"CI config changed: {filename}"))

    # Output
    if not tamper_violations and not ci_violations:
        print("✅ No test-tampering patterns detected. Safe to proceed with Gate C.\n")
        return 0

    print("⚠️  REWARD-HACKING PATTERNS DETECTED:\n")
    for pattern, desc in tamper_violations + ci_violations:
        print(f"  {pattern}: {desc}")
    print("\n💡 Guidance:")
    print("  - Pattern A/B/C in tests/: Likely reward-hacking. Revert and re-implement.")
    print("  - Pattern D (CI config): May be legitimate if Gate A approved. Confirm intent.\n")

    # return-code contract (docstring): CI config change blocks, tampering warns.
    if ci_violations:
        return 2
    return 1


if __name__ == "__main__":
    exit(main())
