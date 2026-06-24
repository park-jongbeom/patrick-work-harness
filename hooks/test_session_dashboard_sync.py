"""HSA-2 분할 회귀 가드 테스트 (HSA-2-b fixture+golden 재설계)

HSA-2(2026-05-28) `session-dashboard-sync.py` 819줄을 3 모듈
(parsers + renderer + sync 진입점)로 분할한 직후 회귀 가드.
HSA-2-b(2026-05-28) T2를 시점 무관 fixture+golden 경로로 재설계 —
이전 baseline 환경변수·subprocess·`/tmp` 의존 제거(HSA-2-FIXB-1 해소).

T1: import 정합 — 3 모듈 import 가능 + 5 핵심 함수 호출 가능
T2: HTML byte-for-byte 동등성 — 인라인 fixture markdown → `parse_*` →
    `generate_html` → `fixtures/dashboard_golden.html`과 비교.
    타임스탬프 2곳(최종 동기화·마지막 업데이트)만 정규식 마스킹.
"""

import re
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

FIXTURES_DIR = HOOKS_DIR / "fixtures"
GOLDEN_HTML = FIXTURES_DIR / "dashboard_golden.html"

# 시점 무관 fixture markdown — Gate B 시점 1회 확정. 변경 시 golden 재생성 필요.
FIXTURE_CURRENT_SESSION_MD = """\
# 현재 세션 상태

> **세션 ID**: HSA-FIXTURE-1 (고정 입력 회귀 가드 — HSA-2-b 도입)
> **세션 주제**: 고정 입력 배너 제목 회귀 가드
> **작업 의도**: 의도 필드가 있을 때 배너 본문이 priority_note 대신 이 문장을 쓰는지 검증한다.
> **현재 상태**: ✅E 완료

---

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | **✅E 완료** |
| Gate 진행 | A✅ → B✅ → C✅ → E✅ |
| 변경 파일 | 2 (NEW 1 / MODIFY 1) |
| 저장소 | plans |
| 착수일 | 2026-01-01 |
| 완료일 | 2026-01-01 |
| R/V/D 분해 | R=0 / V=1 / D=1 |
| Gate별 권장 모델 | B: Sonnet 4.6 (medium/off) |
"""

FIXTURE_SESSION_INDEX_MD = """\
---
project: "Fixture Project"
last_updated: "2026-01-01"
priority_note: "FIXTURE — 시점 무관 회귀 가드"
sessions: []
---

# 세션 인덱스

## 활성·예정 세션

| 세션 ID | 제목 | 저장소 | 상태 |
|---------|------|--------|------|
| FIXTURE-A | 활성 fixture 세션 | plans | A (승인 대기) |

## 최근 완료 (직전 6세션)

| 세션 ID | 제목 | 저장소 | 상태 |
|---------|------|--------|------|
| FIXTURE-1 | 고정 입력 회귀 가드 | plans | ✅E |
| FIXTURE-2 | 두번째 fixture | plans | ✅E |
"""

# 타임스탬프 마스킹 — renderer가 datetime.now()를 2곳에 주입한다:
#   (1) 푸터 "최종 동기화: {now}"
#   (2) 헤더 "📅 마지막 업데이트: {now} KST"
# golden 생성 시각과 테스트 실행 시각이 달라도 회귀 아님 → 둘 다 마스킹.
TIMESTAMP_RE = re.compile(
    r"(최종 동기화|마지막 업데이트):\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}"
)


def _mask(html_text):
    return TIMESTAMP_RE.sub(r"\1: <MASKED>", html_text)


