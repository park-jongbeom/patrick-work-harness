"""훅 출력 계약 시험 — 「강제 종료 허용」 같은 비차단 알림이 실제로 보이는 채널로 나가는가.

공식 hooks 문서: exit 0 훅의 stderr 는 사용자·Claude 어디에도 전달되지 않고, 사용자에게
보이는 경고는 stdout 의 JSON `systemMessage` 다. 이 계약을 어긴 경고 4곳이 2026-10-15
대조 검증에서 발견됐다(gate-a-sync·gate-e-sync·master-plan-stale·error-topics).

각 가드 시험 모듈의 run_hook·픽스처를 그대로 쓰고, 그 모듈의 subprocess.run 을 감싸
stdout·stderr 를 함께 받는다(기존 시험 파일은 고치지 않는다).
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_error_topics_guard as t_err  # noqa: E402
import test_gate_a_sync_guard as t_a  # noqa: E402
import test_gate_e_sync_guard as t_e  # noqa: E402
import test_master_plan_stale_guard as t_mp  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
