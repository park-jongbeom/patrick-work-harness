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


class TestGateAPlanPanel(unittest.TestCase):
    """Gate A 계획 패널 (DASHBOARD-PLAN-VIZ-1).

    설계 근거는 조사 결과다 — 승인 버튼을 늘리지 않고(Anthropic 계측: 권한
    프롬프트의 약 93%가 승인되고, 많이 볼수록 주의가 줄어든다) 읽고 판단할
    요약만 얹는다. 그래서 **버튼이 없다는 것 자체가 계약**이다.
    """

    PLAN = {
        "present": True,
        "files": ["a/b.py (수정)", "c/d.py (생성)"],
        "steps": [("1", "첫 단계"), ("2", "둘째 단계")],
        "risks": [["오판", "정규식", "폴백"]],
        "scope_checks": [(True, "변경 파일 ≤ 7개"), (False, "Step ≤ 5개")],
        "refs": "기존 패턴 재사용",
        "verify": "T1 통과",
        "evidence": {"ⓐ": 2, "ⓒ": 1},
    }

    def test_absent_plan_renders_nothing(self):
        """계획이 없으면 패널이 통째로 빠진다 — 빈 껍데기를 두지 않는다."""
        self.assertEqual(sdr.render_gate_a_plan(None), "")
        self.assertEqual(sdr.render_gate_a_plan({"present": False}), "")

    @staticmethod
    def _full(plan):
        """계획을 넘겨 전체 문서를 렌더한다.

        모듈 상단 `render()` 헬퍼는 9개 인자 계약을 고정하는 용도라
        `gate_a_plan` 을 넘기지 않는다 — 여기서만 직접 호출한다.
        """
        return sdr.generate_html(
            cs(), {"active": [], "completed": []}, "2026-09-24",
            "", "", "", "", "", "", plan,
        )

    def test_no_plan_keeps_dashboard_rendering(self):
        """계획이 없어도 대시보드 자체는 계속 떠야 한다."""
        html = self._full(None)
        self.assertIn("</html>", html)
        self.assertNotIn('class="plan-review"', html)

    def test_panel_shows_counts_and_items(self):
        html = self._full(self.PLAN)
        self.assertIn("plan-review", html)
        self.assertIn("Gate A 계획", html)
        # VIZ-2: 파일은 디렉터리로 묶여 `a/` + `b.py` 로 쪼개 렌더된다
        # (전체 경로 문자열은 더 이상 한 덩어리로 나오지 않는다)
        self.assertIn("a/", html)
        self.assertIn("b.py", html)
        self.assertIn("첫 단계", html)
        self.assertIn("오판", html)

    def test_files_are_grouped_by_directory(self):
        """같은 디렉터리 파일은 한 묶음으로 — 「어디에 몰렸나」가 보여야 한다."""
        plan = dict(self.PLAN, files=["x/a.py (수정)", "x/b.py (수정)",
                                      "y/c.py (생성)"])
        html = sdr.render_gate_a_plan(plan)
        self.assertIn("plan-dir", html)
        # x/ 묶음의 개수 배지가 2 여야 한다
        self.assertIn('<span class="plan-dir-count">2</span>', html)

    def test_scope_gauge_renders_bar(self):
        """한도·실제치가 있으면 막대로 — 「2/7」은 읽어야 알고 막대는 보인다."""
        plan = dict(self.PLAN,
                    scope_checks=[(True, "변경 파일 ≤ 7개 (2개)")])
        html = sdr.render_gate_a_plan(plan)
        self.assertIn("plan-bar-fill", html)
        self.assertIn("2 / 7", html)

    def test_scope_gauge_flags_near_limit(self):
        """한도 80% 이상은 색이 달라진다 — 「아직 통과」와 「곧 걸린다」는 다르다."""
        near = dict(self.PLAN, scope_checks=[(True, "구현 Step ≤ 5개 (5개)")])
        self.assertIn("plan-bar-near", sdr.render_gate_a_plan(near))
        far = dict(self.PLAN, scope_checks=[(True, "변경 파일 ≤ 7개 (1개)")])
        self.assertNotIn("plan-bar-near", sdr.render_gate_a_plan(far))

    def test_step_pipeline_rendered(self):
        """실행 순서는 가로 흐름으로도 보여준다(목록은 상세로 남긴다)."""
        html = sdr.render_gate_a_plan(self.PLAN)
        self.assertIn("plan-flow", html)
        self.assertIn("plan-node", html)
        self.assertIn("plan-arrow", html)  # 2개 이상이면 화살표

    def test_risk_severity_dot_and_legend(self):
        """경중 점은 **범례와 함께**만 뜻이 선다(색만으로 전하지 않는다)."""
        plan = dict(self.PLAN, risks=[["치명적 데이터 손실", "x", "y"],
                                      ["사소한 표기", "x", "y"]])
        html = sdr.render_gate_a_plan(plan)
        self.assertIn("plan-dot-high", html)
        self.assertIn("plan-dot-low", html)
        self.assertIn("plan-legend", html)

    def test_legend_says_default_is_unmarked(self):
        """🔴 경중 미표기가 기본값임을 숨기지 않는다 — AI 가 판정한 척하면 안 된다."""
        plan = dict(self.PLAN, risks=[["경중 표현 없는 위험", "x", "y"]])
        html = sdr.render_gate_a_plan(plan)
        self.assertIn("미표기", html)

    def test_unproven_claim_tile_is_flagged(self):
        """ⓒ 가 남으면 그 타일만 경고색 — 가장 먼저 의심할 자리다."""
        html = sdr.render_gate_a_plan(self.PLAN)
        self.assertIn("plan-tile-warn", html)

    def test_no_unproven_claim_has_no_warning(self):
        plan = dict(self.PLAN, evidence={"ⓐ": 3})
        self.assertNotIn("plan-tile-warn", sdr.render_gate_a_plan(plan))

    def test_failed_scope_check_is_marked(self):
        """미체크 범위 항목이 통과처럼 보이면 거짓 안심을 준다."""
        html = sdr.render_gate_a_plan(self.PLAN)
        self.assertIn("plan-check-fail", html)

    def test_panel_has_no_approval_button(self):
        """승인 버튼을 넣지 않는 것이 이 패널의 설계 계약이다."""
        html = sdr.render_gate_a_plan(self.PLAN)
        for bad in ("<button", "<form", 'type="submit"'):
            self.assertNotIn(bad, html, f"승인 UI 금지: {bad}")

    def test_html_is_escaped(self):
        """계획 본문의 `<T>`·`&` 가 화면을 깨뜨리면 안 된다."""
        plan = dict(self.PLAN, files=["<script>alert(1)</script> & x"])
        html = sdr.render_gate_a_plan(plan)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_panel_appears_before_session_list(self):
        """검토용 패널은 세션 목록보다 위에 온다 — 먼저 읽을 것이 먼저."""
        html = self._full(self.PLAN)
        self.assertLess(
            html.index("plan-review"), html.index("활성 세션"),
            "계획 패널이 활성 세션 아래로 내려갔다",
        )

    def test_risk_table_row_shape_is_padded(self):
        """열 수가 모자란 리스크 행에도 표가 깨지지 않는다."""
        plan = dict(self.PLAN, risks=[["단독 위험"]])
        html = sdr.render_gate_a_plan(plan)
        self.assertIn("단독 위험", html)
