"""fresh_review.py 시험 — 되돌리기 어렵거나 설계 판단이 큰 계획만 새 문맥 검토를 준비하고, 검토자 입력에서 쓴 사람의 요약을 뺀다."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fresh_review as fr  # noqa: E402

SCRIPT = os.path.join(HERE, "fresh_review.py")
HAS_GIT = shutil.which("git") is not None


def doc(files=("src/a.py",), r=0, extra=""):
    """대시보드 R/V/D 줄과 Gate A·B 블록이 있는 세션 문서."""
    listed = "\n".join(f"{i}. `{p}` (수정)" for i, p in enumerate(files, 1))
    return (f"# 현재 세션 상태\n\n| 항목 | 내용 |\n|---|---|\n| R/V/D 분해 | R={r} / V=1: 변경파일 1 +1 / D=0 |\n\n"
            "## Gate A 계획 — 슬러그 규칙\n\n> 계획 머리의 글\n\n"
            "### 이해 브리핑\n- **왜 바꾸나**: 브리핑에만 있는 문장\n- **어떻게 동작하나**: 어떻게\n"
            "- **가장 깨지기 쉬운 곳**: 곳\n- **되돌리는 법**: 이 커밋을 되돌리면 끝난다.\n\n"
            f"### 변경 파일 ({len(files)}개)\n{listed}\n\n### 파일별 변경 내용\n계획 본문의 문장\n\n"
            "### 교훈 조회\n- 일치 없음 (질의: x)\n\n### Gate별 권장 모델\n| B | — |\n\n"
            "### 리스크 및 대응\n| 리스크 | 원인 | 대응 |\n|---|---|---|\n| 위험 | 원인 | 대응 |\n\n"
            f"### 이해도 게이트 발동 판정\n미발동 — 해당 없음\n{extra}\n\n## Gate B\n다음 블록의 문장\n")


def git(*args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


def run(content, *args, repo=None):
    """스크립트를 돌린다 → (exit, stdout, git 폴더에 쓴 입력 또는 None, 작업 폴더 목록).

    repo: None(git 아님) · "git"(보통 저장소) · "worktree"(git 폴더가 프로젝트 밖)."""
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "proj")
        os.mkdir(base)
        git_dir = os.path.join(base, ".git")
        if repo:
            git("init", "-q", base)
        if repo == "worktree":
            git("-C", base, "commit", "-q", "--allow-empty", "-m", "base")
            wt = os.path.join(tmp, "wt")
            git("-C", base, "worktree", "add", "-q", wt)
            git_dir, base = os.path.join(base, ".git", "worktrees", "wt"), wt
        path = os.path.join(base, "CURRENT_SESSION.md")
        if content is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        proc = subprocess.run([sys.executable, SCRIPT, path, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env={**os.environ, "CLAUDE_PROJECT_DIR": base, "PYTHONIOENCODING": "utf-8"})
        target = os.path.join(git_dir, fr.INPUT_NAME)
        written = None
        if os.path.exists(target):
            with open(target, encoding="utf-8") as f:
                written = f.read()
        tree = sorted(n for n in os.listdir(base) if n != ".git")
    return proc.returncode, proc.stdout, written, tree


class TestWhenToReview(unittest.TestCase):

    def test_ordinary_plan_is_not_reviewed(self):
        rc, out, written, _ = run(doc())
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "미실행 — 이해도 게이트 미발동 · R=0")
        self.assertIsNone(written)

    def test_plan_that_is_hard_to_undo_is_reviewed(self):
        out = run(doc(files=("db/migrations/0001.sql",)))[1]
        self.assertTrue(out.startswith("발동 — 이해도 게이트 발동(데이터: db/migrations/0001.sql)"), out)
        self.assertIn(fr.MARKER, out)
        self.assertIn('subagent_type "Plan"', out)
        # 하위 에이전트가 뒤에서 돌면 Agent 호출이 곧바로 돌아온다 — 결과 전에 승인을 청하지 않게 한다
        self.assertIn("답을 받아 처리하기 전에는 승인을 요청하지 않는다", out)

    def test_plan_with_high_reasoning_depth_is_reviewed(self):
        self.assertTrue(run(doc(r=6))[1].startswith("발동 — R=6"))
        self.assertTrue(run(doc(r=3))[1].startswith("미실행 — 이해도 게이트 미발동 · R=3"))

    def test_undecidable_gate_b_falls_back_to_r_and_says_so(self):
        """판정기가 변경 파일 목록을 못 읽으면(백틱 없음) R 만 본다 — 출력 줄에 그 상태가 남는다."""
        def unlisted(r):
            return doc(r=r).replace("1. `src/a.py` (수정)", "1. src/a.py (수정)")

        self.assertTrue(run(unlisted(6))[1].startswith("발동 — R=6"))
        self.assertEqual(run(unlisted(0))[1].strip(), "미실행 — 이해도 게이트 판정 불가 · R=0")

    def test_recorded_plan_is_not_reviewed_again_unless_forced(self):
        recorded = doc(files=("db/migrations/1.sql",), extra="- **새 문맥 검토**: 지적 1 · 고침 1 · 올림 0 · 반박 0")
        self.assertTrue(run(recorded)[1].startswith("미실행 — 이미 검토함"))
        self.assertTrue(run(recorded, "--force")[1].startswith("발동 — 이해도 게이트 발동"))
        self.assertTrue(run(doc(), "--force")[1].startswith("발동 — --force"))

    def test_failed_review_does_not_block_the_next_run(self):
        failed = doc(r=6, extra="- **새 문맥 검토**: 실패 — 검토자가 빈 답을 냈다")
        self.assertTrue(run(failed)[1].startswith("발동 — R=6"))

    def test_naming_the_record_in_the_plan_text_is_not_a_record(self):
        """실제 계획으로 돌려 본 재현: 계획 글이 기록 줄의 이름을 말하자 「이미 검토함」이 됐다."""
        mention = doc(files=("db/migrations/1.sql",), extra="기록이 있으면 `**새 문맥 검토**` 줄을 본다.")
        self.assertTrue(run(mention)[1].startswith("발동 — "))

    def test_the_output_asks_for_the_record_line_it_detects(self):
        out = run(doc(r=6))[1]
        asked = re.findall(r"`(- \*\*새 문맥 검토\*\*: [^`]+)`", out)
        self.assertEqual(len(asked), 2, out)                  # 성공 기록 줄과 실패 기록 줄
        ok, failed = asked
        self.assertRegex(ok.replace("N", "2"), fr.RECORDED)
        self.assertNotRegex(failed, fr.RECORDED)


class TestReviewerInput(unittest.TestCase):

    def check_input(self, text):
        for kept in ("## Gate A 계획 — 슬러그 규칙", "> 계획 머리의 글", "### 변경 파일 (1개)", "`src/a.py`",
                     "계획 본문의 문장", "### 리스크 및 대응"):
            self.assertIn(kept, text)
        for dropped in ("브리핑에만 있는 문장", "### 이해 브리핑", "교훈 조회", "권장 모델", "이해도 게이트", "다음 블록의 문장"):
            self.assertNotIn(dropped, text)

    @unittest.skipUnless(HAS_GIT, "git 이 없다")
    def test_input_goes_into_the_git_dir_not_the_work_tree(self):
        _, out, written, tree = run(doc(r=6), repo="git")
        self.check_input(written)
        self.assertEqual(tree, ["CURRENT_SESSION.md"])
        self.assertIn(fr.INPUT_NAME, out)
        self.assertNotIn("=====", out)

    def test_prompt_names_the_repository_instead_of_relying_on_the_agents_folder(self):
        """실제 계획으로 돌려 본 재현: 하위 에이전트가 다른 폴더에서 시작해 계획의 상대 경로를 하나도 찾지 못했다."""
        out = run(doc(r=6))[1]
        self.assertRegex(out, r"계획이 말하는 저장소는 `[^`]+/proj` 다")

    def test_outside_git_the_plan_goes_inside_the_prompt(self):
        _, out, written, _ = run(doc(r=6))
        self.assertIsNone(written)
        prompt = out.split("-----\n")[1]
        self.check_input(prompt.split("=====\n")[1])

    @unittest.skipUnless(HAS_GIT, "git 이 없다")
    def test_worktree_git_dir_is_outside_the_project_so_the_plan_goes_inside_the_prompt(self):
        """worktree 의 git 폴더는 본 저장소 안에 있다 — 검토자의 Read 가 권한 확인에 걸릴 수 있다."""
        _, out, written, _ = run(doc(r=6), repo="worktree")
        self.assertIsNone(written)
        self.assertIn("=====", out)

    def test_skip_list_does_not_drop_plan_content_by_a_short_word(self):
        """빼는 목록은 부분일치다 — 「OSS」였을 때는 「CROSS-ORIGIN」 절까지 뺐다."""
        extra = "\n\n### CROSS-ORIGIN 설정\n허용 출처를 줄인다\n\n### 모델 권장표\n| C | Sonnet |"
        text = fr.review_input(doc().replace("\n\n## Gate B", extra + "\n\n## Gate B"))
        self.assertIn("허용 출처를 줄인다", text)
        self.assertNotIn("모델 권장표", text)

    def test_plan_without_subsections_is_not_reviewed(self):
        """`###` 절이 없으면 이해 브리핑만 떼어 낼 수 없다 — 요약을 함께 주느니 돌리지 않는다."""
        bold = "| R/V/D 분해 | R=6 / V=1 |\n\n## Gate A 계획\n**변경 파일**: `src/a.py`\n**왜 바꾸나**: 요약\n"
        rc, out, written, _ = run(bold)
        self.assertEqual((rc, written), (0, None))
        self.assertTrue(out.startswith("미실행 — Gate A 블록에 `###` 절이 없어"), out)


class TestNeverStopsGateA(unittest.TestCase):

    def test_breakage_is_reported_as_failure_not_as_not_needed(self):
        rc, out, _, _ = run(None)
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("실패 — 준비하지 못함"), out)
        self.assertIn("- **새 문맥 검토**: 실패 — 스크립트가 준비하지 못함", out)

    def test_r_score_reads_only_the_dashboard_cell(self):
        """대시보드·세션 원장과 같은 칸만 읽는다. 다른 스킬의 양식 인용이 위에 있어도 걸리지 않는다(이 서버 기록 대조)."""
        self.assertEqual(fr.r_score("| R/V/D 분해 | R=7 / V=2 / D=0 |"), 7)
        quoted = ("   R/V/D 분해: R={R-A 항목 1줄 또는 0} / V={…}\n   R/V/D 분해: R=외부 검증 후보 12건(R-D1 +3)\n"
                  "   R/V/D 분해: R=0 / V=1 / D=0\n")                       # 채워진 양식 인용
        self.assertEqual(fr.r_score(quoted + "| R/V/D 분해 | R=6 / V=1 / D=0 |"), 6)
        self.assertIsNone(fr.r_score(quoted))
        self.assertIsNone(fr.r_score("- **R/V/D 분해**: R=6 / V=3"))       # 대시보드도 이 형식은 읽지 않는다
        self.assertIsNone(fr.r_score("| C | Sonnet 5.5 | R=6 / V=3 |"))     # Gate별 권장 모델 표의 칸
        self.assertIsNone(fr.r_score(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
