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
    ANSWERS = ANSWERS
    BASE_FILES = {}

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        sh(self.repo, "init", "-q")
        sh(self.repo, "config", "user.email", "t@t")
        sh(self.repo, "config", "user.name", "t")
        self.write("src/slug.py", "def slug(s):\n    return s\n")
        self.write(".claude/harness-answers.yml", self.ANSWERS)
        for rel, text in self.BASE_FILES.items():
            self.write(rel, text)
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


# ── 반복 (LANE-LOOP-1-b) ─────────────────────────────────────────────

PLAN_DOC = """# 계획

## Phase 1 — 기반
- [x] 저장소를 만든다

## Phase 2 — 슬러그
- [ ] 슬러그가 공백을 지운다
- [ ] 슬러그가 소문자로 바꾼다

## Phase 3 — 문서
- [ ] 사용법을 적는다
"""

PLAN_LOOP = """# 현재 세션 상태

> **세션 ID**: {sid}

## Gate A 계획

### 레인 판정
- **레인**: 자율
- **멈춤 트리거**: 없음
- **표시 트리거**: 기존 시험 변경 — tests/test_old.py
- **기준 커밋**: `{base}`
- **수락 명령**: `{accept}`

### 변경 파일 (3개)

1. `src/slug.py` (수정)
2. `tests/test_slug.py` (생성)
3. `tests/test_old.py` (수정)

### 결정
- **결정**: 공백은 strip 으로 지운다 — 근거: DECISION_LOG 2026-11-01
- **결정**: 빈 문자열은 그대로 돌려준다 — 근거 없음 (권장안)

```markdown
- **결정**: 코드 블록 안의 예시 — 근거 없음
```

## Gate D 검증

- 루프: self-debug 0회 · 수렴
- FIX-B 0건 · DEP 0건
"""

LOOP_ANSWERS = ANSWERS + 'plan_tier: "1"\nsingle_plan_file: "docs/PLAN.md"\n'


