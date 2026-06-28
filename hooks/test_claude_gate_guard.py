#!/usr/bin/env python3
"""claude-gate-guard.py 단위 테스트 (HARNESS-GATEGUARD-FIX-1, 2026-06-28).

라이브 Claude Code PreToolUse 훅 — Gate A 미승인 코드편집·Gate<D 테스트명령을 exit 2로 차단.
실 CURRENT_SESSION.md 표 포맷 인식 + 리포 루트 경로 우선 회귀 잠금.
프로토콜: stdin JSON {tool_name, tool_input, cwd} → 차단 exit 2 / 허용 exit 0.
격리: CLAUDE_PROJECT_DIR를 임시 repo로 덮어써 실저장소 대신 픽스처를 읽게 함.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "claude-gate-guard.py")

SESSION_GATE_A_PENDING = """\
# 현재 세션 상태

> **현재 상태**: A (승인 대기)

| 항목 | 값 |
|------|-----|
| 현재 Gate | **A (승인 대기)** |
| Gate 진행 | A⏸ → B☐ → C☐ → D☐ → E☐ |
"""

SESSION_GATE_C_PENDING = """\
# 현재 세션 상태

> **현재 상태**: C (확인 대기)

| 항목 | 값 |
|------|-----|
| 현재 Gate | **C (확인 대기)** |
| Gate 진행 | A✅ → B✅ → C⏸ → D☐ → E☐ |
"""

SESSION_GATE_D_ACTIVE = """\
# 현재 세션 상태

> **현재 상태**: D (확인 대기)

| 항목 | 값 |
|------|-----|
| 현재 Gate | **D (확인 대기)** |
| Gate 진행 | A✅ → B✅ → C✅ → D⏸ → E☐ |
"""

SESSION_GATE_E_DONE = """\
# 현재 세션 상태

> **현재 상태**: ✅E 완료 (2026-06-28)

| 항목 | 값 |
|------|-----|
| 현재 Gate | **✅E 완료** |
| Gate 진행 | A✅ → B✅ → C✅ → D✅ → E✅ |
"""

# ✅E 세션인데 본문에 Gate A 블록 텍스트가 남은 경우(doc-cleanup 전) — 비차단이어야 함
# (is_gate_a_blocked 폴백 정규식 `Gate\\s*A.*승인\\s*대기` 본문 오탐 회귀 잠금)
SESSION_GATE_E_WITH_GATEA_BODY = """\
# 현재 세션 상태

> **현재 상태**: ✅E 완료 (2026-06-28)

| 항목 | 값 |
|------|-----|
| 현재 Gate | **✅E 완료** |
| Gate 진행 | A✅ → B✅ → C✅ → D✅ → E✅ |

## Gate A 계획 (승인 대기)

