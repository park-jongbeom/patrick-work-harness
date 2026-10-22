"""run_all_tests.py 시험 — 건너뛴 시험을 「통과」 속에 숨기지 않는다 (2026-10-22).

왜: 깨끗한 컨테이너에는 rsync 가 없어 설치 끝에서 끝까지 시험 6건이 건너뛰어졌는데, 러너는 「449건 전건 통과」라고만
말했다. 건너뜀은 실패가 아니지만(환경 탓) 그만큼 확인하지 않았다는 뜻이라 끝줄에 수와 이유를 함께 보여야 한다.
러너는 자기 폴더의 test_*.py 를 돌리므로, 임시 폴더에 러너를 복사하고 그 옆에 시험 파일을 만들어 돌린다.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_all_tests.py")

PLAIN = '''import unittest

class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)
'''

SKIPPING = '''import unittest

class T(unittest.TestCase):
    def test_runs(self):
        self.assertTrue(True)

    @unittest.skipUnless(False, "rsync 가 없다")
    def test_needs_rsync(self):
        self.fail("돌면 안 된다")
'''


class TestSkipReporting(unittest.TestCase):

    def run_runner(self, files):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        shutil.copy(RUNNER, d)
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        proc = subprocess.run([sys.executable, os.path.join(d, "run_all_tests.py")], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=120)
        return proc.returncode, proc.stdout

    def test_no_skips_keeps_the_usual_last_line(self):
        rc, out = self.run_runner({"test_plain.py": PLAIN})
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip().splitlines()[-1], "✅ 1건 전건 통과 · 수집 누락 0")

    def test_skips_are_counted_and_explained(self):
        rc, out = self.run_runner({"test_plain.py": PLAIN, "test_skip.py": SKIPPING})
        self.assertEqual(rc, 0, out)                        # 건너뜀은 실패가 아니다
        last = out.strip().splitlines()
        self.assertNotIn("전건 통과", "\n".join(last[-3:]))
        self.assertIn("건너뜀 1건", out)
        self.assertIn("rsync 가 없다", out)
        self.assertIn("2건 통과", out)

    def test_same_reason_is_grouped_and_kept_to_one_line(self):
        long_reason = SKIPPING.replace('"rsync 가 없다"', '"네트워크 없음\\n[1/5] 설치 버전 v1\\n[2/5] 대상 /tmp/x"')
        rc, out = self.run_runner({"test_skip.py": long_reason.replace("def test_runs", "@unittest.skip('네트워크 없음\\n잡음')\n    def test_runs")})
        reasons = [l for l in out.splitlines() if l.strip().startswith("· test_skip.py")]
        self.assertEqual(len(reasons), 1, out)
        self.assertIn("(2건)", reasons[0])
        self.assertNotIn("[2/5]", out.split("건너뛴 시험")[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