class TestSessionDashboardSplit(unittest.TestCase):
    def test_t1_imports_and_callables(self):
        """3 모듈 import 정합 + 5 함수 호출 가능"""
        import session_dashboard_parsers as p
        import session_dashboard_renderer as r
        import importlib.util

        # session-dashboard-sync.py는 하이픈 포함이라 spec_from_file_location 경유
        sync_path = HOOKS_DIR / "session-dashboard-sync.py"
        spec = importlib.util.spec_from_file_location(
            "session_dashboard_sync", sync_path
        )
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        self.assertTrue(callable(p.parse_current_session))
        self.assertTrue(callable(p.parse_session_index))
        self.assertTrue(callable(r.generate_html))
        self.assertTrue(callable(sync_mod.read_markdown))
        self.assertTrue(callable(sync_mod.main))

    def test_t2_html_golden_equivalence(self):
        """fixture 입력 → generate_html → golden HTML byte 동등 (타임스탬프 마스킹)"""
        import session_dashboard_parsers as p
        import session_dashboard_renderer as r

        cur = p.parse_current_session(FIXTURE_CURRENT_SESSION_MD)
        (
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
        ) = p.parse_session_index(FIXTURE_SESSION_INDEX_MD)
        output = r.generate_html(
            cur,
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
        )

        self.assertTrue(
            GOLDEN_HTML.exists(),
            f"golden 파일 부재: {GOLDEN_HTML}. "
            "fixture 변경 시 fixtures/dashboard_golden.html 재생성 필요.",
        )

        golden_masked = _mask(GOLDEN_HTML.read_text(encoding="utf-8"))
        output_masked = _mask(output)

        if golden_masked != output_masked:
            g_lines = golden_masked.splitlines()
            o_lines = output_masked.splitlines()
            for i, (a, b) in enumerate(zip(g_lines, o_lines)):
                if a != b:
                    self.fail(
                        f"첫 차이 L{i + 1}:\n"
                        f"  golden: {a!r}\n"
                        f"  output: {b!r}"
                    )
            self.fail(
                f"길이 차이: golden={len(g_lines)} vs output={len(o_lines)}"
            )

    def test_t3_intent_absent_fallback(self):
        """세션 주제·작업 의도 부재 → 제목 work_topic·본문 priority_note 폴백

        DASHBOARD-INTENT-1: 의도 필드를 추가하지 않은 과거 세션 문서가
        배너에서 무회귀로 동작하는지 가드 (제목=괄호 작업 주제, 본문=priority_note).
        """
        import session_dashboard_parsers as p
        import session_dashboard_renderer as r

        md_no_intent = (
            "# 현재 세션 상태\n\n"
            "> **세션 ID**: LEGACY-1 (과거 세션 작업 주제)\n"
            "> **현재 상태**: ✅E 완료\n\n"
            "## 대시보드\n\n"
            "| 항목 | 값 |\n|------|-----|\n| 변경 파일 | 1 |\n"
        )
        cur = p.parse_current_session(md_no_intent)
        self.assertEqual(cur["intent_title"], "")
        self.assertEqual(cur["intent_note"], "")

        (
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
        ) = p.parse_session_index(FIXTURE_SESSION_INDEX_MD)
        html = r.generate_html(
            cur,
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
        )
        # 제목 폴백: work_topic (FIXTURE는 sessions:[] → current_title 공백)
        self.assertIn("과거 세션 작업 주제", html)
        # 본문 폴백: priority_note
        self.assertIn("FIXTURE — 시점 무관 회귀 가드", html)

    def test_t4_priority_note_history_stripped(self):
        """priority_note 메가라인 → 현재 세션 head만(과거 이력 체인 절단)

        DASHBOARD-BANNER-FIX-1: priority_note 캡처가 `(이전 priority_note)`
        체인 전량을 포착해 배너에 과거 기록을 덤프하던 버그의 회귀 가드.
        FIX-2: 앵커를 콜론(`이전:|직전:`)→구조적 이력 구분자(개행 선행
        `> (이전 `)로 전환. 콜론 앵커가 세션 중간 head에서 과포착하던
        "head+직전1건 잔존"을 차단. 3 케이스로 강화.
        FIX-3: 케이스 1을 실 2-백슬래시 포맷으로 보강. 실 SESSION_INDEX
        구분자는 백슬래시 2개형이 다수라 1-백슬래시 전용 앵커로는 절단점이
        둘째 백슬래시 앞 → trailing 백슬래시 1개 잔존. 수량자 `+` 적용 후
        3 케이스 모두 무-trailing-백슬래시 단언 추가.
        """
        import session_dashboard_parsers as p

        # 케이스 1: 완료 head — 실 2-백슬래시 구분자(SESSION_INDEX 다수 포맷).
        # FIX-3: \\\\n(소스) = 실 백슬래시 2개. trailing 백슬래시 잔존 회귀 가드.
        mega_done = (
            "---\n"
            'priority_note: "**현재 세션 — ✅E 완료** 현재 작업 설명. '
            "직전: PREV-1 ✅E.\\\\n> (이전 priority_note) "
            '**PREV-1 — ✅E 완료** 과거 세션 본문. 직전: PREV-2 ✅E."\n'
            "---\n"
        )
        (_s, _u, _t, note_done, _l) = p.parse_session_index(mega_done)
        self.assertIn("현재 작업 설명", note_done)
        self.assertIn("직전: PREV-1 ✅E", note_done)  # 현재 head 종결 라인 보존
        self.assertNotIn("(이전 priority_note)", note_done)
        self.assertNotIn("과거 세션 본문", note_done)  # 이력 본문 절단
        self.assertNotIn("PREV-2", note_done)  # 이력 전용 토큰 절단
        self.assertFalse(note_done.endswith(chr(92)))  # trailing 백슬래시 0

        # 케이스 2: 세션 중간(A/B/C) head — `직전:`/`이전:` 종결자 부재.
        # 콜론 앵커였다면 첫 과거 항목 콜론까지 과포착("head+직전1건 잔존").
        mega_mid = (
            "---\n"
            'priority_note: "**현재 세션 — B 확인 대기** 현재 작업 설명. '
            "사용자 Gate B 확인 → /gate-c.\\n> (이전 priority_note) "
            '**PREV-1 — ✅E 완료** 과거 세션 본문. 직전: PREV-2 ✅E."\n'
            "---\n"
        )
        (_s, _u, _t, note_mid, _l) = p.parse_session_index(mega_mid)
        self.assertIn("현재 작업 설명", note_mid)
        self.assertNotIn("(이전 priority_note)", note_mid)
        self.assertNotIn("과거 세션 본문", note_mid)
        self.assertNotIn("PREV-1", note_mid)  # 과포착 회귀 가드(콜론 앵커 결함)
        self.assertNotIn("PREV-2", note_mid)
        self.assertFalse(note_mid.endswith(chr(92)))  # trailing 백슬래시 0

        # 케이스 3: 현재 head prose 내 `> (이전 ` 백틱 인용(개행 선행 없음)
        # → 구분자 오인 금지(prose 보존·실제 이력만 절단).
        mega_prose = (
            "---\n"
            'priority_note: "**현재 세션** 앵커를 `> (이전 `로 전환했다. '
            "직전: PREV-1 ✅E.\\n> (이전 priority_note) "
            'HISTORY_BODY 과거 세션 본문."\n'
            "---\n"
        )
        (_s, _u, _t, note_prose, _l) = p.parse_session_index(mega_prose)
        self.assertIn("`> (이전 `로 전환", note_prose)  # 백틱 prose 보존
        self.assertIn("직전: PREV-1 ✅E", note_prose)
        self.assertNotIn("HISTORY_BODY", note_prose)  # 실제 이력만 절단
        self.assertFalse(note_prose.endswith(chr(92)))  # trailing 백슬래시 0


if __name__ == "__main__":
    unittest.main(verbosity=2)
