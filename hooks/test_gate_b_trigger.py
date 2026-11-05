"""gate_b_trigger.py 시험 — Gate B 가 질문할 계획인지 경로와 「되돌리는 법」으로 판정한다."""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gate_b_trigger as t  # noqa: E402


def plan(files=(), rollback="이 커밋을 되돌리면 끝난다."):
    listed = "\n".join(f"{i}. `{p}` — 수정" for i, p in enumerate(files, 1))
    return ("## Gate A — 계획\n\n### 이해 브리핑\n- **왜 바꾸나**: 왜\n- **어떻게 동작하나**: 어떻게\n"
            f"- **가장 깨지기 쉬운 곳**: 곳\n- **되돌리는 법**: {rollback}\n\n### 변경 파일\n{listed}\n")


class TestPaths(unittest.TestCase):

    def fires(self, path):
        return bool(t.classify([path], "")["reasons"])

    def test_paths_that_are_hard_to_undo_fire(self):
        for path in ("db/migrations/0012_add.py", "migrations/0001.sql", "prisma/schema.prisma", "alembic/env.py",
                     "sql/seed.sql", "app/schema.py",
                     ".env.production", "src/auth/login.py", "lib/auth_middleware.ts", "api/permissions.py",
                     "services/payment_service.py", "billing/invoice.ts", "core/security/token.py", "rbac/roles.py",
                     "deploy/app.yaml", "k8s/api.yaml", "terraform/main.tf", "helm/values.yaml", "Dockerfile",
                     "docker-compose.yml", ".github/workflows/release.yml"):
            self.assertTrue(self.fires(path), path)

    def test_ordinary_code_does_not_fire(self):
        for path in ("src/components/Button.tsx", "hooks/harness_report.py", "skills/gate-b/SKILL.md", "src/author.py",
                     "lib/authoring/tool.py", "src/deployment_notes.py", "src/schemas_note.txt", "package.json"):
            self.assertFalse(self.fires(path), path)

    def test_docs_and_tests_do_not_fire(self):
        """`SECURITY.md`·`tests/auth/` 는 되돌리기 어려운 변경이 아니다."""
        for path in ("SECURITY.md", "docs/migrations/guide.md", "docs/auth/flow.py", "tests/auth/test_login.py",
                     "__tests__/payment.test.ts", "spec/billing/invoice_spec.rb", "fixtures/migrations/a.sql"):
            self.assertFalse(self.fires(path), path)

    def test_reason_names_the_kind_and_the_path(self):
        self.assertEqual(t.classify(["db/migrations/1.sql", "src/a.py"], "")["reasons"], ["데이터: db/migrations/1.sql"])

    def test_windows_path_and_leading_dot_slash(self):
        self.assertTrue(self.fires("db\\migrations\\1.sql"))
        self.assertTrue(self.fires("./deploy/app.yaml"))


class TestRollbackText(unittest.TestCase):

    def fires(self, text):
        return bool(t.classify([], text)["reasons"])

    def test_statements_that_it_cannot_be_undone_fire(self):
        for text in ("운영 DB 마이그레이션이라 되돌리려면 복원이 필요하다.", "이미 나간 메일은 되돌릴 수 없다.", "복구 불가 — 백업에서만 살린다.",
                     "ALTER TABLE 뒤의 데이터가 남는다.", "This step is irreversible."):
            self.assertTrue(self.fires(text), text)

    def test_ordinary_revert_does_not_fire(self):
        for text in ("이 커밋을 되돌리면 끝난다.", "설정 값을 이전으로 바꾼다.", ""):
            self.assertFalse(self.fires(text), text)

    def test_denials_do_not_fire(self):
        """gate-a 가 「되돌릴 수 없는 것」을 적게 해서 「없다」는 문장이 흔하다."""
        for text in ("되돌릴 수 없는 것은 없다.", "되돌릴 수 없는 변경은 없습니다.", "복구할 수 없는 상태는 남지 않는다.",
                     "마이그레이션은 없다.", "마이그레이션 없음.", "migration 없이 코드만 바뀐다."):
            self.assertFalse(self.fires(text), text)

    def test_denial_does_not_hide_a_real_statement_in_the_same_text(self):
        self.assertTrue(self.fires("마이그레이션은 없다. 다만 이미 나간 메일은 되돌릴 수 없다."))

    def test_word_alone_outside_the_rollback_item_is_not_read(self):
        """계획 전체를 읽으면 사소 회차까지 걸렸다(재현 측정) — 「되돌리는 법」과 변경 파일만 본다."""
        doc = plan(["src/a.py"]).replace("- **왜 바꾸나**: 왜", "- **왜 바꾸나**: 지난번 마이그레이션 이후 생긴 문제")
        self.assertEqual(t.verdict(doc)["state"], "미발동")