class LoopCase(CardCase):
    """plan_tier 1 계획 문서가 있는 저장소. 한 사이클 = 기준 체크 → `card --run --target N` → 사이클 커밋."""
    ANSWERS = LOOP_ANSWERS
    BASE_FILES = {"docs/PLAN.md": PLAN_DOC, "tests/test_old.py": "def test_old():\n    assert True\n"}

    def setUp(self):
        super().setUp()
        self.write("tests/test_old.py", "def test_old():\n    assert 1 == 1\n")

    def set_plan(self, accept="python3 -c 'print(1)'", sd=0, fb=0, base=None, sid="T-LOOP-1"):
        self.write("CURRENT_SESSION.md", PLAN_LOOP.format(sid=sid, base=base or self.base, accept=accept))

    def edit_doc(self, old, new, rel="docs/PLAN.md"):
        with open(os.path.join(self.repo, rel), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(old, text)
        self.write(rel, text.replace(old, new))

    def check(self, *criteria):
        for c in criteria:
            self.edit_doc(f"- [ ] {c}", f"- [x] {c}")

    def commit(self, message="cycle"):
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", message)
        return sh(self.repo, "rev-parse", "--short", "HEAD")

    def cycle(self, *criteria, target=2):
        self.check(*criteria)
        _, out, _ = self.run_card("card", "--run", "--target", str(target))
        return out, self.commit()

    def next_cycle(self, base, sid="T-LOOP-2"):
        """다음 사이클의 계획 — 직전 사이클 커밋이 기준이다."""
        self.set_plan(base=base, sid=sid)
        self.write("src/slug.py", "def slug(s):\n    return s.strip().lower()\n")

    def next(self, target=2):
        return self.run_card("next", "--target", str(target))


class TestLoopCard(LoopCase):

    def test_loop_card_carries_flags_decisions_and_checked_criteria(self):
        self.check("슬러그가 공백을 지운다")
        rc, out, _ = self.run_card("card", "--run", "--target", "2")
        self.assertEqual(rc, 0)
        (entry,) = self.ledger()
        self.assertEqual((entry["target"], entry["cycle"]), (2, 1))
        self.assertEqual(entry["scope_problems"], [])
        self.assertEqual(entry["scope_flags"], ["기존 시험 변경: tests/test_old.py"])
        self.assertEqual(entry["flag_triggers"], "기존 시험 변경 — tests/test_old.py")
        self.assertEqual(entry["decisions"], {"sourced": 1, "unsourced": ["빈 문자열은 그대로 돌려준다 — 근거 없음 (권장안)"]})
        self.assertEqual(entry["criteria_checked"], ["Phase 2: 슬러그가 공백을 지운다"])
        self.assertEqual(entry["criteria_removed"], [])
        self.assertEqual(entry["flags"], [])
        self.assertIn("반복 Phase 2 까지 · 사이클 1", out)
        self.assertIn("표시(진행함): 기존 시험 변경: tests/test_old.py", out)
        self.assertIn("근거 없음: 빈 문자열은 그대로 돌려준다", out)
        self.assertIn("next --target 2", out)
        self.assertNotIn("「카드 승인」", out)       # 판정은 반복이 끝난 뒤

    def test_removed_criterion_is_flagged(self):
        self.edit_doc("- [ ] 사용법을 적는다\n", "")
        self.run_card("card", "--run", "--target", "2")
        entry = self.ledger()[0]
        self.assertEqual(entry["criteria_removed"], ["Phase 3: 사용법을 적는다"])
        self.assertIn("완료 기준이 지워지거나 바뀜 1건", entry["flags"])

    def test_reworded_criterion_counts_as_removed(self):
        self.edit_doc("- [ ] 슬러그가 소문자로 바꾼다", "- [x] 소문자")
        self.run_card("card", "--run", "--target", "2")
        entry = self.ledger()[0]
        self.assertEqual(entry["criteria_removed"], ["Phase 2: 슬러그가 소문자로 바꾼다"])
        self.assertEqual(entry["criteria_checked"], ["Phase 2: 소문자"])

    def test_cards_of_the_same_loop_are_not_earlier_pending(self):
        _, first = self.cycle("슬러그가 공백을 지운다")
        self.next_cycle(first)
        _, out, _ = self.run_card("card", "--run", "--target", "2")
        second = self.ledger()[1]
        self.assertEqual(second["cycle"], 2)
        self.assertNotIn("이전 카드 미판정", " ".join(second["flags"]))
        self.assertEqual(second["files"], ["src/slug.py"])     # 직전 사이클 커밋이 기준
        self.assertIn("이 반복의 앞 카드 1장: T-LOOP-1", out)

    def test_pending_card_outside_the_loop_is_still_flagged(self):
        self.run_card("card", "--run")                          # 목표 없는 카드 — 반복 밖
        self.run_card("card", "--run", "--target", "2")
        self.assertIn("이전 카드 미판정 1건", self.ledger()[1]["flags"])


class TestNext(LoopCase):

    def assertStopped(self, out, needle):
        self.assertTrue(out.startswith("반복 판정: 멈춤 — "), out)
        self.assertIn(needle, out)
        self.assertIn("lane_card.py pending", out)

    def test_continue_lists_the_remaining_criteria(self):
        self.cycle("슬러그가 공백을 지운다")
        rc, out, _ = self.next()
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("반복 판정: 계속 — Phase 2 까지 완료 기준 2/3 · 사이클 1/10"), out)
        self.assertIn("- Phase 2: 슬러그가 소문자로 바꾼다", out)
        self.assertNotIn("Phase 3", out)
        self.assertNotIn("pending", out)

    def test_goal_reached(self):
        self.cycle("슬러그가 공백을 지운다", "슬러그가 소문자로 바꾼다")
        _, out, _ = self.next()
        self.assertTrue(out.startswith("반복 판정: 목표 도달 — Phase 2 까지 완료 기준 3/3 · 사이클 1/10"), out)
        self.assertIn("lane_card.py pending", out)

    def test_cycle_cap(self):
        self.cycle("슬러그가 공백을 지운다")
        self.write(".claude/harness-answers.yml", LOOP_ANSWERS.replace("  max_lines: 200\n", "  max_lines: 200\n  max_cycles: 1\n"))
        self.commit("cap")
        _, out, _ = self.next()
        self.assertTrue(out.startswith("반복 판정: 상한 도달 — Phase 2 까지 완료 기준 2/3 · 사이클 1/1"), out)
        self.assertIn("- Phase 2: 슬러그가 소문자로 바꾼다", out)

    def test_stops_without_a_plan_document_setting(self):
        self.write(".claude/harness-answers.yml", ANSWERS)
        self.commit("no plan")
        _, out, _ = self.next()
        self.assertStopped(out, "plan_tier 1 계획 문서")

    def test_stops_when_the_target_phase_is_missing(self):
        _, out, _ = self.next(7)
        self.assertStopped(out, "Phase 7 이 없음")

    def test_stops_on_a_phase_without_criteria(self):
        self.edit_doc("- [ ] 사용법을 적는다", "사용법을 적는다")
        self.commit("no criteria")
        _, out, _ = self.next(3)
        self.assertStopped(out, "체크박스)이 없는 Phase 3")

    def test_stops_without_a_card_of_this_loop(self):
        self.commit("no card")
        _, out, _ = self.next()
        self.assertStopped(out, "이 반복의 카드가 없음")

    def test_stops_when_the_last_cycle_failed(self):
        self.set_plan(accept="python3 -c 'import sys; sys.exit(3)'")
        self.cycle("슬러그가 공백을 지운다")
        _, out, _ = self.next()
        self.assertStopped(out, "막힘 — T-LOOP-1: 수락 명령 실패")

    def test_stops_when_a_criterion_was_removed(self):
        self.edit_doc("- [ ] 사용법을 적는다\n", "")
        self.cycle()
        _, out, _ = self.next()
        self.assertStopped(out, "완료 기준 지움·바뀜 1건")

    def test_stops_on_uncommitted_changes(self):
        self.check("슬러그가 공백을 지운다")
        self.run_card("card", "--run", "--target", "2")        # 사이클 커밋을 빠뜨림
        _, out, _ = self.next()
        self.assertStopped(out, "커밋 안 된 변경")


class TestLoopPending(LoopCase):

    def test_pending_shows_each_cycle_with_its_diff_range(self):
        _, first = self.cycle("슬러그가 공백을 지운다")
        self.next_cycle(first)
        _, second = self.cycle("슬러그가 소문자로 바꾼다")
        rc, out, _ = self.run_card("pending")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("판정 없는 카드 2건"), out)
        self.assertIn("**T-LOOP-1**", out)
        self.assertIn(f"`git diff {self.base}..{first}`", out)
        self.assertIn(f"`git diff {first}..HEAD`", out)
        self.assertIn("근거 없음: 빈 문자열은 그대로 돌려준다", out)
        self.assertIn("Phase 2: 슬러그가 소문자로 바꾼다", out)
        self.assertIn("「모두 승인」", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
