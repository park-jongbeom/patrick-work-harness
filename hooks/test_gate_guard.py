#!/usr/bin/env python3
"""gate-guard.py 단위 테스트.

HARNESS-GATEGUARD-FIX-1 (2026-06-28): 실 CURRENT_SESSION.md 표 포맷 인식 +
리포 루트 경로 우선 회귀 잠금. 픽스처를 실 표 포맷으로 갱신, 구 헤더 포맷 1건 보존.
격리: CLAUDE_PROJECT_DIR를 임시 repo로 덮어써 실저장소 대신 픽스처를 읽게 함.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "gate-guard.py")


def run_hook(payload, session_content=None, hook_event="", at_root=True):
    """gate-guard.py를 서브프로세스 실행.

    session_content=None이면 세션 파일을 두지 않음(fail-open 검증).
    at_root=True면 리포 루트(정본)에, False면 레거시 plans/current_work/에 둔다.
    CLAUDE_PROJECT_DIR를 임시 repo로 덮어써 실저장소 격리.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "repo")
        os.makedirs(repo_dir, exist_ok=True)
        if session_content is not None:
            if at_root:
                session_path = os.path.join(repo_dir, "CURRENT_SESSION.md")
            else:
                legacy = os.path.join(tmpdir, "plans", "current_work")
                os.makedirs(legacy, exist_ok=True)
                session_path = os.path.join(legacy, "CURRENT_SESSION.md")
            with open(session_path, "w", encoding="utf-8") as f:
                f.write(session_content)

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = repo_dir  # 실저장소 대신 픽스처 격리
        if hook_event:
            env["CURSOR_HOOK_EVENT"] = hook_event
        else:
            env.pop("CURSOR_HOOK_EVENT", None)

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


# --- 실 표 포맷 픽스처 (HARNESS-GATEGUARD-FIX-1) ---

SESSION_GATE_A_PENDING = """\
# 현재 세션 상태

> **현재 상태**: A (승인 대기)

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | **A (승인 대기)** |
| Gate 진행 | A⏸ → B☐ → C☐ → D☐ → E☐ |
"""

SESSION_GATE_B_DONE = """\
# 현재 세션 상태

> **현재 상태**: C (확인 대기)

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | **C (확인 대기)** |
| Gate 진행 | A✅ → B✅ → C⏸ → D☐ → E☐ |
"""

SESSION_GATE_D_ACTIVE = """\
# 현재 세션 상태

> **현재 상태**: D (확인 대기)

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | **D (확인 대기)** |
| Gate 진행 | A✅ → B✅ → C✅ → D⏸ → E☐ |
"""

SESSION_GATE_E_DONE = """\
# 현재 세션 상태

> **현재 상태**: ✅E 완료 (2026-06-28)

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | **✅E 완료** |
| Gate 진행 | A✅ → B✅ → C✅ → D✅ → E✅ |
"""

# 구 헤더 포맷 (하위호환 검증용)
SESSION_OLD_FORMAT_A_PENDING = """\
# 현재 작업 세션 (CURRENT SESSION)

> **현재 Gate**: ⏸A — 승인 대기

| 항목 | 값 |
|------|-----|
| **Gate 진행** | ⏸A → ☐B → ☐C → ☐D → ☐E |
"""


def test_gate_a_blocks_file_edit():
    code, result = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_GATE_A_PENDING, hook_event="beforeFileEdit")
    assert code == 1, f"Expected exit 1, got {code}"
    assert result and "block" in result.get("decision", ""), f"Expected block: {result}"
    print("  PASS: Gate A ⏸ → 코드 편집 차단")


def test_gate_a_allows_docs_edit():
    code, _ = run_hook(
        {"file_path": "docs/README.md"},
        SESSION_GATE_A_PENDING, hook_event="beforeFileEdit")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate A ⏸ → 문서 편집 허용")


def test_gate_a_allows_cursor_config():
    code, _ = run_hook(
        {"file_path": ".cursor/rules/new-rule.mdc"},
        SESSION_GATE_A_PENDING, hook_event="beforeFileEdit")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate A ⏸ → .cursor/ 편집 허용")


def test_gate_e_allows_all():
    code, _ = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_GATE_E_DONE, hook_event="beforeFileEdit")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate E ✅ → 모든 편집 허용")


def test_gate_b_blocks_test_command():
    code, result = run_hook(
        {"command": "npm test"},
        SESSION_GATE_B_DONE, hook_event="beforeShellExecution")
    assert code == 1, f"Expected exit 1, got {code}"
    assert result and "block" in result.get("decision", ""), f"Expected block: {result}"
    print("  PASS: Gate ⏸C → npm test 차단")


def test_gate_b_blocks_gradle_test():
    code, result = run_hook(
        {"command": "./gradlew cleanTest test"},
        SESSION_GATE_B_DONE, hook_event="beforeShellExecution")
    assert code == 1, f"Expected exit 1, got {code}"
    print("  PASS: Gate ⏸C → gradlew test 차단")


def test_gate_d_allows_test_command():
    code, _ = run_hook(
        {"command": "npm test"},
        SESSION_GATE_D_ACTIVE, hook_event="beforeShellExecution")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate ⏸D → npm test 허용")


def test_gate_b_allows_non_test_command():
    code, _ = run_hook(
        {"command": "ls -la"},
        SESSION_GATE_B_DONE, hook_event="beforeShellExecution")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: Gate ⏸C → ls -la 허용")


def test_session_start_injects_context():
    code, result = run_hook(
        {"source": "startup"},
        SESSION_GATE_E_DONE, hook_event="sessionStart")
    assert code == 0, f"Expected exit 0, got {code}"
    assert result and "Gate" in result.get("additionalContext", ""), f"Expected context: {result}"
    print("  PASS: sessionStart → Gate 상태 주입")


def test_no_session_file_allows():
    """CURRENT_SESSION.md 없으면 허용 (fail-open)."""
    code, _ = run_hook(
        {"file_path": "src/Foo.kt"}, None, hook_event="beforeFileEdit")
    assert code == 0, f"Expected exit 0, got {code}"
    print("  PASS: 세션 파일 없음 → fail-open 허용")


def test_old_format_still_blocks():
    """구 헤더 포맷(`> **현재 Gate**: ⏸A`)도 하위호환 차단."""
    code, result = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_OLD_FORMAT_A_PENDING, hook_event="beforeFileEdit")
    assert code == 1, f"Expected exit 1, got {code}"
    print("  PASS: 구 포맷 ⏸A → 코드 편집 차단 (하위호환)")


def test_legacy_path_still_found():
    """레거시 plans/current_work/ 위치도 폴백 탐색."""
    code, _ = run_hook(
        {"file_path": "src/main/kotlin/Foo.kt"},
        SESSION_GATE_A_PENDING, hook_event="beforeFileEdit", at_root=False)
    assert code == 1, f"Expected exit 1, got {code}"
    print("  PASS: 레거시 plans/current_work/ 폴백 탐색 + 차단")


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
        test_old_format_still_blocks,
        test_legacy_path_still_found,
    ]

    print(f"gate-guard.py 테스트 ({len(tests)}건)")
    print("=" * 50)
    passed = failed = 0
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
