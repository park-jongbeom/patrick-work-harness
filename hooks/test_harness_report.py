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


def said(text):
    return {"type": "assistant", "timestamp": "2026-10-23T10:00:01Z",
            "message": {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": text}]}}


def gate(letter):
    return assistant(tools=[("g" + letter, "Skill", {"skill": "gate-" + letter})])


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
        self.assertEqual(r["guards"]["comprehension-ledger-stale-guard.py"]["notice"], 5)   # 꼬리표 → 그 훅 파일
        self.assertEqual(r["max_repeat_notice"]["owner"], "comprehension-ledger-stale-guard.py")

    def test_repeated_notice_of_another_hook_names_that_hook(self):
        other = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/verify_gate.py"'
        self.session([hook("hook_system_message", "Stop", other, content="[검증 게이트] 문서 1개(01_고객사_보고서.md)")] * 3)
        self.assertEqual(self.rows()["s1"]["max_repeat_notice"]["owner"], "verify_gate.py")

    def test_report_shows_the_owner_when_the_text_was_not_sent(self):
        path = os.path.join(self.root, "sent.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"session": "s1", "project": "p", "last": "2026-11-10T00:00:00Z", "first": "", "guards": {},
                                "models": {}, "skills": {}, "special": {}, "gates": "", "engine_source": [],
                                "user_prompts": 0, "cross_check_requests": 0, "auto_mode_denials": 0,
                                "safety_check_denials": 0, "context": {},
                                "max_repeat_notice": {"count": 4, "text": "", "owner": "verify_gate.py"}}) + "\n")
        out = os.path.join(self.root, "out")
        hr.main(["--sessions", path, "--out", out])
        with open(os.path.join(out, "report.md"), encoding="utf-8") as f:
            self.assertIn("4회 — (verify_gate.py 의 알림 — 문구는 보내지 않았다)", f.read())

    def test_list_shaped_attachment_content(self):
        """실제 기록에서 알림 content 가 문자열이 아니라 블록 목록인 경우가 있었다(2026-10-22 첫 실행에서 발견)."""
        self.session([hook("hook_system_message", "Stop", "", content=[{"type": "text", "text": "[GATE-E-SYNC] 알림"}]),
                      {"type": "attachment", "attachment": {"type": "hook_success", "hookName": "Stop", "stdout": ["x"]}}])
        self.assertEqual(self.rows()["s1"]["guards"]["gate-e-sync-guard.py"]["notice"], 1)

    def test_notice_tag_joins_its_hook_row(self):
        """Stop 알림에는 명령이 안 남아 꼬리표로만 보인다 — 같은 훅의 실행 시간 행과 한 줄로 합친다(2026-10-28 대조 검증:
        두 줄로 나뉘어 훅 수를 잘못 셌다). 엔진 훅이 내지 않는 꼬리표는 그대로 둔다."""
        stale = "python3 /home/u/.claude/hooks/patrick-work-harness/comprehension-ledger-stale-guard.py"
        self.session([hook("hook_system_message", "Stop", "", content="[COMPREHENSION-LEDGER-STALE] 만료 1건"),
                      {"type": "system", "subtype": "stop_hook_summary", "hookInfos": [{"command": stale, "durationMs": 300}]},
                      hook("hook_system_message", "Stop", "", content="[OTHER-TOOL] 남의 알림")])
        g = self.rows()["s1"]["guards"]
        self.assertEqual(g["comprehension-ledger-stale-guard.py"], {"notice": 1, "fired": 1, "ms_median": 300, "ms_max": 300})
        self.assertNotIn("COMPREHENSION-LEDGER-STALE", g)
        self.assertEqual(g["OTHER-TOOL"]["notice"], 1)

    def test_every_engine_notice_tag_has_one_owner(self):
        self.assertEqual(hr.NOTICE_OWNERS.get("DOCKER-GUARD"), "docker-command-guard.py")
        self.assertEqual(hr.NOTICE_OWNERS.get("GATE-A-SYNC"), "gate-a-sync-guard.py")
        self.assertTrue(all(v in hr.ENGINE_HOOKS for v in hr.NOTICE_OWNERS.values()))

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


def call(mid, ctx, out=100, stop="end_turn", model="claude-sonnet-5-5"):
    """응답 한 번 — 실제 기록처럼 내용 블록마다 줄이 나뉘고 같은 message.id·usage 가 되풀이된다."""
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": ctx - 2, "output_tokens": out}
    return {"type": "assistant", "timestamp": "2026-10-23T10:00:01Z",
            "message": {"id": mid, "model": model, "usage": usage, "stop_reason": stop,
                        "content": [{"type": "text", "text": "ok"}]}}


def skill_body(name):
    return {"type": "user", "isMeta": True, "timestamp": "2026-10-23T10:00:02Z",
            "message": {"content": [{"type": "text", "text": f"Base directory for this skill: /w/.claude/skills/{name}\n\n# 절차"}]}}


