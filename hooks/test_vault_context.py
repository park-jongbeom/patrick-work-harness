"""vault-context.py 시험 — 임시 폴더에 가짜 볼트·가짜 프로젝트(harness-answers.yml)를 만들어 하위 프로세스로 실행한다.

원본(한 제품 프로젝트의 HARNESS-VAULT-REF-1 시험 13건)을 설정 방식으로 옮기고, 하네스판에서 더한 것 — 꺼짐은 출력 0,
볼트 경로 후보·환경변수, 마지막 커밋 시각, 인용 블록 절, 태그 데일리, 개인 영역(90 Private) — 을 더했다.
하위 프로세스는 PYTHONIOENCODING 없이 돌린다(원본 세션의 교훈 — 훅이 스스로 UTF-8 로 낸다).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

HOOK = Path(__file__).with_name("vault-context.py")
MARK = "[볼트 발췌 — vault-context]"
CUT = "…(잘림 — 전문은 볼트 노트)"
HUB = "업무 허브"
SUMMARY_REL = "20 Notes/작업 총정리.md"
TODAY = date.today()

SUMMARY = """---
type: reference
---

# 작업 총정리

## 1. 한눈에 보기

| 사이트 | 상태 |
|---|---|
| 메인 | 운영 중 SUMMARY1 |

## 2. 진행 연표

연표 본문 NOT_IN_OUTPUT

## 6. 어디를 보면 되나

| 알고 싶은 것 | 정본 |
|---|---|
| 세션 진행 | SESSION_INDEX.md SUMMARY6 |
"""

#: 원본과 같은 노트·절을 설정으로 — 받은 원본의 출력과 같은 절·같은 순서가 나와야 한다
ORIGINAL_SHAPE = """vault_ref:
  enabled: true
  vault_paths:
    - "{vault}"
  hub: "20 Notes/{hub}.md"
  sections:
    - "{summary} :: ## 1. 한눈에 보기"
    - "{summary} :: ## 6. 어디를 보면 되나"
  daily_head: "### 프로젝트 A"
