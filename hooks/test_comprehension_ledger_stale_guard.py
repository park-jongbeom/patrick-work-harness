#!/usr/bin/env python3
"""comprehension-ledger-stale-guard.py 단위 테스트.

비차단 훅이라 만료 신호는 종료코드(항상 0)가 아니라 stderr 마커
'COMPREHENSION-LEDGER-STALE' 의 존재 여부로 검증한다.
결정성을 위해 만료 케이스는 먼 과거(2020) verified, 미만료 케이스는
먼 미래(2099) verified 를 써서 실행 날짜(date.today())와 무관하게 한다.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(
    os.path.dirname(__file__), "comprehension-ledger-stale-guard.py"
)
MARKER = "COMPREHENSION-LEDGER-STALE"


def run_hook(ledger_content, session_id="test-sess", write_ledger=True,
             stop_hook_active=False):
    """훅을 서브프로세스로 실행, (returncode, stderr) 반환."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "comprehension_ledger.md")
        if write_ledger:
            with open(ledger_path, "w", encoding="utf-8") as f:
                f.write(ledger_content)
        env = os.environ.copy()
        # 운영 조건 재현: Claude Code 가 Stop 훅 실행 시 항상 설정하는 env.
        # 미설정 시 모듈 로드 시점의 _default_ledger 분기(Path(_proj))를
        # 타지 못해 import-time 크래시(Path 미정의)를 놓친다(과거 위양성 통과 원인).
        env["CLAUDE_PROJECT_DIR"] = os.environ.get("CLAUDE_PROJECT_DIR", ".")
        env["COMPREHENSION_LEDGER_PATH"] = ledger_path
        payload = {"session_id": session_id}
        if stop_hook_active:
            payload["stop_hook_active"] = True
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True, text=True, env=env,
        )
        return proc.returncode, proc.stderr.strip()


# --- 픽스처 ---

def ledger(rows):
    """증적 표 텍스트 생성. rows = [(verified, scope, exp, 주체, 결과, 요약), ...]"""
    head = (
        "# 이해도 게이트 증적 원장\n\n"
        "## 증적 표\n\n"
        "| verified | scope | exp | 설명 주체 | 결과 | 설명 요약 |\n"
        "|----------|-------|-----|-----------|------|-----------|\n"
    )
    body = "".join(
        f"| {v} | {s} | {e} | {who} | {res} | {sm} |\n"
        for v, s, e, who, res, sm in rows
    )
    return head + body


# 첫 발동 전 템플릿(유효 날짜 행 0건)
EMPTY_LEDGER = ledger([("_(첫 발동 세션부터 누적)_", "—", "—", "—", "—", "—")])


# --- 테스트 ---

def test_empty_ledger_allows():
    """증적 0건(템플릿만) → 무알림 exit 0."""
    code, err = run_hook(EMPTY_LEDGER)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify: {err}"
    print("  PASS: 빈 ledger(템플릿) → 무알림 exit 0")


def test_expired_entry_notifies():
    """먼 과거 verified + 3개월 → 만료 알림(exit 0)."""
    led = ledger([("2020-01-01", "matching/ScoringService", "3개월",
                   "AI", "통과", "흐름 요약")])
    code, err = run_hook(led)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER in err, f"expected notify, got: {err}"
    assert "matching/ScoringService" in err, "expected scope in message"
    assert "2020-01-01" in err, "expected verified date in message"
    print("  PASS: 만료(2020 + 3개월) → 비차단 알림(exit 0)")


def test_fresh_entry_allows():
    """먼 미래 verified + 3개월(미만료) → 무알림 exit 0."""
    led = ledger([("2099-01-01", "matching/ScoringService", "3개월",
                   "AI", "통과", "흐름 요약")])
    code, err = run_hook(led)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify: {err}"
    print("  PASS: 미만료(2099 + 3개월) → 무알림 exit 0")