class TestContextCost(ReportCase):

    def test_skill_load_jump_share_and_output_limit_stops(self):
        self.session([user("시작"), call("m1", 30000), call("m1", 30000),   # 같은 응답의 두 줄은 한 번으로 센다
                      user("<command-name>/gate-a</command-name>"), skill_body("gate-a"),
                      call("m2", 46000), call("m3", 47000, stop="max_tokens"),
                      skill_body("deep-research"), call("m4", 57000)])       # 하네스 밖 스킬은 몫에 넣지 않는다
        c = self.rows()["s1"]["context"]
        self.assertEqual((c["calls"], c["first"], c["max"], c["max_tokens_stops"]), (4, 30000, 57000, 1))
        self.assertEqual(c["input_total"], 30000 + 46000 + 47000 + 57000)
        self.assertEqual(c["skill_loads"], {"gate-a": [16000], "deep-research": [10000]})
        self.assertEqual(c["harness_skill_tokens"], 16000 * 3)              # 적재 뒤 호출 3번 동안 실려 있다

    def test_sidechain_and_synthetic_calls_are_not_counted(self):
        side = call("m9", 99000)
        side["isSidechain"] = True
        self.session([call("m1", 20000), side, call("m2", 21000, model="<synthetic>")])
        c = self.rows()["s1"]["context"]
        self.assertEqual((c["calls"], c["max"]), (1, 20000))

    def test_harness_skill_names_match_the_engine(self):
        skills = os.path.join(os.path.dirname(HERE), "skills")
        self.assertEqual(hr.HARNESS_SKILLS, {d for d in os.listdir(skills) if os.path.isdir(os.path.join(skills, d))})

    def test_report_has_context_cost_section(self):
        self.session([user("시작"), call("m1", 30000), skill_body("gate-b"), call("m2", 34000)])
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        hr.main(["--projects-dir", self.root, "--out", out])
        md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
        self.assertIn("## 문맥 비용", md)
        # 응답 · 첫 응답 · 응답당 평균 · 최대 · 압축(자동/수동) · Gate A 회차 · 이월 · 새 대화 절감 · 적재 · 몫 · 출력 한도
        self.assertIn("| proj-a | `s1` | 2 | 30000 | 32000 | 34000 | 0/0 | 0 | — | 0% | gate-b 4000 | 6% | 0 |", md)


class TestComprehensionSkipped(ReportCase):

    def test_a_then_c_without_b_is_counted_per_session(self):
        """Gate A 다음 Gate B 없이 Gate C — 사용 집계기의 「이해도 생략(a→c)」과 같은 기준으로 센다 (2026-10-29)."""
        rows = [{"gates": "a c d e"}, {"gates": "a b c d e"}, {"gates": "a b c a c"}, {"gates": ""}, {"gates": "b c"}]
        self.assertEqual(hr._a_to_c(rows), 2)


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


class TestStopBlocks(ReportCase):
    """Stop 가드의 차단 — exit 2 는 `stop_hook_summary.hookErrors` 의 `[명령]: 메시지` 로만 남고, JSON 차단은 `hook_blocking_error`
    첨부로 남는다. 실행 실패는 hookErrors 와 `hook_non_blocking_error` 첨부 양쪽에 남는다(2026-11-05 실제 기록에서 확인)."""

    GUARD = "python3 /h/hooks/gate-e-sync-guard.py"

    def summary(self, *errors):
        return {"type": "system", "subtype": "stop_hook_summary", "hookInfos": [{"command": self.GUARD, "durationMs": 50}],
                "hookErrors": list(errors), "preventedContinuation": False}

    def test_exit2_block_is_read_from_hook_errors(self):
        self.session([self.summary(f"[{self.GUARD}]: [GATE-E-SYNC] Gate D 기록 없이 ✅E (1/3)")])
        g = self.rows()["s1"]["guards"]["gate-e-sync-guard.py"]
        self.assertEqual((g.get("block"), g.get("fired")), (1, 1))

    def test_failures_are_not_counted_twice(self):
        fail = "Failed with non-blocking status code: /bin/sh: /x/hook.py: No such file or directory"
        self.session([self.summary(fail, "Failed to run: Hook command references ${CLAUDE_PLUGIN_ROOT} …"),
                      hook("hook_non_blocking_error", "Stop", content=fail)])
        guards = self.rows()["s1"]["guards"]
        self.assertEqual(sum(g.get("error", 0) for g in guards.values()), 1)
        self.assertEqual(sum(g.get("block", 0) for g in guards.values()), 0)

    def test_json_block_is_counted_once_and_named(self):
        text = "검증 게이트(tools/verify_gate.py) — 종료 보류 1/2회"
        att = {"type": "attachment", "timestamp": "2026-10-23T10:00:01Z",
               "attachment": {"type": "hook_blocking_error", "hookName": "Stop", "hookEvent": "Stop",
                              "blockingError": {"blockingError": text, "command": ""}}}
        self.session([att, self.summary(text)])
        guards = self.rows()["s1"]["guards"]
        self.assertEqual(guards.get("verify_gate.py", {}).get("block"), 1, guards)
        self.assertEqual(sum(g.get("block", 0) for g in guards.values()), 1)

    def test_tagged_json_block_goes_to_its_hook(self):
        att = {"type": "attachment", "timestamp": "2026-10-23T10:00:01Z",
               "attachment": {"type": "hook_blocking_error", "hookName": "Stop", "hookEvent": "Stop",
                              "blockingError": {"blockingError": "[GATE-E-SYNC] Gate E 미완료 (1/3)"}}}
        self.session([att])
        self.assertEqual(self.rows()["s1"]["guards"]["gate-e-sync-guard.py"]["block"], 1)


