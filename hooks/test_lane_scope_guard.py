"""lane-scope-guard.py 시험 — 자율 레인 세션이 계획 범위를 벗어나면 쓰기 전에 묻고, Gate E 진입을 거부한다.

임시 git 저장소에 기준 커밋을 만들고, 계획(CURRENT_SESSION.md)과 대화 기록을 꾸며 훅을 실제로 실행한다.
카나리아 5종(보호 경로 편집, 계획 밖 파일, 기존 시험 수정, 의존성 추가, 기준 커밋 재작성)이 모두 걸려야
완료다(적용 계획 S7).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lane-scope-guard.py")

ANSWERS = """project: "t"
archive_path: "docs/archive"
autonomous_lane:
  enabled: true
  max_files: 5
  hard_max_lines: 400
  protected_paths: ["config/*.yml"]
"""

PLAN = """# 현재 세션 상태

> **세션 ID**: T-LANE

## Gate A 계획

### 이해 브리핑

- **왜 바꾸나**: 슬러그 함수가 공백을 남긴다.

### 레인 판정
- **레인**: 자율
- **걸린 트리거**: 없음
- **기준 커밋**: `{base}`
- **수락 명령**: `python3 -m pytest tests/test_slug.py -q`

### 변경 파일 ({n}개)

{files}

## Gate D 검증

