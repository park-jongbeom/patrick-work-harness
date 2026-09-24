#!/usr/bin/env python3
"""session_dashboard_renderer.py 시험 (HARNESS-TEST-GAP-3, 2026-09-24).

`session-dashboard-sync.py` 가 import 하는 마지막 미시험 모듈이다.
렌더러가 조용히 틀리면 **대시보드가 그럴듯한 화면으로 틀린 상태를 보여준다** —
오늘 `parsers` 에서 세션 ID 가 잘려 표시되던 결함이 같은 성격이었다.

계약은 전부 **실행해서 확인한 것**이다:
  - `generate_html(current_session, sessions, last_updated, current_title,
    priority_note, last_completed_title, project, gate_status, next_action)` → HTML str
  - `sessions` 는 `{"active": [...], "completed": [...]}` dict
  - 배너 제목은 **폴백 체인**: `intent_title` → `current_title` → `work_topic`
    → `last_completed_title` → `"(작업 주제 미기재)"`
"""

import importlib.util
import os
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "sdr", os.path.join(os.path.dirname(__file__), "session_dashboard_renderer.py")
)
sdr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sdr)

_KEYS = ("session_id", "work_topic", "intent_title", "intent_note", "status",
         "gate_progress", "files_changed", "start_date", "end_date",
         "test_result", "model_rec")


def cs(**over):
    """current_session dict — 지정한 키만 채우고 나머지는 빈 값."""
    d = {k: "" for k in _KEYS}
    d["repos"] = []
    d.update(over)
    return d


def render(current=None, sessions=None, **kw):
    args = dict(last_updated="2026-09-24", current_title="", priority_note="",
                last_completed_title="", project="", gate_status="", next_action="")
    args.update(kw)
    return sdr.generate_html(
        current or cs(),
        sessions if sessions is not None else {"active": [], "completed": []},
        args["last_updated"], args["current_title"], args["priority_note"],
        args["last_completed_title"], args["project"], args["gate_status"],
        args["next_action"],
    )


class TestGenerateHtml(unittest.TestCase):

    def test_returns_complete_html_document(self):
        html = render()
        self.assertTrue(html.startswith("<!DOCTYPE html>"), html[:40])
        self.assertIn("</html>", html)

    def test_css_is_inlined(self):
        """CSS 를 못 읽으면 스타일 없는 날것으로 뜬다 — 링크가 아니라 인라인이어야 한다."""
        html = render()
        self.assertIn("<style", html)

    def test_session_id_is_rendered(self):
        html = render(cs(session_id="PROJ-FIX-1-a-3"))
        self.assertIn("PROJ-FIX-1-a-3", html)

    def test_dashboard_fields_are_rendered(self):
        html = render(cs(status="ZS", gate_progress="ZG", files_changed="ZF",
                         start_date="ZD", test_result="ZT", model_rec="ZM"))
        for mark in ("ZS", "ZG", "ZF", "ZD", "ZT", "ZM"):
            self.assertIn(mark, html, f"{mark} 가 렌더링되지 않았다")


class TestTitleFallbackChain(unittest.TestCase):
    """배너 제목 폴백 — 앞 단계가 비었을 때만 다음으로 내려간다."""

    def test_intent_title_wins(self):
        html = render(cs(intent_title="A_INTENT", work_topic="B_TOPIC"),
                      current_title="C_TITLE", last_completed_title="D_LAST")
        self.assertIn("A_INTENT", html)

    def test_current_title_when_no_intent(self):
        html = render(cs(work_topic="B_TOPIC"),
                      current_title="C_TITLE", last_completed_title="D_LAST")
        self.assertIn("C_TITLE", html)

    def test_work_topic_when_no_intent_or_title(self):
        """`work_topic` 은 3순위다 — 앞 둘이 비어야 비로소 쓰인다.

        이 시험을 쓰다가 「work_topic 이 렌더링 안 된다」고 오판할 뻔했다.
        `current_title` 을 채운 채로 재서 3순위까지 내려가지 않았을 뿐이다.
        """
        html = render(cs(work_topic="B_TOPIC"), last_completed_title="D_LAST")
        self.assertIn("B_TOPIC", html)

    def test_last_completed_when_all_empty(self):
        html = render(cs(), last_completed_title="D_LAST")
        self.assertIn("D_LAST", html)

    def test_placeholder_when_everything_empty(self):
        html = render(cs())
        self.assertIn("작업 주제 미기재", html)


class TestSessionLists(unittest.TestCase):

    def test_active_and_completed_are_rendered(self):
        """세션 dict 계약: `id`·`repo`·`status`·`title` 4키 (파서가 만드는 형태)."""
        sessions = {
            "active": [{"id": "ACT-1", "repo": "r1", "status": "진행", "title": "진행 세션"}],
            "completed": [{"id": "DONE-1", "repo": "r2", "status": "완료", "title": "완료 세션"}],
        }
        html = render(sessions=sessions)
        self.assertIn("ACT-1", html)
        self.assertIn("DONE-1", html)

    def test_missing_session_key_raises(self):
        """키가 빠지면 KeyError 로 **즉시** 죽는다 — 조용히 넘어가지 않는다.

        렌더러는 파서 출력을 그대로 받으므로, 파서가 키를 빠뜨리면 여기서
        멈추는 편이 낫다. 빈 화면은 알아채지만 일부만 빠진 화면은 못 알아챈다.
        """
        with self.assertRaises(KeyError):
            render(sessions={"active": [{"id": "X", "title": "키 누락"}],
                             "completed": []})

    def test_empty_lists_do_not_crash(self):
        """세션이 하나도 없어도 렌더링된다 — 새 프로젝트의 첫 실행이 이 경우다."""
        html = render(sessions={"active": [], "completed": []})
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