class TestSessionsFromElsewhere(ReportCase):
    """노트북에서 만든 sessions.jsonl 을 이 서버의 DECISION_LOG 와 맞댄다 — 대화 기록은 노트북에만 있다(2026-11-05)."""

    def test_report_from_a_sessions_file(self):
        self.session([gate("b"), said(TestGateBRounds.ASKED), user("스킵하고 구현해라"), gate("c")])
        laptop = os.path.join(self.root, "laptop-out")
        hr.main(["--projects-dir", self.root, "--out", laptop])
        log = os.path.join(self.root, "DECISION_LOG.md")
        with open(log, "w", encoding="utf-8") as f:
            f.write("### [2026-10-01] Gate B 스킵은 증거가 아니다 — 시험\n- **결정**: x\n- **결과**:\n")
        here = os.path.join(self.root, "server-out")
        rc = hr.main(["--sessions", os.path.join(laptop, "sessions.jsonl"), "--decision-log", log, "--out", here])
        self.assertEqual(rc, 0)
        md = open(os.path.join(here, "report.md"), encoding="utf-8").read()
        self.assertIn("세션 1개", md)
        self.assertRegex(md, r"\| 2026-10-01 \| Gate B 스킵은 증거가 아니다[^|]*\| 1 \| 20 \|")
        self.assertIn("받은 세션 기록", md)

    def test_missing_sessions_file_is_an_error(self):
        with self.assertRaises(SystemExit):
            hr.main(["--sessions", os.path.join(self.root, "없음.jsonl"), "--out", os.path.join(self.root, "o")])