- self-debug 0회 · FIX-B 0건 · DEP 0건
"""

PLANNED = ["src/slug.py", "tests/test_slug.py"]


def sh(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def gate_a_call():
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "gate-a"}}]}}


def user(text, **extra):
    return {"type": "user", "message": {"content": text}, **extra}


APPROVED = [gate_a_call(), user("자율 레인 승인")]


class LaneGuardCase(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        sh(self.repo, "init", "-q")
        sh(self.repo, "config", "user.email", "t@t")
        sh(self.repo, "config", "user.name", "t")
        self.write("src/slug.py", "def slug(s):\n    return s\n")
        self.write("src/other.py", "x = 1\n")
        self.write("tests/test_old.py", "def test_old():\n    assert True\n")
        self.write("requirements.txt", "pytest\n")
        self.write("migrations/001.sql", "create table t (id int);\n")
        self.write(".claude/harness-answers.yml", ANSWERS)
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", "base")
        self.base = sh(self.repo, "rev-parse", "--short", "HEAD")
        self.set_plan(PLANNED)

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def set_plan(self, files, base=None):
        listing = "\n".join(f"{i}. `{p}` (수정)" for i, p in enumerate(files, 1))
        self.write("CURRENT_SESSION.md", PLAN.format(base=base or self.base, n=len(files), files=listing))

    def implement(self):
        """계획대로 고친 정상 상태."""
        self.write("src/slug.py", "def slug(s):\n    return s.strip().replace(' ', '-')\n")
        self.write("tests/test_slug.py", "from src.slug import slug\n\ndef test_slug():\n    assert slug(' a b ') == 'a-b'\n")

    def run_hook(self, payload, transcript=APPROVED):
        tpath = os.path.join(self.repo, ".git", "transcript.jsonl")   # 저장소 diff 에 안 잡히는 곳
        with open(tpath, "w", encoding="utf-8") as f:
            for line in transcript:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        payload = dict(payload, transcript_path=tpath)
        env = {**os.environ, "LANE_SCOPE_GUARD_BASE": self.repo, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run([sys.executable, SCRIPT], input=json.dumps(payload), capture_output=True,
                              text=True, encoding="utf-8", env=env)
        out = proc.stdout.strip()
        return proc.returncode, (json.loads(out) if out else None)

    def gate_e(self, transcript=APPROVED):
        return self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                              "tool_input": {"skill": "gate-e"}}, transcript)

    def edit(self, rel, transcript=APPROVED):
        return self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                              "tool_input": {"file_path": os.path.join(self.repo, rel)}}, transcript)

    def assertDenied(self, result, needle):
        rc, out = result
        self.assertEqual(rc, 0)
        self.assertIsNotNone(out, "거부해야 하는데 아무것도 내지 않음")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIs(out["continue"], False)
        self.assertIn(needle, out["hookSpecificOutput"]["permissionDecisionReason"])

    def assertAsked(self, result, needle):
        rc, out = result
        self.assertIsNotNone(out, "확인을 물어야 하는데 아무것도 내지 않음")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn(needle, out["hookSpecificOutput"]["permissionDecisionReason"])

    def assertPassed(self, result):
        rc, out = result
        self.assertEqual(rc, 0)
        self.assertTrue(out is None or "hookSpecificOutput" not in out, out)


class TestCanaries(LaneGuardCase):
    """적용 계획 S7 의 완료 판정 — 다섯 가지 모두 걸려야 한다."""

    def test_canary_protected_path_edit_asks_before_writing(self):
        self.assertAsked(self.edit("migrations/001.sql"), "migrations/001.sql")
        self.assertAsked(self.edit("config/app.yml"), "config/app.yml")      # 설정의 추가 보호 경로

    def test_canary_file_outside_plan_is_denied_at_gate_e(self):
        self.implement()
        self.write("src/other.py", "x = 2\n")
        self.assertDenied(self.gate_e(), "src/other.py")

    def test_canary_existing_test_modified(self):
        self.assertAsked(self.edit("tests/test_old.py"), "tests/test_old.py")
        self.implement()
        self.write("tests/test_old.py", "def test_old():\n    pass\n")
        self.set_plan(PLANNED + ["tests/test_old.py"])   # 계획에 적어도 기존 시험은 안 된다
        self.assertDenied(self.gate_e(), "tests/test_old.py")

    def test_canary_dependency_added_through_bash_is_denied(self):
        """Bash 로 쓴 변경은 편집 훅에 안 보인다 — Gate E 의 실제 diff 가 잡는다."""
        self.implement()
        self.write("requirements.txt", "pytest\nrequests\n")
        self.set_plan(PLANNED + ["requirements.txt"])
        self.assertDenied(self.gate_e(), "requirements.txt")

    def test_canary_base_commit_rewritten(self):
        self.implement()
        sh(self.repo, "commit", "-q", "--amend", "-m", "base (rewritten)")
        self.assertDenied(self.gate_e(), "기준 커밋")


class TestGateE(LaneGuardCase):

    def test_planned_change_passes_with_a_summary(self):
        self.implement()
        rc, out = self.gate_e()
        self.assertPassed((rc, out))
        self.assertIn("자율 레인 범위 확인 통과", out["systemMessage"])

    def test_session_docs_and_configured_doc_paths_are_exempt(self):
        self.implement()
        self.write("SESSION_INDEX.md", "# i\n")
        self.write("docs/archive/2026-10-22.md", "# 기록\n")
        self.assertPassed(self.gate_e())

    def test_rename_out_of_protected_path_is_caught_on_the_old_side(self):
        self.implement()
        sh(self.repo, "mv", "migrations/001.sql", "src/schema.sql")
        self.set_plan(PLANNED + ["src/schema.sql"])
        self.assertDenied(self.gate_e(), "migrations/001.sql")

    def test_default_harness_doc_paths_are_exempt(self):
        """설정에 경로 키가 없으면 훅은 기본 경로에 쓴다(skill-usage-auto 등) — 그것도 하네스 문서다(S8c 실사용에서 발견)."""
        self.implement()
        self.write("plans/process_evolution/skill_usage_2026-10.md", "# 사용 기록\n")
        self.write("plans/learning/comprehension_ledger.md", "# 원장\n")
        self.assertPassed(self.gate_e())

    def test_gate_e_without_a_gate_d_record_is_denied_without_stopping(self):
        """Gate D 를 건너뛰면 막되 세션은 멈추지 않는다 — /gate-d 를 돌리면 풀리는 절차 누락이다(S8c 실사용에서 발견)."""
        self.implement()
        with open(os.path.join(self.repo, "CURRENT_SESSION.md"), encoding="utf-8") as f:
            doc = f.read().split("## Gate D 검증")[0]
        self.write("CURRENT_SESSION.md", doc)
        rc, out = self.gate_e()
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("/gate-d", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertNotIn("continue", out)

    def test_gate_d_block_without_markers_is_not_a_record(self):
        self.implement()
        with open(os.path.join(self.repo, "CURRENT_SESSION.md"), encoding="utf-8") as f:
            doc = f.read().replace("- self-debug 0회 · FIX-B 0건 · DEP 0건", "- 시험 통과")
        self.write("CURRENT_SESSION.md", doc)
        self.assertIn("/gate-d", self.gate_e()[1]["hookSpecificOutput"]["permissionDecisionReason"])

    def test_too_many_files(self):
        files = [f"src/m{i}.py" for i in range(6)]
        for p in files:
            self.write(p, "x = 1\n")
        self.set_plan(files)
        self.assertDenied(self.gate_e(), "파일 6개")

    def test_new_test_files_do_not_count_toward_the_file_limit(self):
        files = [f"src/m{i}.py" for i in range(5)] + ["tests/test_m.py"]
        for p in files:
            self.write(p, "x = 1\n")
        self.set_plan(files)
        self.assertPassed(self.gate_e())

    def test_too_many_lines(self):
        self.implement()
        self.write("src/slug.py", "x = 1\n" * 401)
        self.assertDenied(self.gate_e(), "줄")

    def test_two_top_level_modules(self):
        self.write("src/slug.py", "x = 2\n")
        self.write("lib/util.py", "y = 1\n")
        self.set_plan(["src/slug.py", "lib/util.py"])
        self.assertDenied(self.gate_e(), "최상위")

    def test_typed_gate_e_is_blocked_too(self):
        self.write("src/other.py", "x = 2\n")
        rc, out = self.run_hook({"hook_event_name": "UserPromptExpansion",
                                 "command_name": "gate-e", "prompt": "/gate-e"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("src/other.py", out["reason"])


class TestFailClosed(LaneGuardCase):
    """승인은 있는데 확인할 수 없으면 막는다 — 자율 레인이 조용히 열리면 안 된다."""

    def test_unreadable_lane_block_is_denied(self):
        self.implement()
        self.set_plan(PLANNED, base="HEAD")
        self.assertDenied(self.gate_e(), "레인 판정")

    def test_lane_must_be_enabled_at_the_base_commit(self):
        sh(self.repo, "rm", "-q", ".claude/harness-answers.yml")
        sh(self.repo, "commit", "-q", "-m", "no answers")
        self.base = sh(self.repo, "rev-parse", "--short", "HEAD")
        self.set_plan(PLANNED)
        self.write(".claude/harness-answers.yml", ANSWERS)   # 작업 트리에서만 켠다 — 인정 안 됨
        self.implement()
        self.assertDenied(self.gate_e(), "enabled")

    def test_not_a_git_repository(self):
        shutil.rmtree(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, ".git"))     # 대화 기록 자리만 남긴다
        self.assertDenied(self.gate_e(), "확인 불가")


class TestLaneSettings(unittest.TestCase):
    """설정 읽기 — 틀린 YAML 은 아니지만 읽지 못하던 두 경우(S8c, 2026-10-22)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("lane_guard_mod", SCRIPT)
        cls.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.guard)

    def test_comment_after_the_block_key(self):
        """`autonomous_lane:  # 설명` 은 정상 YAML — 읽지 못하면 레인이 꺼진 것으로 보인다."""
        cfg = self.guard.lane_settings("autonomous_lane:   # gate-a §0-Lane\n  enabled: true\n")
        self.assertTrue(cfg["enabled"])

    def test_max_lines_is_read(self):
        cfg = self.guard.lane_settings("autonomous_lane:\n  enabled: true\n  max_lines: 120\n")
        self.assertEqual(cfg["max_lines"], 120)

    def test_defaults_when_block_is_absent(self):
        cfg = self.guard.lane_settings("project: t\n")
        self.assertEqual((cfg["enabled"], cfg["max_files"], cfg["max_lines"], cfg["hard_max_lines"]),
                         (False, 5, 200, 400))


