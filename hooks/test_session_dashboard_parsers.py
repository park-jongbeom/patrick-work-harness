#!/usr/bin/env python3
"""session_dashboard_parsers.py 시험 (HARNESS-TEST-GAP-2, 2026-09-24).

이 모듈은 `session-dashboard-sync.py` 가 import 해서 쓰지만 시험이 하나도
없었다. 파서가 조용히 틀리면 **대시보드가 틀린 값을 그럴듯하게 보여준다** —
빈 화면이면 알아채지만 잘못된 세션 ID·상태는 알아채기 어렵다.

실제로 시험을 쓰다가 결함을 하나 잡았다: 세션 ID 정규식이 `[A-Z0-9\\-]+`
라서 이 하네스의 실제 세션 ID(`...-1-a-3`)를 소문자 앞에서 잘라냈다.
대시보드에 `HARNESS-CROSSCHECK-FIX-1-` 까지만 나오고 있었다.

계약은 전부 **실행해서 확인한 것**이다(추측하지 않는다):
  - `parse_current_session` → dict, 표 값은 닫는 `|` 까지 포함
  - `parse_session_index`   → **8-tuple** (호출부가 언패킹한다)
  - `_strip_history`        → **리터럴** `\\n> (이전 ` 을 구분자로 이후를 절단
    (`priority_note` 는 단일행 YAML 이라 개행이 리터럴 `\\n` 으로 저장된다)
"""

import importlib.util
import os
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "sdp", os.path.join(os.path.dirname(__file__), "session_dashboard_parsers.py")
)
sdp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sdp)


class TestParseCurrentSession(unittest.TestCase):

    def test_real_format_extracts_id_and_status(self):
        content = (
            "# 현재 세션 상태\n\n"
            "> **세션 ID**: HARNESS-CROSSCHECK-FIX-1-a-3 (재계획 2차)\n"
            "> **현재 상태**: 진행 중\n"
        )
        d = sdp.parse_current_session(content)
        self.assertEqual(d["session_id"], "HARNESS-CROSSCHECK-FIX-1-a-3")
        self.assertIn("진행 중", d["status"])

    def test_lowercase_suffix_not_truncated(self):
        """회귀 가드 — 세션 ID 의 소문자 꼬리(`-a-3`)를 잘라내지 않는다.

        2026-09-24 실측: 정규식이 `[A-Z0-9\\-]+` 라서 대시보드에
        `HARNESS-CROSSCHECK-FIX-1-` 까지만 표시되고 있었다. 이 하네스의
        세션 ID 규칙(`-a-1`·`-b-2`)에 소문자가 들어간다.
        """
        d = sdp.parse_current_session("> **세션 ID**: PROJ-FIX-1-b-2\n")
        self.assertEqual(d["session_id"], "PROJ-FIX-1-b-2")

    def test_session_id_without_parenthetical(self):
        d = sdp.parse_current_session("> **세션 ID**: ABC-123\n")
        self.assertEqual(d["session_id"], "ABC-123")

    def test_dashboard_table_fields(self):
        content = (
            "| Gate 진행 | A-OK to B-OK |\n"
            "| 변경 파일 | 7개 |\n"
            "| 착수일 | 2026-09-24 |\n"
        )
        d = sdp.parse_current_session(content)
        # 실측 계약: 닫는 `|` 까지 포함해 반환한다
        self.assertIn("A-OK", d["gate_progress"])
        self.assertIn("7개", d["files_changed"])
        self.assertIn("2026-09-24", d["start_date"])

    def test_missing_fields_do_not_crash(self):
        """빈 입력에서 죽지 않는다 — 파서가 죽으면 대시보드가 통째로 안 뜬다."""
        d = sdp.parse_current_session("")
        self.assertEqual(d["session_id"], "")
        self.assertEqual(d["repos"], [])

    def test_returns_all_expected_keys(self):
        """호출부가 기대하는 키가 빠지면 KeyError 로 동기화가 멈춘다."""
        d = sdp.parse_current_session("")
        for k in ("session_id", "work_topic", "status", "gate_progress",
                  "repos", "files_changed", "start_date", "end_date"):
            self.assertIn(k, d, f"키 누락: {k}")


class TestStripHistory(unittest.TestCase):
    """DASHBOARD-BANNER-FIX-2 회귀 — 과거 이력이 배너로 새지 않는다."""

    def test_history_after_separator_is_cut(self):
        text = "현재 세션 head 내용\\n> (이전 SESSION-1) 과거 내용\\n> (이전 SESSION-2) 더 과거"
        out = sdp._strip_history(text)
        self.assertIn("현재 세션 head", out)
        self.assertNotIn("SESSION-1", out)
        self.assertNotIn("SESSION-2", out)

    def test_head_without_history_is_untouched(self):
        text = "현재 세션 head 만 있고 이력은 없다"
        self.assertEqual(sdp._strip_history(text).strip(), text.strip())

    def test_jikjeon_terminator_in_head_is_kept(self):
        """`직전: X` 종결 라인은 구분자 **앞**이라 살아남아야 한다.

        FIX-1 이 콜론 앵커(`이전:|직전:`)로 잘랐다가 head 를 지나쳐 과포착한
        자리다. 종결자를 이력으로 오인하면 현재 상태가 배너에서 사라진다.
        """
        text = "현재 head 내용 · 직전: SESSION-9 완료\\n> (이전 SESSION-8) 과거"
        out = sdp._strip_history(text)
        self.assertIn("직전: SESSION-9", out)
        self.assertNotIn("SESSION-8", out)


class TestParseSessionIndex(unittest.TestCase):

    def test_returns_eight_tuple(self):
        """실측 계약: 8-tuple 을 돌려준다. 호출부가 언패킹하므로 길이가 계약이다."""
        r = sdp.parse_session_index('project: "my-project"\nlast_updated: "2026-09-24"\n')
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 8, f"언패킹 길이가 바뀌면 sync 가 죽는다: {r}")

    def test_project_and_last_updated_positions(self):
        r = sdp.parse_session_index('project: "my-project"\nlast_updated: "2026-09-24"\n')
        self.assertEqual(r[1], "2026-09-24", "last_updated 위치")
        self.assertEqual(r[5], "my-project", "project 위치")

    def test_empty_input_does_not_crash(self):
        r = sdp.parse_session_index("")
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