class TestGateBRounds(ReportCase):
    """호출 순서가 아니라 사람의 응답을 센다 — 2026-10 의 집계기는 스킵이 이어진 달을 「이상 패턴 없음」으로 냈다."""

    ASKED = "**다음 단계**: 위 질문에 답해 주세요. 답하지 않고 넘어가려면 「스킵」이라고 명시해 주세요"
    PASSED = "**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「구현」으로 응답하면 `/gate-c` 가 시작됩니다."

    def rounds(self, lines):
        self.session(lines)
        return self.rows()["s1"]["gate_b"]

    def test_skip_is_counted_though_the_gate_order_looks_normal(self):
        for reply in ("스킵하고 구현해라", "스킴하고 구현해라", "skip"):      # 「스킴」은 실제 기록의 오타
            self.assertEqual(self.rounds([gate("b"), said(self.ASKED), user(reply), gate("c")]), {"skipped": 1}, reply)

    def test_answer_closes_as_answered(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("훅 파일끼리 import 가 되어 일부만 옮기면 깨진다"),
                         said(self.PASSED), user("구현"), gate("c")])
        self.assertEqual(r, {"answered": 1})

    def test_answer_then_skip_on_the_next_question_is_partial(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("훅 파일끼리 import 가 되어 일부만 옮기면 깨진다"),
                         said(self.ASKED), user("스킵하고 구현해라"), gate("c")])
        self.assertEqual(r, {"partial": 1})

    def test_round_without_a_question(self):
        self.assertEqual(self.rounds([gate("b"), said(self.PASSED), user("구현"), gate("c")]), {"none": 1})

    def test_bare_go_word_is_not_an_answer(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("구현"), said(self.ASKED), user("진행"), gate("c")])
        self.assertEqual(r, {"unanswered": 1})
        for reply in ("구현해라", "계획대로 구현", "계획대로 구현해라", "Gate C 시작"):     # gate-b·gate-c 가 받는 문구
            self.assertEqual(self.rounds([gate("b"), said(self.ASKED), user(reply), gate("c")]), {"unanswered": 1}, reply)

    def test_question_written_to_the_session_document_counts_as_asked(self):
        """v1.7.0 전 문구에는 「위 질문에 답해」가 없다 — 평가 자리표시로 본다."""
        written = assistant(tools=[("e1", "Edit", {"file_path": "/w/CURRENT_SESSION.md", "old_string": "x",
                                                   "new_string": "### 질문 1\n무엇?\n- **평가**: (답변 후 기록)\n"})])
        self.assertEqual(self.rounds([gate("b"), written, said(self.PASSED), user("구현"), gate("c")]), {"unanswered": 1})

    def test_question_only_in_the_reply_counts_as_asked(self):
        """v1.7.0 전에는 질문을 대화에만 적은 회차가 있다 — 실제 기록 대조에서 3회가 「질문 없음」으로 잡혔다."""
        r = self.rounds([gate("b"), said("질문 1 — 왜 바꾸나요? 답을 받으면 평가합니다."), user("계획이 틀렸다고 본 이유는 옛 행 때문이다"),
                         said(self.PASSED), gate("c")])
        self.assertEqual(r, {"answered": 1})
        self.assertEqual(self.rounds([gate("b"), said("이해도 질문 없이 통과합니다. 질문 0건."), user("구현"), gate("c")]), {"none": 1})

    def test_later_instruction_after_a_silent_pass_is_not_an_answer(self):
        """맨 「구현」으로 넘어간 뒤의 지시를 답으로 세면 무언 통과가 「답함」이 된다 — 실제 기록 대조에서 나왔다."""
        r = self.rounds([gate("b"), said("질문 1 — 왜 바꾸나요?"), user("구현"), said("구현을 시작합니다."),
                         user("시험도 같이 돌리고 실패하면 고친 뒤 결과를 알려줘"), gate("c")])
        self.assertEqual(r, {"unanswered": 1})

    def test_round_ends_when_the_model_moves_on_without_gate_c(self):
        """Gate C 호출 없이 구현으로 넘어간 회차가 열려 있으면 몇 시간 뒤의 「질문 1」 언급이 대기를 다시 켠다 — 실제 기록 대조."""
        r = self.rounds([gate("b"), said("질문 1 — 왜 바꾸나요?"), user("구현"), said("구현을 시작합니다."), user("검증"),
                         said("Gate B 질문 1 문구를 고쳤습니다."), user("좋다, 그 부분은 그대로 두고 다음 작업으로 넘어가라")])
        self.assertEqual(r, {"unanswered": 1})

    def test_mention_after_a_skip_does_not_turn_it_into_an_answer(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("스킵하고 구현해라"), said("질문 1 은 미답으로 기록했습니다."),
                         user("시험도 같이 돌리고 실패하면 고친 뒤 결과를 알려줘")])
        self.assertEqual(r, {"skipped": 1})

    def test_background_notice_is_not_a_reply(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("<task-notification><task-id>x</task-id></task-notification>"),
                         user("스킵하고 구현해라"), gate("c")])
        self.assertEqual(r, {"skipped": 1})

    def test_script_removing_the_placeholder_does_not_reopen_the_question(self):
        """Bash 스크립트에는 지울 옛 글자도 들어 있다 — 그 자리표시를 새 질문으로 읽으면 다음 입력이 답이 된다(실제 기록 대조)."""
        script = assistant(tools=[("b1", "Bash", {"command": "python3 - <<'EOF'\np='CURRENT_SESSION.md'\n"
                                                             "s=s.replace('- **평가**: (답변 후 기록)','- **평가**: 미답')\nEOF"})])
        r = self.rounds([gate("b"), said("질문 1 — 왜 바꾸나요?"), user("구현"), script, user("검증")])
        self.assertEqual(r, {"unanswered": 1})

    def test_filling_the_evaluation_does_not_reopen_the_question(self):
        filled = assistant(tools=[("e1", "Edit", {"file_path": "/w/CURRENT_SESSION.md", "old_string": "- **평가**: (답변 후 기록)",
                                                  "new_string": "- **평가**: 통과 — 파일을 짚어 답함"})])
        r = self.rounds([gate("b"), said(self.ASKED), user("훅 파일끼리 import 가 되어 일부만 옮기면 깨진다"), filled,
                         said(self.PASSED), user("이제 구현으로 넘어가도 좋고 시험도 같이 돌려라"), gate("c")])
        self.assertEqual(r, {"answered": 1})

    def test_long_answer_mentioning_skip_is_an_answer(self):
        answer = "이 계획은 원장의 스킵 행을 증거로 읽어서, 만료 전이면 큰 폭발반경 변경도 질문 없이 통과하는 것이 가장 깨지기 쉬운 곳이다"
        self.assertEqual(self.rounds([gate("b"), said(self.ASKED), user(answer), said(self.PASSED), gate("c")]), {"answered": 1})

    def test_typed_gate_command_is_not_an_answer(self):
        r = self.rounds([user("<command-name>/gate-b</command-name>"), said(self.ASKED),
                         user("<command-name>/gate-c</command-name>")])
        self.assertEqual(r, {"unanswered": 1})

    def test_each_call_is_its_own_round(self):
        r = self.rounds([gate("b"), said(self.ASKED), user("스킵"), gate("c"), gate("a"),
                         gate("b"), said(self.PASSED), gate("c")])
        self.assertEqual(r, {"skipped": 1, "none": 1})

    def test_session_ending_on_a_pending_question(self):
        self.assertEqual(self.rounds([gate("b"), said(self.ASKED)]), {"unanswered": 1})

    def test_subagent_lines_are_not_the_round(self):
        side = said(self.ASKED)
        side["isSidechain"] = True
        self.assertEqual(self.rounds([gate("b"), side, said(self.PASSED), user("구현"), gate("c")]), {"none": 1})

    def test_plan_change_is_read_from_the_evaluation(self):
        def filled(value):
            return assistant(tools=[("e1", "Edit", {"file_path": "/w/CURRENT_SESSION.md", "old_string": "x",
                                                    "new_string": f"- **평가**: 통과\n- **계획 변경**: {value}\n"})])
        r = self.rounds([gate("b"), said(self.ASKED), user("훅 파일끼리 import 가 되어 일부만 옮기면 깨진다"),
                         filled("있음 — 위험 서술을 고침"), gate("c"),
                         gate("b"), said(self.ASKED), user("훅 파일끼리 import 가 되어 일부만 옮기면 깨진다"),
                         filled("없음"), gate("c")])
        self.assertEqual(r, {"answered": 2, "plan_changed": 1, "plan_same": 1})

    def test_session_without_gate_b_has_no_rounds(self):
        self.assertEqual(self.rounds([gate("a"), gate("c")]), {})

    CONFIRM = ("**다음 단계**: 위 세 줄을 확인하고 「진행」이라고 답하면 구현을 시작합니다. 묻고 싶은 것이나 바꿀 것이 있으면 "
               "그대로 적어 주세요 — 「질문해 줘」라고 하면 이해 확인 질문을 하나 냅니다.")

    def test_report_shows_responses_next_to_gate_order(self):
        self.session([gate("b"), said(self.ASKED), user("스킵하고 구현해라"), gate("c")])
        data = hr.collect(self.root)
        md = hr.render(data, None, self.root, None)
        self.assertIn("## Gate B 질문 결과", md)
        # 질문 없음 · 확인(진행) · 답함 · 일부 답 뒤 스킵 · 스킵 · 답 없음 · 계획 변경
        self.assertRegex(md, r"\| 합계 \|.*\| 0 \| 0 \| 0 \| 0 \| 1 \| 0 \| 0/0 \|")

    def test_confirmation_round_closes_on_a_go_word(self):
        """확인형 Gate B(2026-11-10) — 되돌리기 어려운 변경 앞에서 한 번 멈추고 「진행」 한 마디로 넘어간다. 시험이 아니다."""
        self.assertEqual(self.rounds([gate("b"), said(self.CONFIRM), user("진행"), gate("c")]), {"confirmed": 1})

    def test_confirmation_round_with_a_change_counts_as_engaged(self):
        write = assistant(tools=[("w1", "Edit", {"file_path": "/w/proj-a/CURRENT_SESSION.md", "old_string": "a",
                                                  "new_string": "- **평가**: 확인 — 계획 변경\n- **계획 변경**: 있음 — 운영 반영을 뺐다"})])
        self.assertEqual(self.rounds([gate("b"), said(self.CONFIRM), user("운영 DB 반영은 빼고 개발 DB 에만 하자"), write, gate("c")]),
                         {"answered": 1, "plan_changed": 1})

    def test_question_rounds_feed_the_pending_prediction(self):
        self.assertEqual(hr._gate_b_asked([{"gate_b": {"none": 3, "answered": 1, "partial": 1, "skipped": 2, "unanswered": 1}},
                                           {"gate_b": {}}, {}]), 5)
        self.assertEqual(hr._gate_b_asked([{"gate_b": {"confirmed": 2, "none": 4}}]), 2)   # 확인 회차도 멈춘 회차다


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestFreshReviewTraces(ReportCase):
    """새 문맥 검토(fresh_review.py) 흔적 — 노트북 보고서만으로 시험 운영을 판정한다(2026-11-10)."""

    RUN = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/fresh_review.py" "/w/proj-a/CURRENT_SESSION.md"'
    PROMPT = "[새 문맥 검토] 너는 이 계획을 처음 읽는 검토자다."

    def notice(self, tid, tokens, ms):
        """하위 에이전트가 뒤에서 돌면 사용량은 완료 알림(`queue-operation` 줄)에만 남는다(실제 기록)."""
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-23T10:05:00Z",
                "content": f"<task-notification>\n<task-id>a1</task-id>\n<tool-use-id>{tid}</tool-use-id>\n"
                           f"<status>completed</status>\n<usage><subagent_tokens>{tokens}</subagent_tokens>"
                           f"<tool_uses>8</tool_uses><duration_ms>{ms}</duration_ms></usage>\n</task-notification>"}

    def run_script(self, tid, first_line, force=False):
        return [assistant(tools=[(tid, "Bash", {"command": self.RUN + (" --force" if force else "")})]),
                tool_result(tid, first_line + "\n…")]

    def test_script_outcomes_review_usage_and_records(self):
        sync = tool_result("r1", "## 다시 쓴 계획 …")
        sync["toolUseResult"] = {"status": "completed", "totalTokens": 100000, "totalDurationMs": 360000}
        record = "- **새 문맥 검토**: 지적 3 · 고침 2(내용 1) · 올림 1 · 반박 0"
        self.session(self.run_script("f1", "발동 — R=6") + self.run_script("f2", "발동 — --force", force=True)
                     + self.run_script("f3", "미실행 — 이해도 게이트 미발동 · R=0")
                     + self.run_script("f4", "실패 — 준비하지 못함: OSError: x") + [
            assistant(tools=[("f5", "Bash", {"command": "grep -n x hooks/fresh_review.py"})]), tool_result("f5", "1: x"),
            assistant(tools=[("r1", "Agent", {"subagent_type": "Plan", "prompt": self.PROMPT})]), sync,
            assistant(tools=[("r2", "Agent", {"subagent_type": "Plan", "prompt": self.PROMPT})]),
            tool_result("r2", "Async agent launched successfully."), self.notice("r2", 40000, 180000),
            self.notice("r2", 40000, 180000),                               # 같은 알림이 enqueue·remove 두 줄로 남는다
            assistant(tools=[("x1", "Agent", {"prompt": "다른 일을 맡긴다"})]), tool_result("x1"),
            assistant(tools=[("w1", "Edit", {"file_path": "/w/proj-a/CURRENT_SESSION.md", "old_string": "a",
                                              "new_string": f"미발동 — 해당 없음\n{record}\n"})]),
            assistant(tools=[("w2", "Write", {"file_path": "/w/proj-a/CURRENT_SESSION.md",
                                               "content": f"# 문서\n{record}\n"})]),          # 같은 기록을 다시 쓴 것
            assistant(tools=[("w3", "Write", {"file_path": "/w/x.md",
                                               "content": "- **새 문맥 검토**: 지적 N · 고침 M(내용 X) · 올림 K · 반박 J\n"})]),
        ])
        f = self.rows()["s1"]["fresh_review"]
        self.assertEqual((f["fired"], f["forced"], f["not_run"], f["failed"]), (1, 1, 1, 1))
        self.assertNotIn("unknown", f)                                    # 파일 이름을 grep 한 것은 실행이 아니다
        self.assertEqual(f["reviews"], 2)
        self.assertEqual((sorted(f["tokens"]), sorted(f["ms"])), ([40000, 100000], [180000, 360000]))
        self.assertEqual(f["records"], ["지적 3 · 고침 2(내용 1) · 올림 1 · 반박 0"])   # 자리표시 줄은 기록이 아니다

    def test_blocked_gate_call_is_counted_and_left_out_of_the_order(self):
        self.session([gate("d"), tool_result("gd"),
                      assistant(tools=[("ge", "Skill", {"skill": "patrick-work-harness:gate-e"})]),
                      tool_result("ge", "PreToolUse:Skill hook error: [레인] Gate D 기록 없음", error=True)])
        row = self.rows()["s1"]
        self.assertEqual((row["blocked_gate_calls"], row["gates"]), (1, "d"))

    def test_session_without_review_has_no_entry(self):
        self.session([gate("a"), tool_result("ga")])
        row = self.rows()["s1"]
        self.assertNotIn("fresh_review", row)
        self.assertEqual(row["blocked_gate_calls"], 0)

    def test_report_section_shows_a_fired_run_without_a_record_and_counts_the_prediction(self):
        self.session(self.run_script("f1", "발동 — 이해도 게이트 발동(데이터: db/migrations/1.sql)"))
        log = os.path.join(self.root, "DECISION_LOG.md")
        with open(log, "w", encoding="utf-8") as f:
            f.write("### [2026-10-01] Gate A 계획을 대화 밖 검토자가 다시 써 보게 한다 — 시험\n- **결정**: x\n- **결과**:\n")
        out = os.path.join(self.root, "out")
        hr.main(["--projects-dir", self.root, "--decision-log", log, "--out", out])
        md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
        self.assertIn("## 새 문맥 검토", md)
        self.assertIn("없음(건너뜀?)", md)
        self.assertRegex(md, r"\| 2026-10-01 \| Gate A 계획을 대화 밖 검토자가[^|]*\| 1 \| 10 \|")