def test_scope_change_exp_skipped():
    """exp 가 'N개월' 아닌 '실질변경 시'(월수 없음) → skip → 무알림."""
    led = ledger([("2020-01-01", "auth/login", "scope 실질변경 시",
                   "사용자", "통과", "흐름 요약")])
    code, err = run_hook(led)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify: {err}"
    print("  PASS: '실질변경 시' exp(월수 없음) → skip 무알림")


def test_missing_ledger_allows():
    """원장 파일 부재 → fail-open 무알림 exit 0."""
    code, err = run_hook("", write_ledger=False)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify: {err}"
    print("  PASS: 원장 부재 → fail-open 무알림")


def test_malformed_rows_allow():
    """날짜 없는 행·비표 텍스트 → 파싱 skip → 무알림 exit 0."""
    code, err = run_hook("# 원장\n날짜 없음\n| 헤더만 | x |\n")
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify: {err}"
    print("  PASS: 비정형 행 → 파싱 skip 무알림")


def test_one_month_expiry_notifies():
    """폭발반경 大 exp '1개월' + 먼 과거 → 만료 알림."""
    led = ledger([("2020-01-01", "payment/checkout", "1개월",
                   "사용자", "통과", "흐름 요약")])
    code, err = run_hook(led)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER in err, f"expected notify, got: {err}"
    assert "payment/checkout" in err, "expected scope in message"
    print("  PASS: 1개월 만료(2020) → 비차단 알림")


def test_stop_hook_active_allows():
    """stop_hook_active=True → 만료 항목이 있어도 즉시 무알림(중복 방지)."""
    led = ledger([("2020-01-01", "matching/ScoringService", "3개월",
                   "AI", "통과", "흐름 요약")])
    code, err = run_hook(led, stop_hook_active=True)
    assert code == 0, f"expected 0, got {code}"
    assert MARKER not in err, f"unexpected notify on re-fire: {err}"
    print("  PASS: stop_hook_active → 만료 있어도 알림 생략")


def test_operational_env_no_import_crash():
    """회귀: CLAUDE_PROJECT_DIR 설정(=운영 조건) + LEDGER_PATH 오버라이드 없이
    실행해도 import-time 크래시(Path 미정의)가 나지 않는다.

    `Path` import 누락 버그는 _default_ledger 분기(Path(_proj))에서만
    터지고, 그 분기는 CLAUDE_PROJECT_DIR 가 있고 LEDGER_PATH 오버라이드가
    없을 때만 평가된다. 다른 테스트는 LEDGER_PATH 를 항상 세팅하지만
    _default_ledger 식 자체는 모듈 로드 시 무조건 계산되므로, 이 테스트는
    오버라이드를 빼서 import-time 평가 경로를 명시적으로 가드한다.
    """
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    env.pop("COMPREHENSION_LEDGER_PATH", None)
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps({"session_id": "test-sess"}),
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"expected 0, got {proc.returncode}: {proc.stderr}"
    assert "Traceback" not in proc.stderr, f"import-time 크래시 재발: {proc.stderr}"
    assert "NameError" not in proc.stderr, f"Path 미정의 재발: {proc.stderr}"
    print("  PASS: 운영 env(CLAUDE_PROJECT_DIR) → import-time 크래시 없음")


if __name__ == "__main__":
    tests = [
        test_empty_ledger_allows,
        test_expired_entry_notifies,
        test_fresh_entry_allows,
        test_scope_change_exp_skipped,
        test_missing_ledger_allows,
        test_malformed_rows_allow,
        test_one_month_expiry_notifies,
        test_stop_hook_active_allows,
        test_operational_env_no_import_crash,
    ]
    print(f"comprehension-ledger-stale-guard.py 테스트 ({len(tests)}건)")
    print("=" * 55)
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__} — {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__} — {e}")
            failed += 1
    print("=" * 55)
    print(f"결과: {passed} passed, {failed} failed / {len(tests)} total")
    sys.exit(1 if failed else 0)
