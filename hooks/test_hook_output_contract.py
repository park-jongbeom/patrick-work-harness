"""훅 출력 계약 시험 — 「강제 종료 허용」 같은 비차단 알림이 실제로 보이는 채널로 나가는가.

공식 hooks 문서: exit 0 훅의 stderr 는 사용자·Claude 어디에도 전달되지 않고, 사용자에게
보이는 경고는 stdout 의 JSON `systemMessage` 다. 이 계약을 어긴 경고 4곳이 2026-10-15
대조 검증에서 발견됐다(gate-a-sync·gate-e-sync·master-plan-stale·error-topics).

각 가드 시험 모듈의 run_hook·픽스처를 그대로 쓰고, 그 모듈의 subprocess.run 을 감싸
stdout·stderr 를 함께 받는다(기존 시험 파일은 고치지 않는다).

레인 범위 가드(S8b, 2026-10-22): 플러그인 `hooks/hooks.json` 과 `install.sh` 가 세 경로(PreToolUse
Skill·Edit 계열, UserPromptExpansion)에 모두 배선하는지, 그리고 네 가지 출력(거부·묻기·입력 차단·
통과 알림)이 모두 stdout JSON 으로 나가고 stderr 는 비는지 본다. `install.sh` 는 릴리스를 내려받아
설치하므로, 배선 코드(settings.json 을 쓰는 헤레독)만 떼어 임시 HOME 에 실제로 실행한다.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_error_topics_guard as t_err  # noqa: E402
import test_gate_a_sync_guard as t_a  # noqa: E402
import test_gate_e_sync_guard as t_e  # noqa: E402
import test_lane_scope_guard as t_lane  # noqa: E402
import test_master_plan_stale_guard as t_mp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANE = "lane-scope-guard.py"
EDIT_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"


def _capture(module, call):
    """module.run_hook 를 그대로 부르되 자식 프로세스의 stdout·stderr 를 가로챈다."""
    seen = {}
    real_run = module.subprocess.run

    def spy(*args, **kwargs):
        proc = real_run(*args, **kwargs)
        seen["proc"] = proc
        return proc

    module.subprocess.run = spy
    try:
        call()
    finally:
        module.subprocess.run = real_run
    return seen["proc"]


def _drive_past_max(module, max_blocks, run):
    """연속 차단을 한도까지 채운 뒤, 한도를 넘긴 호출의 프로세스를 돌려준다."""
    for _ in range(max_blocks):
        run()
    return _capture(module, run)


class TestForceAllowNoticeChannel(unittest.TestCase):

    def _assert_visible_notice(self, proc, tag):
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertIn(tag, data["systemMessage"])
        self.assertIn("강제 종료 허용", data["systemMessage"])
        self.assertNotIn("강제 종료 허용", proc.stderr)

    def test_gate_a_sync(self):
        sid = "t-contract-a"
        t_a.clear_counter(sid)
        cur = t_a.current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", intent=None)
        proc = _drive_past_max(t_a, t_a.MAX_BLOCKS, lambda: t_a.run_hook(cur, session_id=sid))
        t_a.clear_counter(sid)
        self._assert_visible_notice(proc, "[GATE-A-SYNC]")

    def test_gate_e_sync(self):
        sid = "t-contract-e"
        t_e.clear_counter(sid)
        idx = t_e.index_yaml("SESS-1", "✅E (2026-05-18, PASS)")
        cur = t_e.current_md("SESS-1", "D (확인 대기)", "D (확인 대기)")
        proc = _drive_past_max(t_e, t_e.MAX_BLOCKS, lambda: t_e.run_hook(idx, cur, session_id=sid))
        t_e.clear_counter(sid)
        self._assert_visible_notice(proc, "[GATE-E-SYNC]")

    def test_master_plan_stale(self):
        sid = "t-contract-mp"
        t_mp.clear_counter(sid)
        cur = t_mp.current_md("HARNESS-STALE-GUARD-1")
        plan = t_mp.master_plan_md("PLAN-SYNC-13")
        proc = _drive_past_max(t_mp, t_mp.MAX_BLOCKS, lambda: t_mp.run_hook(cur, plan, session_id=sid))
        t_mp.clear_counter(sid)
        self._assert_visible_notice(proc, "[MASTER-PLAN-STALE]")

    def test_error_topics(self):
        sid = "t-contract-err"
        t_err.clear_counter(sid)
        cur = t_err.current_md("FIX-B-CONTRACT-1")
        topics = {"my-api": {"testing.md": "무관\n"}}
        proc = _drive_past_max(t_err, t_err.MAX_BLOCKS,
                               lambda: t_err.run_hook(cur, session_id=sid, topics=topics))
        t_err.clear_counter(sid)
        self._assert_visible_notice(proc, "[ERROR-TOPICS]")


def _lane_paths(hooks_cfg):
    """{(이벤트, matcher)} — 레인 가드가 배선된 경로."""
    return {(ev, g.get("matcher", "")) for ev, groups in hooks_cfg.items() for g in groups
            for h in g.get("hooks", []) if LANE in h.get("command", "")}


def _run_install_registration(home, hooks_dir):
    """install.sh 의 배선 헤레독을 그대로 떼어 임시 HOME 에 실행한다."""
    text = open(os.path.join(ROOT, "install.sh"), encoding="utf-8").read()
    code = re.search(r"python3 - <<PYEOF\n(.*?)\nPYEOF", text, re.S).group(1)
    code = (code.replace("${GLOBAL_SETTINGS}", os.path.join(home, ".claude", "settings.json"))
                .replace("${GLOBAL_HOOKS_DIR}", hooks_dir).replace("${HOOK_PY}", "python3"))
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    with open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8") as f:
        return json.load(f)["hooks"]


class TestLaneGuardWiring(unittest.TestCase):
    WANT = {("PreToolUse", "Skill"), ("PreToolUse", EDIT_MATCHER), ("UserPromptExpansion", "")}

    def test_plugin_hooks_json_wires_all_three_paths(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            self.assertEqual(_lane_paths(json.load(f)["hooks"]), self.WANT)

    def test_install_registration_wires_all_three_paths(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        hooks_dir = os.path.join(home, "hooks")
        shutil.copytree(os.path.join(ROOT, "hooks"), hooks_dir)
        self.assertEqual(_lane_paths(_run_install_registration(home, hooks_dir)), self.WANT)

    def test_install_registration_is_idempotent(self):
        """다시 설치해도 항목이 늘지 않는다 — 중복 판정을 matcher 까지 보게 바꾼 뒤의 회귀 방지."""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        hooks_dir = os.path.join(home, "hooks")
        shutil.copytree(os.path.join(ROOT, "hooks"), hooks_dir)
        first = _run_install_registration(home, hooks_dir)
        second = _run_install_registration(home, hooks_dir)
        self.assertEqual(second, first)

    def test_install_skips_the_lane_guard_when_its_file_is_missing(self):
        """PreToolUse 훅 파일이 없으면 exit 2 = 차단 — 모든 편집이 막히지 않게 등록하지 않는다."""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        hooks_dir = os.path.join(home, "hooks")
        shutil.copytree(os.path.join(ROOT, "hooks"), hooks_dir)
        os.remove(os.path.join(hooks_dir, LANE))
        self.assertEqual(_lane_paths(_run_install_registration(home, hooks_dir)), set())


class TestLaneGuardOutputChannels(t_lane.LaneGuardCase):
    """거부·묻기·입력 차단·통과 알림이 모두 stdout JSON 이고 stderr 는 빈다."""

    def _proc(self, payload):
        return _capture(t_lane, lambda: self.run_hook(payload))

    def _assert_json_only(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        return json.loads(proc.stdout)

    def test_deny_at_gate_e_stops_the_session(self):
        self.write("src/other.py", "x = 2\n")
        out = self._assert_json_only(self._proc({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                                 "tool_input": {"skill": "gate-e"}}))
        self.assertIs(out["continue"], False)
        self.assertTrue(out["stopReason"])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_ask_before_a_protected_write(self):
        out = self._assert_json_only(self._proc({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                                 "tool_input": {"file_path": os.path.join(self.repo, "requirements.txt")}}))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_typed_gate_e_is_blocked(self):
        self.write("src/other.py", "x = 2\n")
        out = self._assert_json_only(self._proc({"hook_event_name": "UserPromptExpansion",
                                                 "command_name": "gate-e", "prompt": "/gate-e"}))
        self.assertEqual(out["decision"], "block")

    def test_pass_notice_is_a_system_message(self):
        self.implement()
        out = self._assert_json_only(self._proc({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                                 "tool_input": {"skill": "gate-e"}}))
        self.assertIn("자율 레인 범위 확인 통과", out["systemMessage"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