def boundary(trigger="auto", pre=0):
    """압축 경계 — 실제 기록(2.1.312~2.1.319)의 system 줄: compactMetadata 에 trigger·preTokens."""
    return {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-10-23T10:00:03Z",
            "content": "Conversation compacted", "compactMetadata": {"trigger": trigger, "preTokens": pre}}


def compact_summary(text="이전 대화 요약"):
    return {"type": "user", "isCompactSummary": True, "timestamp": "2026-10-23T10:00:03Z", "message": {"content": text}}


def reattached(name, chars):
    """자동 압축 뒤 Claude Code 가 다시 붙인 스킬 본문(`invoked_skills` 첨부, 문서상 스킬마다 앞 5,000토큰)."""
    return {"type": "attachment", "timestamp": "2026-10-23T10:00:03Z",
            "attachment": {"type": "invoked_skills", "skills": [{"name": name, "path": "projectSettings:" + name,
                                                                 "content": "x" * chars}]}}


def body(name, chars):
    head = f"Base directory for this skill: /w/.claude/skills/{name}\n\n"
    return {"type": "user", "isMeta": True, "timestamp": "2026-10-23T10:00:02Z",
            "message": {"content": [{"type": "text", "text": head + "x" * (chars - len(head))}]}}


def typed(name):
    return user(f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>")


def loaded_note(name):
    """같은 스킬을 같은 내용으로 다시 부르면 본문 대신 이 한 줄이 붙는다(2.1.312·2.1.319 실제 기록). 본문과 달리
    내용이 목록이 아니라 문자열이다 — 목록으로 만든 첫 시험은 통과했지만 실제 기록 7건을 하나도 세지 못했다."""
    return {"type": "user", "isMeta": True, "timestamp": "2026-10-23T10:00:02Z",
            "message": {"content": f"Skill /{name} is already loaded above; instructions unchanged."}}


def skill_call(tid, name, args=None):
    return [assistant(tools=[(tid, "Skill", {"skill": name, **({"args": args} if args else {})})]),
            tool_result(tid, f"Launching skill: {name}")]


def image_result(tid, count):
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 5000}}
    return {"type": "user", "timestamp": "2026-10-23T10:00:02Z",
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": [image] * count}]}}


class TestContextAccounting(ReportCase):
    """요약이 압축·회차 이월·문맥 출처·스킬 다시 싣기를 센다 — 판단은 노트북 피드백을 받은 뒤에 한다(2026-11-10)."""

    def test_skill_share_stops_at_compaction_and_counts_the_reattached_copy(self):
        self.session([user("시작"), call("m1", 30000), typed("gate-a"), body("gate-a", 32000),
                      call("m2", 46000), call("m3", 47000),
                      boundary("auto", 47000), compact_summary(), reattached("gate-a", 16000),
                      call("m4", 20000), call("m5", 21000)])
        c = self.rows()["s1"]["context"]
        self.assertEqual(c["compactions"], {"auto": 1, "manual": 0, "pre_tokens": [47000]})
        # 본문 16000 토큰(글자 32000 → 글자당 0.5)은 압축 전 응답 2번, 다시 붙은 사본 8000 토큰은 압축 뒤 응답 2번
        self.assertEqual(c["harness_skill_tokens"], 16000 * 2 + 8000 * 2)

    def test_load_right_after_a_compaction_is_estimated_not_negative(self):
        self.session([user("시작"), call("m1", 30000), call("m2", 400000), boundary("auto", 400000),
                      *skill_call("t1", "doc-cleanup"), body("doc-cleanup", 20000), call("m3", 50000), call("m4", 51000)])
        c = self.rows()["s1"]["context"]
        self.assertGreater(c["skill_loads"]["doc-cleanup"][0], 0)    # 50000-400000 은 본문 크기가 아니다
        self.assertGreater(c["harness_skill_tokens"], 0)

    def test_cycle_carry_and_fresh_start_saving(self):
        lines = [user("시작"), call("m1", 30000), typed("gate-a"), body("gate-a", 2000), call("m2", 50000), call("m3", 80000),
                 *skill_call("t2", "gate-a"), loaded_note("gate-a"), call("m4", 90000), call("m5", 100000)]
        self.session(lines)
        c = self.rows()["s1"]["context"]
        self.assertEqual((c["cycles"], c["carry"]), (2, [0, 50000]))
        self.assertEqual(c["fresh_saving"], 50000 + 50000)           # 둘째 회차의 응답 2번이 이월분만큼 덜 실렸을 것
        self.session(lines[:-1] + [boundary("auto", 90000), call("m5", 20000)])
        self.assertEqual(self.rows()["s1"]["context"]["fresh_saving"], 50000)   # 압축 뒤에는 이미 줄었다

    def test_reload_modes_duplicates_and_loaded_notes(self):
        self.session([user("시작"), call("m1", 30000),
                      typed("gate-b"), body("gate-b", 1000), call("m2", 31000),
                      *skill_call("t1", "gate-c"), body("gate-c", 1000), call("m3", 32000),
                      *skill_call("t2", "gate-a", "작업 이름"), body("gate-a", 1000), call("m4", 33000),
                      *skill_call("t3", "gate-b"), loaded_note("gate-b"), call("m5", 33100),
                      typed("gate-c"), body("gate-c", 1000), call("m6", 34000),          # 앞 사본이 아직 문맥에 있다
                      boundary("manual", 34000), typed("gate-c"), body("gate-c", 1000), call("m7", 20000)])
        r = self.rows()["s1"]["context"]["reloads"]
        self.assertEqual(r, {"typed": 3, "tool": 1, "args": 1, "other": 0, "dup": 1, "dup_tokens": 900, "notes": 1})

    def test_sources_are_weighted_by_residency_and_images_are_counted_apart(self):
        self.session([user("시작해"), call("m1", 30000),
                      assistant(tools=[("r1", "Read", {"file_path": "/w/a.py"})]), tool_result("r1", "y" * 1000),
                      call("m2", 31000),
                      assistant(tools=[("r2", "Read", {"file_path": "/w/a.png"})]), image_result("r2", 2),
                      call("m3", 32000),
                      assistant(tools=[("b1", "Bash", {"command": "ls"})]), tool_result("b1", "z" * 500),
                      call("m4", 33000), boundary("manual", 33000), call("m5", 9000)])
        c = self.rows()["s1"]["context"]
        s = c["sources"]
        # 응답 m1 뒤에 들어온 Read 결과는 m2·m3·m4 에 실리고 압축에서 끝난다(m5 에는 없다)
        self.assertEqual((s["tool:Read"], s["tool:Bash"], s["user"]), (1000 * 3, 500 * 1, 3 * 4))
        self.assertEqual(c["images"], {"count": 2, "resident": 2 * 2})
        self.assertNotIn("A" * 100, json.dumps(s))

    def test_pasted_images_are_counted_with_tool_images(self):
        image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 5000}}
        pasted = {"type": "user", "timestamp": "2026-10-23T10:00:00Z", "cwd": "/w/proj-a",
                  "message": {"content": [{"type": "text", "text": "이 화면"}, image]}}
        self.session([pasted, call("m1", 30000), call("m2", 31000)])
        self.assertEqual(self.rows()["s1"]["context"]["images"], {"count": 1, "resident": 2})

    def test_claude_code_versions_are_recorded(self):
        self.session([user("a", version="2.1.319"), call("m1", 30000), user("b", version="2.1.320"),
                      user("c", version="2.1.99")])
        self.assertEqual(self.rows()["s1"]["cc_versions"], ["2.1.99", "2.1.319", "2.1.320"])   # 글자순이 아니라 버전순

    def test_windows_skill_path_is_read_on_any_computer(self):
        """윈도 대화 기록을 이 서버에서 읽으면 `\\` 가 나뉘지 않아 경로 전체가 스킬 이름이 됐다(2026-11-10 실제 기록)."""
        win = {"type": "user", "isMeta": True, "timestamp": "2026-10-23T10:00:02Z",
               "message": {"content": [{"type": "text", "text": "Base directory for this skill: "
                                                                "d:\\Users\\u\\work\\proj\\.claude\\skills\\gate-b\n\n# 절차"}]}}
        self.session([user("시작"), call("m1", 30000), typed("gate-b"), win, call("m2", 34000)])
        c = self.rows()["s1"]["context"]
        self.assertEqual((list(c["skill_loads"]), c["reloads"]["typed"]), (["gate-b"], 1))

    def test_report_shows_the_new_columns_and_sections(self):
        self.session([user("시작"), call("m1", 30000), typed("gate-a"), body("gate-a", 2000), call("m2", 31000),
                      assistant(tools=[("r1", "Read", {"file_path": "/w/a.py"})]), tool_result("r1", "y" * 1000),
                      call("m3", 32000)])
        out = os.path.join(self.root, "out")
        hr.main(["--projects-dir", self.root, "--out", out])
        md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
        self.assertIn("| 압축(자동/수동) |", md)
        self.assertIn("## 문맥 출처", md)
        self.assertRegex(md, r"\| proj-a \| `s1` \|[^\n]*tool:Read \d+%")
        self.assertIn("## 스킬 다시 싣기", md)


