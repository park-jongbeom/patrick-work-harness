#!/usr/bin/env python3
"""skills/gate-a/lessons_lookup.py 단위 시험 (HARNESS-LESSON-1)."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "gate-a", "lessons_lookup.py")


def entry(date, sid, title, when="", rule="", evidence="", status="유효", recur=0):
    lines = [f"## [{date}] {sid} — {title}", "- **발생 Gate**: D"]
    if when:
        lines.append(f"- **적용 조건**: {when}")
    lines += ["- **증상**: 실패", f"- **재발 방지 규칙**: {rule}"]
    if evidence:
        lines.append(f"- **근거**: {evidence}")
    lines.append(f"- **상태**: {status}")
    lines += [f"- **재발**: [2026-10-0{k + 1}] S-{k} — 또 남" for k in range(recur)]
    return "\n".join(lines) + "\n\n"


class LessonsLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.project = os.path.join(self.root, "plans")
        os.makedirs(os.path.join(self.project, ".claude"))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))

    def run_lookup(self, *extra, project=None):
        r = subprocess.run([sys.executable, "-I", SCRIPT, project or self.project, *extra],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
        return r.returncode, r.stdout

    def with_repo_topics(self, files):
        self.write("plans/.claude/harness-answers.yml", "code_repos:\n  - api\n  - web\n")
        for name, body in files.items():
            self.write(f"api/docs/rules/error_topics/{name}", body)

    def test_matches_next_action_and_caps_at_two(self):
        self.with_repo_topics({
            "testing.md": entry("2026-10-09", "S-1", "MockK stub 누락", when="MockK 로 서비스 단위 시험을 쓸 때",
                                rule="relaxed mock 대신 every 로 모든 호출을 고정", evidence="S-1 · gradlew test exit 1")
                          + entry("2026-09-01", "S-2", "MockK verify 순서", when="MockK verify 를 쓸 때",
                                  rule="verifyOrder 사용")
                          + entry("2026-08-01", "S-3", "MockK 초기화", when="MockK 픽스처를 공유할 때",
                                  rule="clearAllMocks"),
            "runtime_env.md": entry("2026-10-01", "S-4", "포트 충돌", when="docker compose 로 띄울 때",
                                    rule="기존 컨테이너 정리"),
        })
        self.write("plans/SESSION_INDEX.md", "next_action: MockK 단위 시험 추가 (MatchService)\n")
        code, out = self.run_lookup()
        self.assertEqual(code, 0)
        shown = [l for l in out.splitlines() if l.startswith("- [")]
        self.assertTrue(1 <= len(shown) <= 2, out)
        self.assertIn("S-1", shown[0], out)  # 적용 조건에서 두 단어가 맞은 항목이 가장 강하다
        self.assertNotIn("포트 충돌", out)
        self.assertIn("relaxed mock 대신", out)
        self.assertIn("항목 4건", out)

    def test_never_more_than_two(self):
        self.with_repo_topics({"testing.md": "".join(
            entry(f"2026-10-0{k}", f"S-{k}", "MockK stub 누락", when="MockK stub 누락 시험", rule="r")
            for k in range(1, 6))})
        _, out = self.run_lookup("--query", "MockK stub 누락")
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("- [")]), 2, out)

    def test_one_shared_word_outside_condition_is_not_enough(self):
        self.with_repo_topics({"testing.md": entry("2026-10-09", "S-1", "커밋 전 KDoc 주석 정리",
                                                    rule="KDoc 본문에 */ 를 쓰지 않는다")
                                             + entry("2026-10-08", "S-2", "포트 충돌", rule="정리")})
        _, out = self.run_lookup("--query", "커밋 메시지 영어")
        self.assertIn("일치하는 교훈: 없음", out)

    def test_no_match_says_none(self):
        self.with_repo_topics({"testing.md": entry("2026-10-09", "S-1", "MockK stub 누락",
                                                    when="MockK 로 시험을 쓸 때", rule="every 로 고정")})
        self.write("plans/SESSION_INDEX.md", "next_action: 대시보드 색상 정리\n")
        code, out = self.run_lookup()
        self.assertEqual(code, 0)
        self.assertIn("일치하는 교훈: 없음", out)

    def test_automatic_query_needs_a_stronger_match(self):
        """긴 next_action 문장에서 한 칸만 약하게 겹치면 자동 주입하지 않는다."""
        others = "".join(entry(f"2026-09-0{k}", f"X-{k}", f"무관 항목 {k}", rule="다른 규칙") for k in range(1, 5))
        self.with_repo_topics({"testing.md": entry("2026-10-09", "S-1", "Flyway checksum mismatch",
                                                    rule="Flyway 마이그레이션 파일은 수정하지 않는다") + others})
        self.write("plans/SESSION_INDEX.md", "next_action: Flyway checksum 정리\n")
        _, auto = self.run_lookup()
        _, manual = self.run_lookup("--query", "Flyway checksum 정리")
        self.assertIn("일치하는 교훈: 없음", auto)
        self.assertIn("S-1", manual)

    def test_explicit_query_overrides_next_action(self):
        self.with_repo_topics({"runtime_env.md": entry("2026-10-01", "S-4", "포트 충돌",
                                                        when="docker compose 로 띄울 때", rule="기존 컨테이너 정리")})
        self.write("plans/SESSION_INDEX.md", "next_action: MockK 시험\n")
        code, out = self.run_lookup("--query", "docker compose 포트")
        self.assertEqual(code, 0)
        self.assertIn("S-4", out)
        self.assertIn("질의(--query)", out)

    def test_superseded_entries_are_skipped(self):
        self.with_repo_topics({"testing.md": entry("2026-10-09", "S-OLD", "MockK stub 누락",
                                                    when="MockK 로 시험을 쓸 때", rule="옛 규칙",
                                                    status="대체됨 → [2026-10-18] S-NEW")})
        self.write("plans/SESSION_INDEX.md", "next_action: MockK 시험 추가\n")
        code, out = self.run_lookup()
        self.assertEqual(code, 0)
        self.assertNotIn("S-OLD", out)
        self.assertIn("대체됨 1건 제외", out)

    def test_recurrence_breaks_ties(self):
        self.with_repo_topics({"testing.md":
                               entry("2026-10-09", "S-A", "MockK stub", when="MockK stub 누락 시험", rule="r")
                               + entry("2026-09-09", "S-B", "MockK stub", when="MockK stub 누락 시험", rule="r", recur=2)})
        self.write("plans/SESSION_INDEX.md", "next_action: MockK stub 누락\n")
        _, out = self.run_lookup()
        shown = [l for l in out.splitlines() if l.startswith("- [")]
        self.assertIn("S-B", shown[0], out)

    def test_old_format_entries_still_match_on_title_and_rule(self):
        self.with_repo_topics({"testing.md": "## [2026-05-01] S-OLDFMT — Flyway checksum mismatch\n"
                                             "- **재발 방지 규칙**: Flyway 마이그레이션 파일은 수정하지 않는다\n"})
        _, out = self.run_lookup("--query", "Flyway checksum mismatch 마이그레이션")
        self.assertIn("S-OLDFMT", out)
        self.assertIn("(옛 형식 — 칸 없음)", out)

    def test_level3_entries_under_topic_sections_are_read(self):
        """옛 저장소는 `## 분류` 아래 `### [날짜]` 로 항목을 적었다 — 이 형식도 읽어야 한다."""
        self.with_repo_topics({"git_commit.md": textwrap.dedent("""\
            # Git·커밋 오류
            ## 커밋 메시지
            ### [2026-03-31] 자동 생성 커밋 메시지가 영어로 작성됨
            - **재발 방지 규칙**: 커밋 메시지는 한국어 Conventional Commits 로 쓴다
            ### [2026-04-02] 상위 AGENTS.md 임의 수정
            - **재발 방지 규칙**: 상위 진입 문서는 고치지 않는다
            ## 기타
            설명 문단
            """)})
        _, out = self.run_lookup("--query", "커밋 메시지 영어")
        self.assertIn("영어로 작성됨", out)
        self.assertIn("항목 2건", out)
        self.assertIn("한국어 Conventional Commits", out)

    def test_same_lesson_copied_to_sibling_repos_is_shown_once(self):
        body = entry("2026-03-31", "S-C", "자동 생성 커밋 메시지가 영어로 작성됨",
                     rule="커밋 메시지는 한국어로 쓴다")
        self.with_repo_topics({"git_commit.md": body})
        self.write("web/docs/rules/error_topics/git_commit.md", body)
        _, out = self.run_lookup("--query", "커밋 메시지 영어")
        shown = [l for l in out.splitlines() if l.startswith("- [")]
        self.assertEqual(len(shown), 1, out)
        self.assertIn("2곳", shown[0], out)

    def test_error_topics_path_takes_precedence(self):
        self.write("plans/.claude/harness-answers.yml", "error_topics_path: .claude/error_topics\n")
        self.write("plans/.claude/error_topics/gate_process.md",
                   entry("2026-10-15", "S-G", "구현 한마디로 Gate B 건너뜀", when="Gate B 질문 대기 중 「구현」 입력",
                         rule="질문에 답하거나 스킵을 명시"))
        self.write("plans/SESSION_INDEX.md", "next_action: Gate B 질문 대기 중 구현 입력 흐름 정리\n")
        _, out = self.run_lookup()
        self.assertIn("저장소 1곳", out)
        self.assertIn("S-G", out)

    def test_no_store_and_bad_inputs_still_exit_zero(self):
        code, out = self.run_lookup()
        self.assertEqual(code, 0)
        self.assertIn("교훈 저장소 없음", out)
        self.write("plans/.claude/harness-answers.yml", "- not\n- a mapping\n")
        code, _ = self.run_lookup(project=os.path.join(self.root, "does-not-exist"))
        self.assertEqual(code, 0)

    def test_unreadable_file_does_not_fail(self):
        self.with_repo_topics({"testing.md": "placeholder"})
        path = os.path.join(self.root, "api/docs/rules/error_topics/testing.md")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\x00 not utf-8 \x80")
        code, out = self.run_lookup()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
