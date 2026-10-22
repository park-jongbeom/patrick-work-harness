"""harness_report.py 시험 — 대화 기록에서 하네스가 실제로 어떻게 동작했는지 뽑는다.

합성 대화 기록(JSONL)을 임시 projects 폴더에 만들어 넣고 결과를 본다. 기록 형식은 Claude Code 2.1.307 의 실제
대화 기록에서 확인한 것을 따른다(2026-10-22): 훅 실행은 `attachment` 줄(hook_success·hook_system_message 등,
toolUseID·command·stdout·durationMs), 훅의 exit 2 거부는 도구 결과의 「PreToolUse:X hook error: [명령]: …」,
Stop 훅은 `stop_hook_summary`.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness_report as hr  # noqa: E402

GUARD = "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/lane-scope-guard.py\""
TEST_GUARD = "python3 /home/u/.claude/hooks/patrick-work-harness/test-write-guard.py"
SOURCE_GUARD = "python3 \"${CLAUDE_PROJECT_DIR}/../plans/hooks/master-plan-stale-guard.py\""


def user(text, ts="2026-10-23T10:00:00Z", **extra):
    return {"type": "user", "timestamp": ts, "cwd": "/w/proj-a", "message": {"content": text}, **extra}


def assistant(model="claude-sonnet-5-5", tools=(), ts="2026-10-23T10:00:01Z"):
    content = [{"type": "tool_use", "id": tid, "name": name, "input": inp} for tid, name, inp in tools]
    return {"type": "assistant", "timestamp": ts, "message": {"model": model, "content": content or [{"type": "text", "text": "ok"}]}}


def tool_result(tid, text="done", error=False):
    return {"type": "user", "timestamp": "2026-10-23T10:00:02Z",
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]}}


def hook(kind, name, command="", stdout="", content="", tid=None, ms=40):
    att = {"type": kind, "hookName": name, "hookEvent": name.split(":")[0], "command": command,
           "stdout": stdout, "content": content, "durationMs": ms}
    if tid:
        att["toolUseID"] = tid
    return {"type": "attachment", "timestamp": "2026-10-23T10:00:01Z", "attachment": att}


def ask(reason="보호 경로"):
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                              "permissionDecisionReason": reason}}, ensure_ascii=False)


class ReportCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def session(self, lines, project="-w-proj-a", sid="s1"):
        d = os.path.join(self.root, project)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "w", encoding="utf-8") as f:
            for line in lines:
                f.write((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n")

    def rows(self, **kw):
        return {r["session"]: r for r in hr.collect(self.root, **kw)["sessions"]}


class TestUserAndModel(ReportCase):

    def test_counts_only_what_the_user_typed(self):
        self.session([
            user("계획 세워라"),
            user("<command-name>/gate-a</command-name>"),               # 직접 입력한 슬래시 명령 — 센다
            user("Base directory for this skill …", isMeta=True),        # 스킬 본문
            user("요약…", isCompactSummary=True),                       # 압축 요약
            user("<local-command-stdout>ok</local-command-stdout>"),     # 로컬 명령 출력
            tool_result("t1"),                                           # 도구 결과
            user("대조 검증 해달라"),
            assistant("claude-opus-5-5"), assistant("claude-opus-5-5"), assistant("claude-sonnet-5-5"),
        ])
        r = self.rows()["s1"]
        self.assertEqual(r["user_prompts"], 3)
        self.assertEqual(r["cross_check_requests"], 1)
        self.assertEqual(r["models"], {"claude-opus-5-5": 2, "claude-sonnet-5-5": 1})
        self.assertEqual(r["project"], "proj-a")


class TestHookDecisions(ReportCase):

    def test_ask_outcome_is_joined_by_tool_use_id(self):
        self.session([
            assistant(tools=[("t1", "Edit", {}), ("t2", "Edit", {})]),
            hook("hook_success", "PreToolUse:Edit", GUARD, ask(), tid="t1", ms=120),
            tool_result("t1", "edited"),                                   # 허용
            hook("hook_success", "PreToolUse:Edit", GUARD, ask(), tid="t2", ms=180),
            tool_result("t2", "The user doesn't want to proceed", error=True),   # 거부
        ])
        g = self.rows()["s1"]["guards"]["lane-scope-guard.py"]
        self.assertEqual(g["ask"], 2)
        self.assertEqual(g["ask_allowed"], 1)
        self.assertEqual(g["ask_denied"], 1)
        self.assertEqual((g["ms_median"], g["ms_max"]), (150, 180))

    def test_exit2_deny_is_read_from_the_tool_result(self):
        self.session([
            assistant(tools=[("t1", "Bash", {"command": "git commit -m x"})]),
            tool_result("t1", "PreToolUse:Bash hook error: [python3 /h/hooks/commit-msg-guard.py]: 형식 위반", error=True),
        ])
        self.assertEqual(self.rows()["s1"]["guards"]["commit-msg-guard.py"]["deny"], 1)

    def test_json_deny_with_stop_and_block(self):
        stop = json.dumps({"continue": False, "stopReason": "범위", "hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "범위"}})
        self.session([
            assistant(tools=[("t1", "Skill", {"skill": "gate-e"})]),
            hook("hook_success", "PreToolUse:Skill", GUARD, stop, tid="t1"),
            hook("hook_success", "UserPromptExpansion", GUARD, json.dumps({"decision": "block", "reason": "x"})),
        ])
        g = self.rows()["s1"]["guards"]["lane-scope-guard.py"]
        self.assertEqual((g["deny"], g["stop"], g["block"]), (1, 1, 1))

    def test_silent_success_is_not_a_firing(self):
        self.session([hook("hook_success", "PreToolUse:Edit", GUARD, "", tid="t9")])
        self.assertEqual(self.rows()["s1"]["guards"].get("lane-scope-guard.py", {}).get("fired", 0), 0)

    def test_repeated_notice_is_measured(self):
        msg = "[COMPREHENSION-LEDGER-STALE] 이해도 ledger 만료 항목 24건 — 재검증 권장"
        self.session([hook("hook_system_message", "Stop", "", content=msg) for _ in range(5)]
                     + [hook("hook_system_message", "Stop", "", content="[GATE-E-SYNC] 다른 알림")])
        r = self.rows()["s1"]
        self.assertEqual(r["max_repeat_notice"]["count"], 5)
        self.assertTrue(r["max_repeat_notice"]["text"].startswith("[COMPREHENSION-LEDGER-STALE]"))
        self.assertEqual(r["guards"]["COMPREHENSION-LEDGER-STALE"]["notice"], 5)

    def test_list_shaped_attachment_content(self):
        """실제 기록에서 알림 content 가 문자열이 아니라 블록 목록인 경우가 있었다(2026-10-22 첫 실행에서 발견)."""
        self.session([hook("hook_system_message", "Stop", "", content=[{"type": "text", "text": "[GATE-E-SYNC] 알림"}]),
                      {"type": "attachment", "attachment": {"type": "hook_success", "hookName": "Stop", "stdout": ["x"]}}])
        self.assertEqual(self.rows()["s1"]["guards"]["GATE-E-SYNC"]["notice"], 1)

    def test_one_broken_session_does_not_stop_the_report(self):
        self.session([user("ok")], sid="good")
        self.session([{"type": "attachment", "attachment": {"type": "hook_success", "hookName": 7, "command": 3}}], sid="odd")
        data = hr.collect(self.root)
        self.assertIn("good", {r["session"] for r in data["sessions"]})

    def test_auto_mode_and_safety_check_denials(self):
        self.session([
            tool_result("a", "Permission for this action was denied by the Claude Code auto mode classifier. Reason: x", error=True),
            tool_result("b", "Permission for this command was denied by a built-in Claude Code safety check, not by the user.", error=True),
        ])
        r = self.rows()["s1"]
        self.assertEqual((r["auto_mode_denials"], r["safety_check_denials"]), (1, 1))


class TestEngineSourceAndGates(ReportCase):

    def test_engine_source_from_hook_paths(self):
        self.session([hook("hook_success", "PreToolUse:Edit", GUARD, "")], sid="p")
        self.session([hook("hook_success", "PreToolUse:Edit", TEST_GUARD, "")], sid="i")
        self.session([{"type": "system", "subtype": "stop_hook_summary", "hookInfos": [{"command": SOURCE_GUARD, "durationMs": 50}]}], sid="s")
        self.session([user("안녕")], sid="n")
        r = self.rows()
        self.assertEqual([r[k]["engine_source"] for k in ("p", "i", "s", "n")],
                         [["plugin"], ["install.sh"], ["source-copy"], []])

    def test_gate_sequence_skills_and_c_to_e(self):
        self.session([
            assistant(tools=[("t1", "Skill", {"skill": "patrick-work-harness:gate-a"})]),
            user("<command-name>/gate-c</command-name>"),
            assistant(tools=[("t2", "Skill", {"skill": "gate-e"}), ("t3", "Skill", {"skill": "audit"})]),
        ])
        r = self.rows()["s1"]
        self.assertEqual(r["gates"], "a c e")
        self.assertEqual(r["c_to_e"], 1)
        self.assertEqual(r["skills"]["audit"], 1)


class TestCollection(ReportCase):

    def test_tmp_projects_are_excluded_unless_asked(self):
        self.session([user("x")], project="-tmp-s8c-canary")
        self.session([user("y")])
        self.assertEqual(set(self.rows()), {"s1"})
        self.assertEqual(len(hr.collect(self.root, include_tmp=True)["sessions"]), 2)

    def test_since_filters_by_last_activity(self):
        self.session([user("old", ts="2026-09-01T00:00:00Z")], sid="old")
        self.session([user("new", ts="2026-10-23T00:00:00Z")], sid="new")
        self.assertEqual(set(self.rows(since="2026-10-01")), {"new"})

    def test_unreadable_lines_are_counted_not_fatal(self):
        self.session(["{not json", user("ok")])
        data = hr.collect(self.root)
        self.assertEqual(data["bad_lines"], 1)
        self.assertEqual(data["sessions"][0]["user_prompts"], 1)


class TestPredictionsAndOutput(ReportCase):

    DECISION_LOG = """# 결정 기록