"""


def daily(body_marker: str, with_section: bool = True) -> str:
    sec = f"### 프로젝트 A\n- [ ] 할 일 {body_marker}\n\n" if with_section else ""
    return f"# 데일리\n\n## ✅ 할 일\n\n{sec}### 다른 절\n- 다른 일 OTHER_SECTION\n"


class VaultContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.project = self.root / "proj"
        (self.project / ".claude").mkdir(parents=True)
        self.note(SUMMARY_REL, SUMMARY)
        self.note(f"20 Notes/{HUB}.md", f"허브 자신 [[{HUB}]]")
        self.configure(ORIGINAL_SHAPE.format(vault=self.vault.as_posix(), hub=HUB, summary=SUMMARY_REL))

    def tearDown(self):
        self.tmp.cleanup()

    def configure(self, block: str):
        (self.project / ".claude" / "harness-answers.yml").write_text(
            '_engine_version: "1.26.0"\nproject_repo: "x"\n' + block + "archive_path: \"docs/archive\"\n", encoding="utf-8")

    def write_daily(self, d: date, text: str, folder: str = "10 Journal"):
        self.note(f"{folder}/{d.year}/{d.isoformat()}.md", text)

    def note(self, rel: str, text: str):
        p = self.vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def run_hook(self, extra_env=None, raw=False):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "VAULT_REF_PATH")}
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env.update(extra_env or {})
        r = subprocess.run([sys.executable, str(HOOK)], env=env, input=b"{}", capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout if raw else r.stdout.decode("utf-8")


class Normal(VaultContextTest):
    def test_all_sections_with_path_and_date_in_order(self):
        self.write_daily(TODAY - timedelta(days=1), daily("DAILY_PAST"))
        self.note("20 Notes/관련 노트.md", f"본문 [[{HUB}]] 링크")
        out = self.run_hook()
        self.assertTrue(out.startswith(MARK), out[:80])
        marks = ["SUMMARY1", "SUMMARY6", "DAILY_PAST", "20 Notes/관련 노트.md"]
        for s in marks:
            self.assertIn(s, out)
        self.assertEqual([out.index(s) for s in marks], sorted(out.index(s) for s in marks))   # 머리 → 절 → 데일리 → 백링크
        self.assertNotIn("NOT_IN_OUTPUT", out)  # §2 는 넣지 않음
        self.assertNotIn("OTHER_SECTION", out)  # 데일리 다른 절은 넣지 않음
        self.assertIn(f"(수정 {TODAY.isoformat()})", out)
        self.assertIn("harness-answers.yml 의 vault_ref", out)
        self.assertLessEqual(len(out), 8000)

    def test_future_daily_is_ignored(self):
        self.write_daily(TODAY + timedelta(days=1), daily("DAILY_FUTURE"))
        self.write_daily(TODAY - timedelta(days=1), daily("DAILY_PAST"))
        out = self.run_hook()
        self.assertIn("DAILY_PAST", out)
        self.assertNotIn("DAILY_FUTURE", out)

    def test_walks_back_when_latest_daily_lacks_section(self):
        self.write_daily(TODAY, daily("NONE", with_section=False))
        older = TODAY - timedelta(days=2)
        self.write_daily(older, daily("DAILY_OLDER"))
        out = self.run_hook()
        self.assertIn("DAILY_OLDER", out)
        self.assertIn(f"{older.isoformat()}.md", out)

    def test_previous_year_folder(self):
        self.write_daily(date(TODAY.year - 1, 12, 31), daily("DAILY_LAST_YEAR"))
        self.assertIn("DAILY_LAST_YEAR", self.run_hook())

    def test_no_daily_section_says_none(self):
        self.write_daily(TODAY, daily("NONE", with_section=False))
        self.assertIn("(없음 — 최근 7개 데일리에", self.run_hook())


class Links(VaultContextTest):
    def test_alias_and_heading_links_count_but_not_plain_text_excluded_or_private(self):
        self.note("20 Notes/별칭.md", f"[[{HUB}|허브]]")
        self.note("20 Notes/절링크.md", f"[[{HUB}#다음 액션]]")
        self.note("20 Notes/글자만.md", f"{HUB} 이야기만 한다")
        self.note("50 Scrum/2026/카드.md", f"[[{HUB}]]")
        self.note("10 Journal/2026/2026-01-01.md", f"[[{HUB}]]")
        self.note("90 Private/개인 메모.md", f"[[{HUB}]]")     # 2026-11-20 실제 실행에서 이 꼴의 이름이 섞였다
        out = self.run_hook()
        self.assertIn("20 Notes/별칭.md", out)
        self.assertIn("20 Notes/절링크.md", out)
        self.assertNotIn("글자만.md", out)
        self.assertNotIn("카드.md", out)
        self.assertNotIn("90 Private", out)
        self.assertNotIn(f"20 Notes/{HUB}.md (수정", out)  # 허브 자신
        self.assertIn("2개 중", out)


class Size(VaultContextTest):
    def test_each_section_clipped_and_others_survive(self):
        huge_rows = "\n".join(f"| 행 {i} | " + "가" * 50 + " |" for i in range(400))
        self.note(SUMMARY_REL, SUMMARY.replace("| 메인 | 운영 중 SUMMARY1 |", huge_rows + "\n" + "나" * 2000))
        self.write_daily(TODAY, daily("DAILY_PAST " + "다" * 3000))
        out = self.run_hook()
        self.assertIn(CUT, out)
        self.assertIn("SUMMARY6", out)  # 앞 절이 넘쳐도 뒤 절은 남음
        self.assertIn("DAILY_PAST", out)
        self.assertLessEqual(len(out), 8000)
        self.assertLessEqual(max(len(l) for l in out.split("\n")), 400)


class Off(VaultContextTest):
    """꺼진 프로젝트는 맥락에 한 글자도 넣지 않는다 — 플러그인·install.sh 는 모든 프로젝트에 이 훅을 건다."""

    def test_disabled_block_prints_nothing(self):
        self.configure(ORIGINAL_SHAPE.format(vault=self.vault.as_posix(), hub=HUB, summary=SUMMARY_REL)
                       .replace("enabled: true", "enabled: false"))
        self.assertEqual(self.run_hook(raw=True), b"")

    def test_no_block_or_no_answers_file_prints_nothing(self):
        self.configure("")
        self.assertEqual(self.run_hook(raw=True), b"")
        (self.project / ".claude" / "harness-answers.yml").unlink()
        self.assertEqual(self.run_hook(raw=True), b"")


class VaultChoice(VaultContextTest):
    def block(self, *paths):
        return "vault_ref:\n  enabled: true\n  vault_paths:\n" + "".join(f'    - "{p}"\n' for p in paths) + \
               f'  sections:\n    - "{SUMMARY_REL} :: ## 1. 한눈에 보기"\n'

    def test_first_existing_candidate_is_used(self):
        self.configure(self.block((self.root / "dead-copy").as_posix(), self.vault.as_posix()))
        out = self.run_hook()
        self.assertIn(f"볼트: {self.vault.as_posix()}", out)
        self.assertIn("SUMMARY1", out)

    def test_environment_variable_comes_first(self):
        other = self.root / "other"
        (other / "20 Notes").mkdir(parents=True)
        (other / SUMMARY_REL).write_text(SUMMARY.replace("SUMMARY1", "FROM_ENV"), encoding="utf-8")
        out = self.run_hook({"VAULT_REF_PATH": str(other)})
        self.assertIn("FROM_ENV", out)
        self.assertNotIn("SUMMARY1", out)

    def test_home_shorthand_is_expanded(self):
        self.configure(self.block("~/vault"))
        out = self.run_hook({"HOME": str(self.root), "USERPROFILE": str(self.root)})
        self.assertIn("SUMMARY1", out)

    def test_no_vault_gives_one_line(self):
        self.configure(self.block((self.root / "gone").as_posix()))
        out = self.run_hook()
        self.assertTrue(out.startswith(MARK))
        self.assertIn("볼트 폴더 없음", out)
        self.assertEqual(out.strip().count("\n"), 0)

    def test_header_shows_no_git_when_vault_is_not_a_repository(self):
        self.assertIn("마지막 커밋 확인 불가(git 저장소 아님)", self.run_hook())

    @unittest.skipUnless(shutil.which("git"), "git 이 없다")
    def test_header_shows_last_commit_and_age(self):
        old = (TODAY - timedelta(days=30)).isoformat() + "T12:00:00"
        env = dict(os.environ, GIT_AUTHOR_DATE=old, GIT_COMMITTER_DATE=old, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
            subprocess.run(["git", "-C", str(self.vault), *args], env=env, check=True, capture_output=True)
        out = self.run_hook()
        self.assertIn(f"마지막 커밋 {old[:10]}", out)
        self.assertIn("(30일 전)", out)


class Shapes(VaultContextTest):
    """첫 대상 프로젝트의 꼴 — 허브의 「📍 지금 상태」는 인용 블록이고, 데일리는 태그가 든 줄이다(이 서버의 볼트 사본)."""

    HUB_NOTE = ("# 허브\n\n## ✅ 현재 상태\n\n> 📍 **지금 상태 (2026-10-21 아침 기준)**\n> - 코어 QUOTE1\n> - 디자인 QUOTE2\n>\n"
                "> 📍 **이전 「지금 상태」**\n> 옛 줄\n\n본문 AFTER_QUOTE\n")

    def setUp(self):
        super().setUp()
        self.note("20 Notes/허브.md", self.HUB_NOTE)

    def test_quote_block_section_and_tag_daily(self):
        self.configure("vault_ref:\n  enabled: true  # 켬\n  vault_paths: [\"%s\"]\n  hub: \"20 Notes/허브.md\"\n"
                       "  sections:\n    - \"20 Notes/허브.md :: > 📍 **지금 상태\"\n  daily_tag: \"#proj-a\"\n"
                       % self.vault.as_posix())
        self.write_daily(TODAY, "# 데일리\n- [ ] 할 일 TAGGED #proj-a\n- [ ] 다른 일 UNTAGGED #other\n"
                                "- [ ] 비슷한 태그 PREFIX #proj-a-site\n")
        out = self.run_hook()
        self.assertIn("QUOTE1", out)
        self.assertIn("QUOTE2", out)
        self.assertIn("이전 「지금 상태」", out)      # 빈 > 줄까지 한 인용 블록이다
        self.assertNotIn("AFTER_QUOTE", out)
        self.assertIn("TAGGED", out)
        self.assertNotIn("UNTAGGED", out)
        self.assertNotIn("PREFIX", out)               # 다른 태그의 앞부분은 같은 태그가 아니다

    def test_private_note_in_sections_is_not_read(self):
        self.note("90 Private/비밀.md", "## 비밀\nSECRET_BODY\n")
        self.configure("vault_ref:\n  enabled: true\n  vault_paths:\n    - \"%s\"\n  sections:\n"
                       "    - \"90 Private/비밀.md :: ## 비밀\"\n" % self.vault.as_posix())
        out = self.run_hook()
        self.assertNotIn("SECRET_BODY", out)
        self.assertIn("읽지 않음 — 개인 영역 90 Private", out)

    def test_key_combinations(self):
        base = "vault_ref:\n  enabled: true\n  vault_paths:\n    - \"%s\"\n" % self.vault.as_posix()
        self.write_daily(TODAY, daily("HEAD_WINS") + "- 태그 줄 TAG_LOSES #proj-a\n", folder="Daily")
        self.configure(base + "  daily_dir: \"Daily\"\n  daily_head: \"### 프로젝트 A\"\n  daily_tag: \"#proj-a\"\n")
        out = self.run_hook()
        self.assertIn("HEAD_WINS", out)               # 둘 다 있으면 소절
        self.assertNotIn("TAG_LOSES", out)
        self.assertIn("Daily/", out)
        self.configure(base)                          # 허브·절·데일리 모두 없음 → 머리만
        out = self.run_hook()
        self.assertTrue(out.startswith(MARK))
        self.assertNotIn("## ", out)


class Failures(VaultContextTest):
    def test_summary_note_missing_keeps_other_sections(self):
        (self.vault / SUMMARY_REL).unlink()
        self.write_daily(TODAY, daily("DAILY_PAST"))
        out = self.run_hook()
        self.assertIn("(없음 — 노트 없음)", out)
        self.assertIn("DAILY_PAST", out)

    def test_missing_heading_says_none(self):
        self.note(SUMMARY_REL, "# 총정리\n\n본문만\n")
        self.assertIn("(없음 — 절 없음)", self.run_hook())

    def test_output_is_utf8_even_when_the_console_is_cp949(self):
        """Windows 기본 출력 인코딩(cp949)으로 강제해도 한글·「—」가 UTF-8 로 나온다 — 배선에는 PYTHONIOENCODING 이 없다."""
        out = self.run_hook({"PYTHONIOENCODING": "cp949"}, raw=True)
        self.assertTrue(out.decode("utf-8").startswith(MARK))


if __name__ == "__main__":
    unittest.main()