def edit(tid, path):
    return [assistant(tools=[(tid, "Edit", {"file_path": path, "old_string": "a", "new_string": "b"})]), tool_result(tid)]


class TestEditTiming(ReportCase):
    """Gate A 승인 전 코드 편집 — 승인 전 편집을 막는 훅을 둘지는 이 수를 보고 정한다(2026-11-10, 외부 평가의 P0)."""

    def test_edits_before_approval_and_outside_the_cycle(self):
        self.session([user("작업하자"), *edit("e0", "/w/proj-a/src/early.py"),             # 회차 밖(Gate A 전)
                      typed("gate-a"), body("gate-a", 500), *edit("e1", "/w/proj-a/src/app.py"),   # 승인 전
                      *edit("e2", "/w/proj-a/CURRENT_SESSION.md"),                         # 계획 문서 — 코드 아님
                      *edit("e3", "C:\\w\\proj-a\\.claude\\settings.json"),       # 하네스 설정 — 코드 아님
                      user("Gate A 승인"), *edit("e4", "/w/proj-a/src/app.py"),            # 승인 뒤
                      *skill_call("t1", "gate-c"), body("gate-c", 300), *edit("e5", "/w/proj-a/src/b.ts"),
                      *skill_call("t2", "gate-e"), body("gate-e", 300), *edit("e6", "/w/proj-a/src/late.kt"),  # 회차 밖(Gate E 뒤)
                      typed("gate-a"), body("gate-a", 500), *skill_call("t3", "gate-c"), body("gate-c", 300),
                      *edit("e7", "/w/proj-a/src/c.py"),                                   # 다음 Gate 호출이 승인 표지
                      assistant(tools=[("b1", "Bash", {"command": "sed -i s/a/b/ src/d.py"})]), tool_result("b1")])
        self.assertEqual(self.rows()["s1"]["edits"],
                         {"code": 6, "pre_approval": 1, "pre_approval_cycles": 1, "outside_cycle": 2})

    def test_session_without_gates_counts_no_outside_edits(self):
        self.session([user("고쳐줘"), *edit("e1", "/w/proj-a/src/app.py")])
        self.assertEqual(self.rows()["s1"]["edits"], {"code": 1, "pre_approval": 0, "pre_approval_cycles": 0,
                                                      "outside_cycle": 0})

    def test_report_has_the_edit_timing_section(self):
        self.session([user("시작"), call("m1", 30000), typed("gate-a"), body("gate-a", 500),
                      *edit("e1", "/w/proj-a/src/app.py"), call("m2", 31000)])
        out = os.path.join(self.root, "out")
        hr.main(["--projects-dir", self.root, "--out", out])
        with open(os.path.join(out, "report.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("## 코드 편집 시점", md)
        self.assertIn("| proj-a | `s1` | 1 | 1 | 1 (1) | 0 |", md)


class TestFreshReviewHeads(ReportCase):
    """「알 수 없음」 회차의 첫 줄을 남긴다 — 노트북 실사용 4회 중 3회가 여기 들어갔다(2026-11-10)."""

    RUN, PROMPT, run_script = TestFreshReviewTraces.RUN, TestFreshReviewTraces.PROMPT, TestFreshReviewTraces.run_script

    def test_unknown_runs_keep_their_first_line_and_list_results_are_read_as_text(self):
        listed = tool_result("f2", [{"type": "text", "text": "발동 — R=6\n…"}])
        self.session(self.run_script("f1", "Python was not found; run without arguments to install")
                     + [assistant(tools=[("f2", "Bash", {"command": self.RUN})]), listed])
        f = self.rows()["s1"]["fresh_review"]
        self.assertEqual((f.get("unknown"), f.get("fired")), (1, 1))
        self.assertEqual(f["unknown_heads"], ["Python was not found; run without arguments to install"])
        out = os.path.join(self.root, "out")
        hr.main(["--projects-dir", self.root, "--out", out])
        md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
        self.assertIn("| 알 수 없음 |", md)
        self.assertIn("Python was not found", md)

    def test_review_that_ran_without_a_record_is_flagged_even_if_no_run_was_recognised(self):
        self.session([assistant(tools=[("r1", "Agent", {"subagent_type": "Plan", "prompt": self.PROMPT})]),
                      tool_result("r1", "다시 쓴 계획")])
        out = os.path.join(self.root, "out")
        hr.main(["--projects-dir", self.root, "--out", out])
        with open(os.path.join(out, "report.md"), encoding="utf-8") as f:
            self.assertIn("없음(건너뜀?)", f.read())


class TestPredictionsAfterTheUpdate(ReportCase):
    """갱신 시각이 기록된 PC 의 세션은 그 결정이 든 릴리스 뒤에 시작한 세션만 센다 — 결정일로 세면 갱신 전 세션이 섞인다."""

    def test_rows_with_an_engine_version_are_counted_only_after_the_release(self):
        log = os.path.join(self.root, "DECISION_LOG.md")
        with open(log, "w", encoding="utf-8") as f:
            f.write("### [2026-11-11] 훅이 막은 Skill 호출은 Gate 순서에 넣지 않는다\n- **결과**:\n")
        changelog = os.path.join(self.root, "CHANGELOG.md")
        with open(changelog, "w", encoding="utf-8") as f:
            f.write("# Changelog\n\n## [Unreleased]\n\n## [1.19.0] - 2026-11-11\n\n## [1.18.0] - 2026-11-10\n")
        rows = [{"last": "2026-11-12T00:00:00Z", "blocked_gate_calls": 1, "engine_at_start": v}
                for v in ("1.18.0", "1.19.0", "1.20.1", None)]
        rows.append({"last": "2026-11-12T00:00:00Z", "blocked_gate_calls": 1})        # 갱신 시각이 없는 곳(이 서버)
        p = hr.prediction_progress(log, rows, changelog=changelog)[0]
        self.assertEqual(p["count"], 3)

    def test_feedback_metric_says_what_it_counts(self):
        source = next(m[3] for m in hr.METRICS if m[0].startswith("작업 PC 의 사용 기록 요약을"))
        self.assertIn("결정일 뒤", source)


class TestRepeatedSends(ReportCase):
    """노트북은 보낼 때마다 최근 30일 전체를 보낸다 — 받는 쪽은 같은 세션을 한 번만 센다(2026-11-10)."""

    def test_same_session_from_two_sends_keeps_the_latest_row(self):
        paths = []
        for i, (last, prompts) in enumerate((("2026-11-01T10:00:00Z", 1), ("2026-11-03T10:00:00Z", 5))):
            path = os.path.join(self.root, f"send{i}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"session": "s1", "last": last, "user_prompts": prompts}) + "\n")
                f.write(json.dumps({"session": f"only{i}", "last": last, "user_prompts": 0}) + "\n")
            paths.append(path)
        rows = {r["session"]: r for r in hr.load_sessions(list(reversed(paths)))["sessions"]}
        self.assertEqual(sorted(rows), ["only0", "only1", "s1"])
        self.assertEqual(rows["s1"]["user_prompts"], 5)