- 완료 세션 본문에 남은 Gate A 블록 텍스트 (슬림화 전)
"""


def run_hook(payload, session_content=None, at_root=True):
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "repo")
        os.makedirs(repo_dir, exist_ok=True)
        if session_content is not None:
            if at_root:
                path = os.path.join(repo_dir, "CURRENT_SESSION.md")
            else:
                legacy = os.path.join(tmpdir, "plans", "current_work")
                os.makedirs(legacy, exist_ok=True)
                path = os.path.join(legacy, "CURRENT_SESSION.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(session_content)
        payload.setdefault("cwd", repo_dir)
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = repo_dir  # 실저장소 대신 픽스처 격리
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True, text=True, cwd=repo_dir, env=env,
        )
        return proc.returncode, proc.stderr.strip()


def _edit(file_path, session, at_root=True):
    return run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": file_path}}, session, at_root)


def _bash(command, session):
    return run_hook(
        {"tool_name": "Bash", "tool_input": {"command": command}}, session)


# ── Gate A 미승인 코드편집 차단 (exit 2) ──
def test_gate_a_blocks_code_edit():
    rc, err = _edit("src/Main.kt", SESSION_GATE_A_PENDING)
    assert rc == 2, f"expected 2 got {rc}"
    assert "PROC" in err, err
    print("  PASS: Gate A ⏸ + 코드편집 → exit 2")


def test_gate_a_allows_md_edit():
    rc, _ = _edit("docs/README.md", SESSION_GATE_A_PENDING)
    assert rc == 0, f"expected 0 got {rc}"
    print("  PASS: Gate A ⏸ + .md(면제) → exit 0")


def test_gate_a_allows_claude_dir():
    rc, _ = _edit(".claude/skills/x/SKILL.md", SESSION_GATE_A_PENDING)
    assert rc == 0, f"expected 0 got {rc}"
    print("  PASS: Gate A ⏸ + .claude/(면제) → exit 0")


def test_gate_e_allows_code_edit():
    rc, _ = _edit("src/Main.kt", SESSION_GATE_E_DONE)
    assert rc == 0, f"expected 0 got {rc}"
    print("  PASS: ✅E + 코드편집 → exit 0")


# ── Gate<D 테스트명령 차단 (exit 2) ──
def test_gate_c_blocks_test_cmd():
    rc, err = _bash("docker exec react-web-ga npm test", SESSION_GATE_C_PENDING)
    assert rc == 2, f"expected 2 got {rc}"
    print("  PASS: ⏸C + npm test → exit 2")


def test_gate_d_allows_test_cmd():
    rc, _ = _bash("pytest tests/", SESSION_GATE_D_ACTIVE)
    assert rc == 0, f"expected 0 got {rc}"
    print("  PASS: ⏸D + pytest → exit 0")


def test_gate_a_allows_non_test_bash():
    rc, _ = _bash("ls -la", SESSION_GATE_A_PENDING)
    assert rc == 0, f"expected 0 got {rc}"
    print("  PASS: Gate A + 비테스트 명령 → exit 0")


# ── 경로 해소 ──
def test_repo_root_path_resolved():
    """리포 루트 CURRENT_SESSION.md(정본 위치)를 정확히 탐색 → 차단."""
    rc, _ = _edit("src/Main.kt", SESSION_GATE_A_PENDING, at_root=True)
    assert rc == 2, f"리포 루트 미탐색 의심: got {rc}"
    print("  PASS: 리포 루트 경로 탐색 + 차단")


def test_legacy_path_resolved():
    """레거시 plans/current_work/ 위치도 폴백 탐색 → 차단."""
    rc, _ = _edit("src/Main.kt", SESSION_GATE_A_PENDING, at_root=False)
    assert rc == 2, f"레거시 경로 폴백 실패: got {rc}"
    print("  PASS: 레거시 plans/current_work/ 폴백 + 차단")


def test_no_block_when_unresolved():
    """세션 파일 미배치 시 차단하지 않음(fail-open). 실저장소 격리하에 허용."""
    rc, _ = run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": "src/Main.kt"}}, None)
    assert rc == 0, f"fail-open 기대 0 got {rc}"
    print("  PASS: 세션 파일 부재 → fail-open exit 0")


def test_done_session_with_gate_a_body_not_blocked():
    """✅E 세션 본문에 'Gate A … 승인 대기' 텍스트가 남아도 비면제 편집 비차단(폴백 오탐 회귀)."""
    rc, _ = _edit("src/Main.kt", SESSION_GATE_E_WITH_GATEA_BODY)
    assert rc == 0, f"✅E인데 Gate A 본문 텍스트로 오차단: got {rc}"
    print("  PASS: ✅E + Gate A 본문 텍스트 → 비차단(exit 0)")


if __name__ == "__main__":
    tests = [
        test_gate_a_blocks_code_edit,
        test_gate_a_allows_md_edit,
        test_gate_a_allows_claude_dir,
        test_gate_e_allows_code_edit,
        test_done_session_with_gate_a_body_not_blocked,
        test_gate_c_blocks_test_cmd,
        test_gate_d_allows_test_cmd,
        test_gate_a_allows_non_test_bash,
        test_repo_root_path_resolved,
        test_legacy_path_resolved,
        test_no_block_when_unresolved,
    ]
    print(f"claude-gate-guard.py 테스트 ({len(tests)}건)")
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
