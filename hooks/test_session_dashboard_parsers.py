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


class TestParsersFromReview(unittest.TestCase):
    """파서 — 코드 리뷰(2026-10-15)가 재현한 결함."""

    def test_parenthesized_evaluation_is_evaluated(self):
        """괄호로 감싼 실제 평가는 자리표시가 아니다 — 끝난 질문이 다시 뜨면 안 된다."""
        doc = ("## Gate B — 이해도\n\n### 질문 1\n무엇?\n"
               "- **읽을 곳**: 이해 브리핑 「왜 바꾸나」\n- **평가**: (통과 — 정확히 답함)\n")
        self.assertTrue(sdp.parse_comprehension(doc)["questions"][0]["evaluated"])

    def test_placeholder_evaluation_is_pending(self):
        for ph in ("(답변 후 기록)", "(filled after the answer)"):
            doc = f"## Gate B — 이해도\n\n### 질문 1\n무엇?\n- **평가**: {ph}\n"
            self.assertFalse(sdp.parse_comprehension(doc)["questions"][0]["evaluated"], ph)

    def test_colon_inside_bold_label(self):
        self.assertEqual(sdp._labeled_items("- **왜 바꾸나:** 이유"), [("왜 바꾸나", "이유")])

    def test_unindented_note_is_not_glued_to_last_item(self):
        items = sdp._labeled_items("- **되돌리는 법**: 되돌림\n  이어짐\n\n메모 문단\n- 일반 글머리")
        self.assertEqual(items, [("되돌리는 법", "되돌림 이어짐")])

    def test_heading_inside_code_fence_is_not_a_section(self):
        """계획이 인용한 템플릿의 `### 질문 N` 이 절을 쪼개지 않는다."""
        doc = ("## Gate A — 계획\n\n### 이해 브리핑\n- **왜 바꾸나**: a\n\n"
               "### 템플릿\n```\n### 질문 N\n본문\n```\n### 다음 절\nx\n")
        titles = [t for t, _ in sdp.parse_gate_documents(doc)[0]["sections"]]
        self.assertEqual(titles, ["이해 브리핑", "템플릿", "다음 절"])

    def test_evidence_before_after_on_one_line_uses_final(self):
        """「ⓒ 1건 → 승격, 최종 ⓒ 0건」 은 한 주장의 전후 — 최종값을 쓴다."""
        doc = "## Gate A 계획\n\n### 주장-근거 대조\n\n- ⓒ 1건 → 실측 승격, 최종 ⓒ 0건\n"
        self.assertNotIn("ⓒ", sdp.parse_gate_a_plan(doc)["evidence"])

    def test_table_cells_split_respects_escape(self):
        self.assertEqual(sdp.split_table_cells("| x \\| y | z |"), ["x | y", "z"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestParseGateAPlan(unittest.TestCase):
    """Gate A 계획 파싱 (DASHBOARD-PLAN-VIZ-1).

    계약은 전부 실행해서 확인한 것이고, 표기 변형은 원본 작업공간의 계획
    문서 909개에서 실측한 빈도를 근거로 골랐다.
    """

    PLAN = (
        "# 현재 세션 상태\n\n"
        "> **세션 ID**: T-1\n\n"
        "## Gate A 계획\n\n"
        "### 2. 변경 파일 (2개)\n\n"
        "**1. `a/b.py` (수정)**\n"
        "- 무언가 고친다\n\n"
        "**2. `c/d.py` (생성)**\n\n"
        "### 3. 구현 Step (2개)\n\n"
        "1. **첫 단계** 설명\n"
        "2. **둘째 단계** 설명\n\n"
        "### 리스크 및 대응\n\n"
        "| 리스크 | 원인 | 대응 |\n"
        "|---|---|---|\n"
        "| 오판 | 정규식 | 폴백 |\n\n"
        "### Gate A 범위 점검\n\n"
        "- [x] 변경 파일 ≤ 7개 (2개)\n"
        "- [ ] 구현 Step ≤ 5개\n\n"
        "## 다음 절\n"
    )

    def test_absent_plan_returns_present_false(self):
        """계획이 없으면 present=False — 렌더러가 패널을 통째로 생략한다."""
        d = sdp.parse_gate_a_plan("# 제목\n\n본문뿐\n")
        self.assertFalse(d["present"])
        self.assertEqual(d["files"], [])

    def test_empty_input_does_not_crash(self):
        d = sdp.parse_gate_a_plan("")
        self.assertFalse(d["present"])

    def test_returns_all_expected_keys(self):
        """렌더러가 .get 없이 쓰는 키가 빠지면 대시보드가 죽는다."""
        d = sdp.parse_gate_a_plan("")
        for k in ("present", "files", "steps", "risks", "scope_checks",
                  "refs", "verify", "evidence"):
            self.assertIn(k, d, f"키 누락: {k}")

    def test_files_steps_risks_scope_extracted(self):
        d = sdp.parse_gate_a_plan(self.PLAN)
        self.assertTrue(d["present"])
        self.assertEqual(len(d["files"]), 2, d["files"])
        self.assertIn("a/b.py", d["files"][0])
        self.assertEqual(len(d["steps"]), 2, d["steps"])
        self.assertEqual(d["steps"][0][0], "1")
        self.assertEqual(len(d["risks"]), 1, d["risks"])
        self.assertEqual(d["risks"][0][0], "오판")

    def test_unchecked_scope_item_is_false(self):
        """미체크 항목이 True 로 들어가면 화면이 통과로 거짓 안심시킨다."""
        d = sdp.parse_gate_a_plan(self.PLAN)
        flags = dict((t, ok) for ok, t in d["scope_checks"])
        self.assertTrue(any(v for v in flags.values()))
        self.assertIn(False, [ok for ok, _ in d["scope_checks"]])

    def test_plan_block_stops_at_next_h2(self):
        """`## 다음 절` 이후 내용이 계획으로 새면 안 된다."""
        block = sdp._plan_block(self.PLAN)
        self.assertIn("변경 파일", block)
        self.assertNotIn("다음 절", block)

    def test_plain_numbered_file_list(self):
        """굵기 없는 번호목록 파일 표기 — 실측 최다 형식."""
        text = ("## Gate A — 계획\n\n### 변경 파일 (2)\n\n"
                "1. `x/y.ts` (신규) — 설명\n2. `z.ts` (수정)\n")
        d = sdp.parse_gate_a_plan(text)
        self.assertEqual(len(d["files"]), 2, d["files"])

    def test_bold_label_sections_when_no_h3(self):
        """`###` 가 없고 `**변경 파일**:` 라벨만 있는 문서도 읽는다."""
        text = ("## Gate A — 계획\n\n**변경 파일 (2, ≤7)**:\n\n"
                "1. `a.ts` (신규)\n2. `b.ts` (수정)\n")
        d = sdp.parse_gate_a_plan(text)
        self.assertEqual(len(d["files"]), 2, d["files"])

    def test_h3_present_means_bold_labels_do_not_split(self):
        """`###` 가 있으면 본문 속 `**강조**:` 로 절이 쪼개지면 안 된다.

        굵은 라벨을 무조건 절 구분자로 인정했다가 파일 추출이 54%→7% 로
        무너진 자리다(실측 회귀).
        """
        text = ("## Gate A 계획\n\n### 변경 파일 (2)\n\n"
                "**설계 결정**: 어쩌고\n\n1. `a.ts` (신규)\n2. `b.ts` (수정)\n")
        d = sdp.parse_gate_a_plan(text)
        self.assertEqual(len(d["files"]), 2, d["files"])

    def test_inline_risk_split_keeps_noun_dot(self):
        """` · ` 로 나열한 리스크는 건별로 끊되, 명사 접속 `A·B` 는 유지."""
        text = ("## Gate A 계획\n\n### 요약\n\n"
                "- 위험: nested JSON·배열 오판(폴백) · 값 변경 통과\n")
        d = sdp.parse_gate_a_plan(text)
        self.assertEqual(len(d["risks"]), 2, d["risks"])
        self.assertIn("nested JSON·배열", d["risks"][0][0])

    def test_evidence_tags_counted(self):
        """ⓒ(미승격 주장) 개수는 사람이 가장 먼저 의심할 신호다."""
        text = "## Gate A 계획\n\n### 근거\n\n- ⓐ 실측 · ⓐ 또 · ⓒ 추론\n"
        d = sdp.parse_gate_a_plan(text)
        self.assertEqual(d["evidence"].get("ⓐ"), 2)
        self.assertEqual(d["evidence"].get("ⓒ"), 1)


class TestVizHelpers(unittest.TestCase):
    """시각화 보조 (DASHBOARD-PLAN-VIZ-2)."""

    def test_severity_defaults_to_med(self):
        """🔴 경중이 안 적혔으면 low 가 아니라 med — 안 적힌 위험을 낮음으로
        칠하면 화면이 「전부 안전하다」고 거짓말한다."""
        self.assertEqual(sdp.risk_severity(["그냥 위험"]), "med")

    def test_severity_low_and_high_keywords(self):
        self.assertEqual(sdp.risk_severity(["사소한 표기 오류"]), "low")
        self.assertEqual(sdp.risk_severity(["낮은 위험"]), "low")
        self.assertEqual(sdp.risk_severity(["치명적 데이터 손실"]), "high")

    def test_severity_reads_all_cells(self):
        """표 형식이면 대응 칸의 표현까지 본다."""
        self.assertEqual(
            sdp.risk_severity(["오판", "정규식", "영향 없음"]), "low"
        )

    def test_group_files_by_directory(self):
        g = sdp.group_files(["x/a.py (수정)", "x/b.py (수정)", "y/c.py (생성)"])
        self.assertEqual([d for d, _ in g], ["x/", "y/"])
        self.assertEqual(len(g[0][1]), 2)

    def test_group_files_keeps_non_path_entries(self):
        """경로가 아닌 설명 줄도 버리지 않는다 — 버리면 계획이 화면에서 샌다."""
        g = sdp.group_files(["설명만 있는 줄"])
        self.assertEqual(g, [("", ["설명만 있는 줄"])])

    def test_scope_gauges_extract_actual_and_limit(self):
        g = sdp.scope_gauges([(True, "변경 파일 ≤ 7개 (2개)")])
        self.assertEqual(g, [("변경 파일", 2, 7)])

    def test_scope_gauges_skip_items_without_numbers(self):
        """수치가 없는 서술형은 게이지에서 빠진다(체크 목록으로 남는다)."""
        self.assertEqual(sdp.scope_gauges([(True, "논리적 이유 1가지")]), [])

    def test_scope_gauges_handle_silcheuk_form(self):
        """`(실측 6)` 표기(실측 존재)도 읽는다."""
        g = sdp.scope_gauges([(True, "변경 파일 ≤ 7개 (실측 6)")])
        self.assertEqual(g, [("변경 파일", 6, 7)])


# 합성 문서다 — 실제 세션 계획을 시험 자료로 쓰지 않는다(공개 저장소).
# 모양만 실측을 따른다: 3칸 파일 표 · 중첩 Step · 4열 리스크 표 · 사전 조사 절.
_DOC = """# 현재 세션 상태

> **세션 ID**: DEMO-1

## Gate A — 구현 계획 (2026-10-11)

계획 머리말 한 줄.

### 사전 조사 결과

- 새 이미지가 뜨는 순간 마이그레이션이 적용된다.
  - 실패하면 기동이 멈춘다.

### 변경 파일 목록

| # | 저장소 | 경로 |
|---|--------|------|
| 1 | repo-a | `docs/INDEX.md` |

### 리스크와 대응

| # | 리스크 | 심각도 | 대응 |
|---|--------|--------|------|
| 1 | 기동 실패 | 심각 | 사전 대조 |

### 점검 결과

- 주장-근거 대조 ✅ (ⓒ 0건)

#### 하위 제목

하위 본문.

## Gate B — 이해도 게이트

- 판정: 일반 위험

### 질문 1

무엇이 보이는가?

## 직전 완료 세션

- 다른 절 — Gate 블록이 아니다.
"""


class TestParseGateDocuments(unittest.TestCase):
    """계획 전문 파싱 (DASHBOARD-FULL-PLAN, 2026-10-11).

    요약 파서는 다섯 가지만 골라 한 줄씩으로 만든다. 이쪽 계약은 반대다 —
    **고르지 않고, 다듬지 않는다.**
    """

    def setUp(self):
        self.docs = sdp.parse_gate_documents(_DOC)
        self.by_gate = {d["gate"]: d for d in self.docs}

    def test_splits_gate_blocks_in_order(self):
        self.assertEqual([d["gate"] for d in self.docs], ["A", "B"])
        self.assertEqual(self.by_gate["A"]["heading"],
                         "Gate A — 구현 계획 (2026-10-11)")

    def test_block_ends_at_next_same_level_heading(self):
        """`## 직전 완료 세션` 은 Gate B 블록에 섞이지 않는다."""
        text = "".join(b for _t, b in self.by_gate["B"]["sections"])
        self.assertNotIn("다른 절", text)

    def test_every_section_is_kept(self):
        """요약 파서가 버리던 절(사전 조사·점검 결과)이 전부 남는다."""
        titles = [t for t, _b in self.by_gate["A"]["sections"]]
        self.assertEqual(
            titles,
            ["", "사전 조사 결과", "변경 파일 목록", "리스크와 대응", "점검 결과"],
        )

    def test_lead_text_before_first_section_is_kept(self):
        self.assertEqual(self.by_gate["A"]["sections"][0],
                         ("", "계획 머리말 한 줄."))
        self.assertIn("판정: 일반 위험", self.by_gate["B"]["sections"][0][1])

    def test_body_is_raw_markdown(self):
        """중첩 항목의 들여쓰기와 표 문법이 그대로다 — 렌더러가 살려야 한다."""
        body = dict(self.by_gate["A"]["sections"])["사전 조사 결과"]
        self.assertIn("\n  - 실패하면 기동이 멈춘다.", body)
        risk = dict(self.by_gate["A"]["sections"])["리스크와 대응"]
        self.assertIn("| 1 | 기동 실패 | 심각 | 사전 대조 |", risk)

    def test_deeper_heading_stays_inside_section(self):
        body = dict(self.by_gate["A"]["sections"])["점검 결과"]
        self.assertIn("#### 하위 제목", body)
        self.assertIn("하위 본문.", body)

    def test_no_gate_block_returns_empty_list(self):
        self.assertEqual(sdp.parse_gate_documents("# 제목\n\n본문\n"), [])
        self.assertEqual(sdp.parse_gate_documents(""), [])

    def test_plan_block_contract_unchanged(self):
        """일반화 뒤에도 `_plan_block` 은 Gate A 본문만 돌려준다."""
        block = sdp._plan_block(_DOC)
        self.assertIn("### 사전 조사 결과", block)
        self.assertNotIn("질문 1", block)


class TestLosslessSummaryFields(unittest.TestCase):
    """요약 패널이 잃던 것 세 가지 — 실측으로 찾은 결함의 회귀 방지."""

    def setUp(self):
        self.plan = sdp.parse_gate_a_plan(_DOC)

    def test_file_table_keeps_every_cell(self):
        """앞 2칸만 이으면 `| # | 저장소 | 경로 |` 표에서 경로가 떨어진다."""
        self.assertEqual(self.plan["files"], ["1 — repo-a — docs/INDEX.md"])

    def test_risk_header_is_passed_through(self):
        self.assertEqual(self.plan["risk_header"],
                         ["#", "리스크", "심각도", "대응"])
        self.assertEqual(self.plan["risks"],
                         [["1", "기동 실패", "심각", "사전 대조"]])

    def test_count_notation_is_not_an_unproven_claim(self):
        """`ⓒ 0건` 은 개수를 적은 것이지 미검증 주장이 아니다."""
        self.assertNotIn("ⓒ", self.plan["evidence"])

    def test_real_tags_are_still_counted(self):
        doc = _DOC.replace("(ⓒ 0건)", "(ⓒ 2건)\n- 추론 주장 하나 ⓒ\n- 또 하나 ⓒ")
        self.assertEqual(sdp.parse_gate_a_plan(doc)["evidence"]["ⓒ"], 2)

    def test_no_risk_table_means_no_header(self):
        doc = "## Gate A\n\n### 리스크\n\n- 위험 하나\n"
        self.assertEqual(sdp.parse_gate_a_plan(doc)["risk_header"], [])

    def test_written_unproven_count_is_shown(self):
        """「ⓒ 2건」이라고 적었는데 0건으로 나오면 검토자가 놓친다."""
        doc = _DOC.replace("(ⓒ 0건)", "(ⓒ 2건)")
        self.assertEqual(sdp.parse_gate_a_plan(doc)["evidence"]["ⓒ"], 2)

    def test_tag_legend_rows_are_not_claims(self):
        """범례 표(`| ⓒ 추론 | … |`)는 주장이 아니다(엔진 이슈 #3 잔여)."""
        legend = ("\n| 태그 | 기준 |\n|---|---|\n| ⓐ 실측 | 명령 |\n"
                  "| ⓑ 파일 인용 | 줄 |\n| **ⓒ 추론** | 그 밖 |\n")
        doc = _DOC.replace("### 점검 결과\n", "### 점검 결과\n" + legend)
        self.assertEqual(sdp.parse_gate_a_plan(doc)["evidence"], {})


_BRIEF_DOC = """# 현재 세션 상태

## Gate A — 구현 계획

### 이해 브리핑

- **왜 바꾸나**: 화면에 <핵심>이 없다.
- **어떻게 동작하나**: 지금 → 바뀐 뒤.
  이어진 줄도 본문이다.
- **가장 깨지기 쉬운 곳**: 옛 문서.
- **되돌리는 법**: 커밋을 되돌린다.

### 변경 파일

1. `a.py` (수정)

## Gate B — 이해도 게이트

- **판정**: 일반 위험

### 질문 1 (힌트 후 통과)

첫 질문인가?

- **읽을 곳**: 이해 브리핑 「가장 깨지기 쉬운 곳」
- **평가**: 통과

### 질문 2

둘째 질문인가?

- **읽을 곳**: 이해 브리핑 「되돌리는 법」
- **평가**: (답변 후 기록)
"""


class TestParseComprehension(unittest.TestCase):
    """이해 브리핑 4항목·Gate B 질문 (HARNESS-DASH-LEARN-1-b-2)."""

    def setUp(self):
        self.c = sdp.parse_comprehension(_BRIEF_DOC)

    def test_four_labels_in_order(self):
        self.assertEqual([lb for lb, _ in self.c["briefing"]],
                         list(sdp.BRIEFING_LABELS))
        self.assertEqual(self.c["missing"], [])

    def test_continuation_line_joins_item(self):
        self.assertEqual(dict(self.c["briefing"])["어떻게 동작하나"],
                         "지금 → 바뀐 뒤. 이어진 줄도 본문이다.")

    def test_pilot_labels_are_aliased(self):
        """규칙화 전 시범 계획 2건이 쓴 라벨도 같은 칸에 들어간다."""
        doc = (_BRIEF_DOC.replace("**왜 바꾸나**", "**왜 하는가**")
               .replace("**어떻게 동작하나**", "**핵심 동작**"))
        labels = [lb for lb, _ in sdp.parse_comprehension(doc)["briefing"]]
        self.assertEqual(labels, list(sdp.BRIEFING_LABELS))

    def test_missing_label_is_reported(self):
        doc = _BRIEF_DOC.replace("- **되돌리는 법**: 커밋을 되돌린다.\n", "")
        self.assertEqual(sdp.parse_comprehension(doc)["missing"], ["되돌리는 법"])

    def test_no_briefing_section_means_both_empty(self):
        """절이 없는 것과 항목이 빠진 것은 다르게 말해야 한다."""
        c = sdp.parse_comprehension(_DOC)
        self.assertEqual((c["briefing"], c["missing"]), ([], []))

    def test_questions_with_where_and_evaluation(self):
        q = self.c["questions"]
        self.assertEqual([x["title"] for x in q], ["질문 1 (힌트 후 통과)", "질문 2"])
        self.assertEqual(q[1]["text"], "둘째 질문인가?")
        self.assertEqual(q[1]["where"], "이해 브리핑 「되돌리는 법」")
        self.assertEqual([x["evaluated"] for x in q], [True, False])

    def test_empty_input_does_not_crash(self):
        self.assertEqual(sdp.parse_comprehension(""),
                         {"briefing": [], "missing": [], "questions": []})

    def test_parser_failure_returns_empty(self):
        """내부 예외는 빈 값으로 — 동기화 전체가 실패하면 안 된다."""
        import unittest.mock as um
        with um.patch.object(sdp, "_labeled_items", side_effect=RuntimeError):
            self.assertEqual(sdp.parse_comprehension(_BRIEF_DOC),
                             {"briefing": [], "missing": [], "questions": []})
