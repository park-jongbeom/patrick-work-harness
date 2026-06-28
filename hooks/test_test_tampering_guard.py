#!/usr/bin/env python3
"""test-tampering-guard.py 단위 테스트.

reward-hacking 검출기 회귀 잠금 (HARNESS-TAMPER-FIX-1, 2026-06-28):
  - tests/ 변조(@Disabled·assert 감소·mock+database 제거) → exit 1 (warning)
  - CI config 변경(docker-compose 등) → exit 2 (block)
  - 무변경 → exit 0
  - staged(--cached) 변조도 검출 / git diff 인자순서 회귀 방지

pytest 부재 환경 대비 unittest.TestCase 기반 — `python3 test_test_tampering_guard.py -v` 로 실행.
임시 git repo 픽스처 + TEST_TAMPERING_GUARD_REPO_ROOT 격리(실저장소 무영향).
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = os.path.join(os.path.dirname(__file__), "test-tampering-guard.py")

BASE_FOO = (
    "class FooTest {\n"
    "  void a() { assertEquals(1, x); }\n"
    "  void b() { assertEquals(2, y); }\n"
    "  void c() { assertTrue(z); }\n"
    "}\n"
)


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def run_hook(repo):
    """훅을 서브프로세스로 실행, (returncode, stdout, stderr) 반환."""
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        cwd=repo,
        env={**os.environ, "TEST_TAMPERING_GUARD_REPO_ROOT": repo},
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestTamperingGuard(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="ttg-")
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t.t")
        _git(self.repo, "config", "user.name", "t")
        (Path(self.repo) / "tests").mkdir()
        self._write("tests/FooTest.java", BASE_FOO)
        self._write("docker-compose.yml", "services:\n  app:\n    image: a\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _write(self, rel, content):
        (Path(self.repo) / rel).write_text(content)

    # ── 무변경 → 0 ──
    def test_clean_returns_0(self):
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 0, out)

    # ── Pattern A: @Disabled → 1 ──
    def test_pattern_a_disabled(self):
        self._write("tests/FooTest.java", BASE_FOO.replace(
            "  void a()", "  @Disabled\n  void a()"))
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 1, out)
        self.assertIn("Pattern A", out)

    # ── Pattern B: assert 라인 감소 → 1 ──
    def test_pattern_b_assert_decrease(self):
        self._write("tests/FooTest.java",
                    "class FooTest {\n  void a() {  }\n  void b() {  }\n  void c() {  }\n}\n")
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 1, out)
        self.assertIn("Pattern B", out)

    # ── Pattern C: mock+database 라인 제거 → 1 ──
    def test_pattern_c_mock_reduction(self):
        self._write("tests/DbTest.java", "class DbTest { Mock database conn; }\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "add db")
        os.remove(Path(self.repo) / "tests/DbTest.java")
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 1, out)
        self.assertIn("Pattern C", out)

    # ── Pattern D: CI config 변경 → 2 (block) ──
    def test_pattern_d_ci_change_blocks(self):
        self._write("docker-compose.yml", "services:\n  app:\n    image: CHANGED\n")
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 2, out)
        self.assertIn("Pattern D", out)

    # ── D + A 동시 → D 우선(2) ──
    def test_d_takes_precedence(self):
        self._write("docker-compose.yml", "services:\n  app:\n    image: CHANGED\n")
        self._write("tests/FooTest.java", BASE_FOO.replace(
            "  void a()", "  @Disabled\n  void a()"))
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 2, out)

    # ── staged(--cached) 변조도 검출 → 1 ──
    def test_staged_tampering_detected(self):
        self._write("tests/FooTest.java", BASE_FOO.replace(
            "  void a()", "  @Disabled\n  void a()"))
        _git(self.repo, "add", "tests/FooTest.java")  # 워킹트리 clean, staged에만 존재
        rc, out, _ = run_hook(self.repo)
        self.assertEqual(rc, 1, out)
        self.assertIn("Pattern A", out)

    # ── 인자순서 회귀: tests/ 변경 시 diff 비어있지 않음 ──
    def test_arg_order_regression_nonempty_diff(self):
        os.environ["TEST_TAMPERING_GUARD_REPO_ROOT"] = self.repo
        spec = importlib.util.spec_from_file_location("ttg", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._write("tests/FooTest.java", "class FooTest {\n  void a() {  }\n}\n")
        diff = mod.get_git_diff_tests()
        self.assertTrue(diff.strip(),
                        "tests/ 변경이 있는데 diff가 비어있음 — git 인자순서 버그 회귀")


if __name__ == "__main__":
    unittest.main(verbosity=2)
