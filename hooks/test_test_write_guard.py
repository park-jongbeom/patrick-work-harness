"""test-write-guard.py 시험 — Gate D 중 시험 파일 쓰기는 ask, 그 밖은 통과."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-write-guard.py")


def session(status):
    return f"# 현재 세션 상태\n\n> **세션 ID**: S-1\n> **현재 상태**: {status}\n\n| 항목 | 내용 |\n|---|---|\n| 현재 Gate | {status} |\n"


def run_hook(tool, path, status=None, raw=None):
    with tempfile.TemporaryDirectory() as base:
        if status is not None:
            with open(os.path.join(base, "CURRENT_SESSION.md"), "w", encoding="utf-8") as f:
                f.write(session(status))
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
                   "tool_input": {"file_path": os.path.join(base, path) if path else ""}}
        proc = subprocess.run(
            [sys.executable, SCRIPT], input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "TEST_WRITE_GUARD_BASE": base, "PYTHONIOENCODING": "utf-8"},
        )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


class TestTestWriteGuard(unittest.TestCase):

    def test_gate_d_test_file_asks(self):
        for path in ("tests/test_x.py", "src/test/kotlin/AT.kt", "web/a.spec.ts", "hooks/test_guard.py"):
            rc, out = run_hook("Edit", path, "D (확인 대기)")
            self.assertEqual(rc, 0)
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", path)
            self.assertIn("명세와 시험이 실제로 충돌", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_write_and_multiedit_also_covered(self):
        for tool in ("Write", "MultiEdit"):
            _, out = run_hook(tool, "tests/test_x.py", "D (진행 중)")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_other_gates_pass(self):
        for status in ("C (확인 대기)", "A (승인 대기)", "✅E 완료 (2026-10-15)"):
            self.assertEqual(run_hook("Edit", "tests/test_x.py", status), (0, None), status)

    def test_non_test_files_pass_in_gate_d(self):
        for path in ("hooks/guard.py", "README.md", "skills/gate-d/SKILL.md"):
            self.assertEqual(run_hook("Edit", path, "D (확인 대기)"), (0, None), path)

    def test_fail_open(self):
        self.assertEqual(run_hook("Edit", "tests/test_x.py", None), (0, None))   # 문서 없음
        self.assertEqual(run_hook("Bash", "tests/test_x.py", "D"), (0, None))    # 다른 도구
        self.assertEqual(run_hook("Edit", "", "D", raw="{oops"), (0, None))      # 깨진 입력


if __name__ == "__main__":
    unittest.main(verbosity=2)
