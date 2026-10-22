"""lane_card.py 시험 — 자율 레인 검토 카드가 사실로 채워지고, 카드와 사람의 판정이 원장에 빠짐없이 남는다.

임시 git 저장소에 기준 커밋·계획(CURRENT_SESSION.md)·설정을 만들고 스크립트를 실제로 실행한다.
적용 계획 S8a 의 완료 판정은 「카드 판정이 원장에 100% 남음」이다.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lane_card.py")

ANSWERS = """project: "t"
archive_path: "docs/archive"
autonomous_lane:
  enabled: true
  max_lines: 200
"""

PLAN = """# 현재 세션 상태

> **세션 ID**: T-CARD-1

## Gate A 계획

### 레인 판정
- **레인**: 자율
- **걸린 트리거**: 없음
- **기준 커밋**: `{base}`
- **수락 명령**: `{accept}`

### 변경 파일 (2개)

1. `src/slug.py` (수정)
2. `tests/test_slug.py` (생성)

## Gate D 검증

- 루프: self-debug {sd}회 · 수렴
- FIX-B {fb}건 · DEP 0건
"""


def sh(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


class CardCase(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        sh(self.repo, "init", "-q")
        sh(self.repo, "config", "user.email", "t@t")
        sh(self.repo, "config", "user.name", "t")
        self.write("src/slug.py", "def slug(s):\n    return s\n")
        self.write(".claude/harness-answers.yml", ANSWERS)
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", "base")
        self.base = sh(self.repo, "rev-parse", "--short", "HEAD")
        self.set_plan()
        self.write("src/slug.py", "def slug(s):\n    return s.strip()\n")
        self.write("tests/test_slug.py", "def test_slug():\n    assert True\n")

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def set_plan(self, accept="python3 -c 'print(1)'", sd=0, fb=0, base=None):
        self.write("CURRENT_SESSION.md", PLAN.format(base=base or self.base, accept=accept, sd=sd, fb=fb))

    def run_card(self, *args):
        proc = subprocess.run([sys.executable, SCRIPT, *args, "--repo", self.repo], capture_output=True,
                              text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return proc.returncode, proc.stdout, proc.stderr

    def ledger(self):
        path = os.path.join(self.repo, "docs", "archive", "lane-ledger.jsonl")
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class TestCard(CardCase):

    def test_card_is_written_to_the_ledger_as_pending(self):
        rc, out, _ = self.run_card("card", "--run")
        self.assertEqual(rc, 0)
        (entry,) = self.ledger()
        self.assertEqual((entry["kind"], entry["session_id"], entry["verdict"]), ("card", "T-CARD-1", "대기"))
        self.assertEqual(entry["base"], self.base)
        self.assertEqual(sorted(entry["files"]), ["src/slug.py", "tests/test_slug.py"])
        self.assertEqual(entry["acceptance"], [{"cmd": "python3 -c 'print(1)'", "rc": 0}])
        self.assertEqual(entry["scope_problems"], [])
        self.assertEqual(entry["flags"], [])
        self.assertIn("검토 카드", out)
        self.assertIn("「카드 승인」", out)

    def test_acceptance_command_is_rerun_and_failure_is_flagged(self):
        self.set_plan(accept="python3 -c 'import sys; sys.exit(3)'")
        rc, out, _ = self.run_card("card", "--run")
        entry = self.ledger()[0]
        self.assertEqual(entry["acceptance"][0]["rc"], 3)
        self.assertIn("수락 명령 실패", " ".join(entry["flags"]))
        self.assertIn("실패", out)

    def test_without_run_the_card_says_so(self):
        self.run_card("card")
        entry = self.ledger()[0]
        self.assertIsNone(entry["acceptance"][0]["rc"])
        self.assertIn("수락 명령 재실행 안 함", entry["flags"])

    def test_scope_violation_is_flagged(self):
        self.write("src/other.py", "x = 1\n")
        self.run_card("card", "--run")
        entry = self.ledger()[0]
        self.assertIn("계획 밖 파일: src/other.py", entry["scope_problems"])
        self.assertIn("범위 위반", " ".join(entry["flags"]))

    def test_markers_and_no_new_test_are_flagged(self):
        self.set_plan(sd=2, fb=1)
        os.remove(os.path.join(self.repo, "tests", "test_slug.py"))
        self.run_card("card", "--run")
        entry = self.ledger()[0]
        self.assertEqual((entry["self_debug"], entry["fix_b"], entry["dep"]), (2, 1, 0))
        flags = " ".join(entry["flags"])
        for needle in ("self-debug 2회", "FIX-B 1건", "새 시험 없음"):
            self.assertIn(needle, flags)

    def test_missing_markers_are_flagged(self):
        """표지가 없으면 error-topics 가드가 조용히 꺼진다 — 카드가 알린다."""
        with open(os.path.join(self.repo, "CURRENT_SESSION.md"), encoding="utf-8") as f:
            doc = f.read().split("## Gate D 검증")[0]
        self.write("CURRENT_SESSION.md", doc)
        self.run_card("card", "--run")
        self.assertIn("Gate D 표지 없음", " ".join(self.ledger()[0]["flags"]))

    def test_planned_line_budget_overrun_is_flagged(self):
        self.write("src/slug.py", "x = 1\n" * 250)
        self.run_card("card", "--run")
        self.assertIn("계획 줄 수 초과", " ".join(self.ledger()[0]["flags"]))

    def test_unreadable_lane_block_still_leaves_a_card(self):
        self.set_plan(base="HEAD")
        rc, out, _ = self.run_card("card", "--run")
        self.assertEqual(rc, 0)
        entry = self.ledger()[0]
        self.assertEqual(entry["lane"], "검토")
        self.assertIn("레인 판정을 자율로 읽지 못함", " ".join(entry["flags"]))

    def test_missing_ledger_path_is_an_error_not_a_skip(self):
        self.write(".claude/harness-answers.yml", "project: \"t\"\n")
        rc, out, err = self.run_card("card", "--run")
        self.assertNotEqual(rc, 0)
        self.assertIn("archive_path", out + err)


class TestVerdict(CardCase):

    def test_verdict_is_appended_and_pending_is_cleared(self):
        self.run_card("card", "--run")
        rc, out, _ = self.run_card("pending")
        self.assertIn("T-CARD-1", out)
        rc, out, _ = self.run_card("verdict", "--verdict", "경미", "--note", "이름이 모호함")
        self.assertEqual(rc, 0)
        card, verdict = self.ledger()
        self.assertEqual((verdict["kind"], verdict["verdict"], verdict["note"]), ("verdict", "경미", "이름이 모호함"))
        self.assertEqual(verdict["card_id"], card["card_id"])
        rc, out, _ = self.run_card("pending")
        self.assertNotIn("T-CARD-1", out)

    def test_unknown_verdict_is_rejected(self):
        self.run_card("card", "--run")
        rc, _, _ = self.run_card("verdict", "--verdict", "좋음")
        self.assertNotEqual(rc, 0)
        self.assertEqual(len(self.ledger()), 1)

    def test_verdict_without_a_card_is_an_error(self):
        os.makedirs(os.path.join(self.repo, "docs", "archive"), exist_ok=True)
        rc, out, err = self.run_card("verdict", "--verdict", "승인")
        self.assertNotEqual(rc, 0)
        self.assertIn("카드", out + err)

    def test_earlier_pending_card_is_flagged_on_the_next_card(self):
        self.run_card("card", "--run")
        self.write("CURRENT_SESSION.md", PLAN.replace("T-CARD-1", "T-CARD-2").format(
            base=self.base, accept="python3 -c 'print(1)'", sd=0, fb=0))
        self.run_card("card", "--run")
        second = self.ledger()[1]
        self.assertIn("이전 카드 미판정 1건", " ".join(second["flags"]))
        self.assertEqual(sorted(second["files"]), ["src/slug.py", "tests/test_slug.py"])  # 원장 자신은 빠진다


if __name__ == "__main__":
    unittest.main(verbosity=2)