class TestVerdict(unittest.TestCase):

    def test_fires_from_the_plan(self):
        v = t.verdict(plan(["src/a.py", "db/migrations/1.sql"]))
        self.assertEqual((v["state"], v["reasons"]), ("발동", ["데이터: db/migrations/1.sql"]))

    def test_rollback_text_alone_fires(self):
        self.assertEqual(t.verdict(plan(["src/a.py"], "이미 나간 메일은 되돌릴 수 없다."))["state"], "발동")

    def test_quiet_plan(self):
        v = t.verdict(plan(["src/a.py", "src/b.py"]))
        self.assertEqual((v["state"], v["files"]), ("미발동", 2))

    def test_files_listed_in_a_table_are_read(self):
        doc = plan().replace("### 변경 파일\n", "### 변경 파일\n| 파일 | 내용 |\n|---|---|\n| `db/migrations/1.sql` | 추가 |\n")
        self.assertEqual(t.verdict(doc)["state"], "발동")

    def test_nothing_to_read_cannot_be_judged(self):
        for doc in ("", "# 메모\n", "## Gate A — 계획\n\n### 이해 브리핑\n- **왜 바꾸나**: 왜\n"):
            self.assertEqual(t.verdict(doc)["state"], "판정 불가", doc)

    def test_broken_input_cannot_be_judged(self):
        self.assertEqual(t.verdict(None)["state"], "판정 불가")


class TestCommandLine(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = t.main(list(argv))
        return rc, out.getvalue().strip()

    def test_prints_one_line_and_exits_zero(self):
        path = os.path.join(self.root, "CURRENT_SESSION.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(plan(["db/migrations/1.sql"]))
        self.assertEqual(self.run_main(path), (0, "발동 — 데이터: db/migrations/1.sql"))

    def test_quiet_plan_says_how_many_files_it_read(self):
        path = os.path.join(self.root, "CURRENT_SESSION.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(plan(["src/a.py"]))
        self.assertEqual(self.run_main(path), (0, "미발동 — 변경 파일 1개, 해당 없음"))

    def test_empty_argument_falls_back_to_the_project_session_file(self):
        """스킬의 `${CURRENT_SESSION_FILE}` 은 셸 변수가 아니다 — 그대로 실행되면 빈 인자가 온다."""
        with open(os.path.join(self.root, "CURRENT_SESSION.md"), "w", encoding="utf-8") as f:
            f.write(plan(["db/migrations/1.sql"]))
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.root
        self.addCleanup(lambda: os.environ.pop("CLAUDE_PROJECT_DIR") if old is None else os.environ.update(CLAUDE_PROJECT_DIR=old))
        self.assertEqual(self.run_main(""), (0, "발동 — 데이터: db/migrations/1.sql"))

    def test_missing_file_does_not_stop_the_gate(self):
        rc, line = self.run_main(os.path.join(self.root, "없음.md"))
        self.assertEqual(rc, 0)
        self.assertTrue(line.startswith("판정 불가 — "), line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
