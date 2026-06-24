#!/usr/bin/env python3
"""gate-guard.py 단위 테스트."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "gate-guard.py")


def run_hook(payload, session_content, hook_event=""):
    """gate-guard.py를 서브프로세스로 실행, 결과 반환."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # CURRENT_SESSION.md 생성
        plans_dir = os.path.join(tmpdir, "plans", "current_work")
        os.makedirs(plans_dir, exist_ok=True)
        session_path = os.path.join(plans_dir, "CURRENT_SESSION.md")
        with open(session_path, "w", encoding="utf-8") as f:
            f.write(session_content)

        # 리포 시뮬레이션 (cwd = tmpdir/repo)
        repo_dir = os.path.join(tmpdir, "repo")
        os.makedirs(repo_dir, exist_ok=True)

        env = os.environ.copy()
        if hook_event:
            env["CURSOR_HOOK_EVENT"] = hook_event

        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=env,
        )
        stdout = proc.stdout.strip()
        result = None
        if stdout:
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"raw": stdout}
        return proc.returncode, result


# --- 테스트 세션 콘텐츠 ---

SESSION_GATE_A_PENDING = """\
# 현재 작업 세션 (CURRENT SESSION)

> **현재 Gate**: ⏸A — 승인 대기

| 항목 | 값 |
|------|-----|
| **Gate 진행** | ⏸A → ☐B → ☐C → ☐D → ☐E |
"""

SESSION_GATE_B_DONE = """\
# 현재 작업 세션 (CURRENT SESSION)

> **현재 Gate**: ⏸C — 테스트 계획 대기

| 항목 | 값 |
|------|-----|
| **Gate 진행** | ✅A → ✅B → ⏸C → ☐D → ☐E |
"""

SESSION_GATE_D_ACTIVE = """\
# 현재 작업 세션 (CURRENT SESSION)

> **현재 Gate**: ⏸D — 검증 실행 대기

| 항목 | 값 |
|------|-----|
| **Gate 진행** | ✅A → ✅B → ✅C → ⏸D → ☐E |
"""

SESSION_GATE_E_DONE = """\
# 현재 작업 세션 (CURRENT SESSION)

> **현재 Gate**: ✅E (세션 완료)

| 항목 | 값 |
|------|-----|
| **Gate 진행** | ✅A → ✅B → ✅C → ✅D → ✅E |
"""


def test_gate_a_blocks_file_edit():
    """Gate A ⏸ 상태에서 코드 편집 차단."""
    code, result = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_GATE_A_PENDING,
        hook_event="beforeFileEdit",
    )
    assert code == 1, f"Expected exit 1, got {code}"
    assert result and "block" in result.get("decision", ""), f"Expected block: {result}"
    print("  PASS: Gate A ⏸ → 코드 편집 차단")


def test_gate_a_allows_docs_edit():
    """Gate A ⏸이어도 문서(.md) 편집은 허용."""
    code, _ = run_hook(
        {"file_path": "docs/README.md"},
        SESSION_GATE_A_PENDING,
        hook_event="beforeFileEdit",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate A ⏸ → 문서 편집 허용")


def test_gate_a_allows_cursor_config():
    """Gate A ⏸이어도 .cursor/ 설정 편집은 허용."""
    code, _ = run_hook(
        {"file_path": ".cursor/rules/new-rule.mdc"},
        SESSION_GATE_A_PENDING,
        hook_event="beforeFileEdit",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate A ⏸ → .cursor/ 편집 허용")


def test_gate_e_allows_all():
    """Gate E ✅ 상태에서 모든 편집 허용."""
    code, _ = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_GATE_E_DONE,
        hook_event="beforeFileEdit",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate E ✅ → 모든 편집 허용")


def test_gate_b_blocks_test_command():
    """Gate B 완료(⏸C) 상태에서 테스트 명령 차단."""
    code, result = run_hook(
        {"command": "npm test"},
        SESSION_GATE_B_DONE,
        hook_event="beforeShellExecution",
    )
    assert code == 1, f"Expected exit 1, got {code}"
    assert result and "block" in result.get("decision", ""), f"Expected block: {result}"
    print("  PASS: Gate ⏸C → npm test 차단")


def test_gate_b_blocks_gradle_test():
    """Gate B 완료(⏸C) 상태에서 gradlew test 차단."""
    code, result = run_hook(
        {"command": "./gradlew cleanTest test"},
        SESSION_GATE_B_DONE,
        hook_event="beforeShellExecution",
    )
    assert code == 1, f"Expected exit 1, got {code}"
    print("  PASS: Gate ⏸C → gradlew test 차단")


def test_gate_d_allows_test_command():
    """Gate D ⏸ 상태에서 테스트 명령 허용."""
    code, _ = run_hook(
        {"command": "npm test"},
        SESSION_GATE_D_ACTIVE,
        hook_event="beforeShellExecution",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate ⏸D → npm test 허용")


def test_gate_b_allows_non_test_command():
    """Gate B 완료(⏸C) 상태에서 비-테스트 명령은 허용."""
    code, _ = run_hook(
        {"command": "ls -la"},
        SESSION_GATE_B_DONE,
        hook_event="beforeShellExecution",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate ⏸C → ls -la 허용")


def test_session_start_injects_context():
    """sessionStart에서 Gate 상태 컨텍스트 주입."""
    code, result = run_hook(
        {"source": "startup"},
        SESSION_GATE_E_DONE,
        hook_event="sessionStart",
    )
    assert code == 0, f"Expected exit 0, got {code}"
    assert result and "Gate" in result.get("additionalContext", ""), f"Expected context: {result}"
    print("  PASS: sessionStart → Gate 상태 주입")


def test_no_session_file_allows():
    """CURRENT_SESSION.md 없으면 허용 (fail-open)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["CURSOR_HOOK_EVENT"] = "beforeFileEdit"
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps({"file_path": "src/Foo.kt"}),
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env=env,
        )
        assert proc.returncode == 0, f"Expected exit 0, got {proc.returncode}"
    print("  PASS: 세션 파일 없음 → fail-open 허용")


if __name__ == "__main__":
    tests = [
        test_gate_a_blocks_file_edit,
        test_gate_a_allows_docs_edit,
        test_gate_a_allows_cursor_config,
        test_gate_e_allows_all,
        test_gate_b_blocks_test_command,
        test_gate_b_blocks_gradle_test,
        test_gate_d_allows_test_command,
        test_gate_b_allows_non_test_command,
        test_session_start_injects_context,
        test_no_session_file_allows,
    ]

    print(f"gate-guard.py 테스트 ({len(tests)}건)")
    print("=" * 50)

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__} — {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__} — {e}")
            failed += 1

    print("=" * 50)
    print(f"결과: {passed} passed, {failed} failed / {len(tests)} total")
    sys.exit(1 if failed else 0)
