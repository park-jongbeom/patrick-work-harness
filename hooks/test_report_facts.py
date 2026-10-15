"""report_facts.py 시험 — 임시 git 저장소로 변경 파일 범주·JUnit 합계·기준 커밋 재현표를 확인한다."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "report_facts.py")
sys.path.insert(0, HERE)
import report_facts as rf  # noqa: E402

# 시험 명령: impl.py 에 FIXED 가 있으면 시험 2개가 통과, 없으면 test_new 만 실패하는 JUnit 을 쓴다
RUNNER = r'''
import os
fixed = "FIXED" in open("impl.py").read()
has_new = os.path.exists("tests/test_new.py")
cases = ['<testcase classname="t" name="test_old"/>']
if has_new:
    cases.append('<testcase classname="t" name="test_new"/>' if fixed else
                 '<testcase classname="t" name="test_new"><failure>x</failure></testcase>')
    cases.append('<testcase classname="t" name="test_guard"/>')
open("junit.xml", "w").write("<testsuite>" + "".join(cases) + "</testsuite>")
'''


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def run(repo, *args):
    p = subprocess.run([sys.executable, SCRIPT, "--repo", repo, *args], capture_output=True,
                       text=True, encoding="utf-8")
    return p.returncode, p.stdout


class TestReportFacts(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        os.makedirs(os.path.join(self.repo, "tests"))
        self._write("impl.py", "x = 1\n")
        self._write("runner.py", RUNNER)
        self._write("README.md", "# r\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()

    def _write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def test_category_rules(self):
        cases = {"hooks/test_x.py": "tests", "src/test/A.kt": "tests", "a/b.spec.ts": "tests",
                 "pkg/foo_test.go": "tests", "__tests__/x.tsx": "tests", "skills/gate-a/SKILL.md": "skills",
                 "CHANGELOG.md": "docs", "hooks/guard.py": "code"}
        for path, cat in cases.items():
            self.assertEqual(rf.category(path), cat, path)

    def test_changed_files_include_untracked_and_counts(self):
        self._write("impl.py", "x = 2  # FIXED\n")
        self._write("tests/test_new.py", "def test_new(): pass\n")   # 추적 안 된 새 파일
        self._write("README.md", "# r2\n")
        rc, out = run(self.repo, "--base", self.base, "--json")
        facts = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(facts["changed"]["total"], 3)
        self.assertEqual(facts["changed"]["by_category"], {"code": 1, "docs": 1, "tests": 1})

    def test_junit_totals(self):
        self._write("j.xml", '<testsuites><testsuite><testcase name="a"/><testcase name="b">'
                             '<failure/></testcase><testcase name="c"><skipped/></testcase>'
                             '</testsuite></testsuites>')
        totals = rf.junit_totals([os.path.join(self.repo, "j.xml")])
        self.assertEqual(totals, {"tests": 3, "passed": 1, "failed": 1, "error": 0, "skipped": 1})

    def test_fail_on_base_table(self):
        """새 시험을 기준 커밋에 얹어 돌리면 test_new 만 실패, test_guard 는 회귀 방지용(통과)."""
        self._write("impl.py", "x = 2  # FIXED\n")
        self._write("tests/test_new.py", "def test_new(): pass\n")
        rc, out = run(self.repo, "--base", self.base, "--json",
                      "--fail-on-base", f"{sys.executable} runner.py", "--base-junit", "junit.xml")
        fb = dict(json.loads(out)["fail_on_base"]["cases"])
        self.assertEqual(fb["t::test_new"], "fails_on_base")
        self.assertEqual(fb["t::test_guard"], "passes_on_base")
        rc, md = run(self.repo, "--base", self.base,
                     "--fail-on-base", f"{sys.executable} runner.py", "--base-junit", "junit.xml")
        self.assertIn("시험 **3건 중 1건이 수정 전 실패**", md)
        self.assertIn("수정 전 통과 2건(회귀 방지용)", md)
        # worktree 를 남기지 않는다
        wt = subprocess.run(["git", "-C", self.repo, "worktree", "list"], capture_output=True,
                            text=True).stdout.strip().splitlines()
        self.assertEqual(len(wt), 1)

    def test_errors_are_reported_not_invented(self):
        rc, md = run(self.repo, "--junit", os.path.join(self.repo, "missing.xml"))
        self.assertEqual(rc, 0)
        self.assertIn("시험 합계: 확인 불가", md)
        rc, md = run(self.repo, "--fail-on-base", "true")
        self.assertIn("기준 커밋 재현: 확인 불가", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