### [2026-10-22] 레인 범위 가드는 쓰기 전에 묻고 Gate E 에서 실제 diff 로 막는다 — 확인할 수 없으면 막는다
- **예측**: 확인 창 10회 중 오탐 …
- **확인 시점**: 확인 창 10회
- **결과**:

### [2026-10-21] 엔진 배포 파일 일관성을 시험으로 묶는다
- **확인 시점**: 3회 릴리스 뒤
- **결과**:

### [2026-10-20] 끝난 결정
- **결과**: 확인됨
"""

    def test_pending_predictions_are_mapped_or_listed_as_uncountable(self):
        self.session([assistant(tools=[("t1", "Edit", {})]),
                      hook("hook_success", "PreToolUse:Edit", GUARD, ask(), tid="t1"), tool_result("t1")])
        path = os.path.join(self.root, "DECISION_LOG.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.DECISION_LOG)
        data = hr.collect(self.root)
        preds = hr.prediction_progress(path, data["sessions"])
        self.assertEqual(len(preds), 2)                       # 결과가 찬 항목은 빼고 대기 항목만
        lane = next(p for p in preds if p["title"].startswith("레인 범위 가드"))
        self.assertEqual((lane["countable"], lane["count"], lane["target"]), (True, 1, 10))
        lint = next(p for p in preds if p["title"].startswith("엔진 배포 파일"))
        self.assertFalse(lint["countable"])
        self.assertTrue(lint["source"])

    def test_report_files_are_written_outside_and_flag_empty_input(self):
        out = tempfile.mkdtemp()                  # 읽는 폴더 밖 — 안에 두면 자기 출력을 대화 기록으로 읽는다
        self.addCleanup(shutil.rmtree, out, True)
        rc = hr.main(["--projects-dir", self.root, "--out", out])
        self.assertEqual(rc, 0)
        md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
        self.assertIn("세션 0개", md)
        self.assertIn("형식 확인 필요", md)
        self.session([user("x")])
        hr.main(["--projects-dir", self.root, "--out", out])
        rows = [json.loads(l) for l in open(os.path.join(out, "sessions.jsonl"), encoding="utf-8")]
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