class TestInactive(LaneGuardCase):
    """자율 레인이 아니면 아무것도 하지 않는다 — 검토 레인의 정상 작업을 막지 않는다."""

    def test_no_approval_means_review_lane(self):
        self.write("src/other.py", "x = 2\n")
        review = [gate_a_call(), user("Gate A 승인")]
        self.assertEqual(self.gate_e(review), (0, None))
        self.assertEqual(self.edit("migrations/001.sql", review), (0, None))

    def test_approval_for_an_earlier_plan_does_not_carry_over(self):
        self.write("src/other.py", "x = 2\n")
        self.assertEqual(self.gate_e(APPROVED + [gate_a_call()]), (0, None))

    def test_skill_body_and_compact_summary_are_not_approval(self):
        self.write("src/other.py", "x = 2\n")
        transcript = [gate_a_call(),
                      user("「자율 레인 승인」 approves an autonomous-lane plan", isMeta=True),
                      user("요약: 사용자가 자율 레인 승인이라고 답함", isCompactSummary=True)]
        self.assertEqual(self.gate_e(transcript), (0, None))

    def test_phrase_inside_a_system_tag_is_not_approval(self):
        self.write("src/other.py", "x = 2\n")
        transcript = [gate_a_call(), user("<system-reminder>자율 레인 승인</system-reminder> 계속")]
        self.assertEqual(self.gate_e(transcript), (0, None))

    def test_other_skills_and_tools_are_ignored(self):
        self.write("src/other.py", "x = 2\n")
        self.assertEqual(self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                        "tool_input": {"skill": "gate-d"}}), (0, None))
        self.assertEqual(self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                        "tool_input": {"command": "ls"}}), (0, None))

    def test_garbage_stdin_is_ignored(self):
        proc = subprocess.run([sys.executable, SCRIPT], input="not json", capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
