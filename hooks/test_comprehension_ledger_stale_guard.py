#!/usr/bin/env python3
"""comprehension-ledger-stale-guard.py 단위 테스트.

비차단 훅이라 만료 신호는 종료코드(항상 0)가 아니라 stderr 마커
'COMPREHENSION-LEDGER-STALE' 의 존재 여부로 검증한다.
결정성을 위해 만료 케이스는 먼 과거(2020) verified, 미만료 케이스는
먼 미래(2099) verified 를 써서 실행 날짜(date.today())와 무관하게 한다.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

# Windows cp949 콘솔에서 '—'·'✅' 등 출력 시 UnicodeEncodeError 방지 (Python 3.7+)
sys.stdout.reconfigure(encoding="utf-8")

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
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
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
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert proc.returncode == 0, f"expected 0, got {proc.returncode}: {proc.stderr}"
    assert "Traceback" not in proc.stderr, f"import-time 크래시 재발: {proc.stderr}"
    assert "NameError" not in proc.stderr, f"Path 미정의 재발: {proc.stderr}"
    print("  PASS: 운영 env(CLAUDE_PROJECT_DIR) → import-time 크래시 없음")


# ── 경로 해석 단언 (HARNESS-LEDGER-PATH-1, 2026-08-07) ──
#
# 기존 8건은 COMPREHENSION_LEDGER_PATH 로 경로를 **주입**해 훅을 실행하므로,
# 정작 운영에서 쓰이는 경로 계산식(_resolve_ledger_path)을 한 번도 거치지
# 않는다. 실제로 `.parent` 를 제거해 원장에 도달하지 못하게 만든 사본이
# 기존 회귀 9/9 를 그대로 통과함을 A/B 대조로 실증했다 — fail-open 설계
# (read_text 의 except → None → allow) 탓에 "경로 오류"와 "만료 0건"의
# 관측 결과가 exit 0 + 무출력로 동일해 구별되지 않기 때문이다.
# 따라서 아래 테스트들은 서브프로세스 실행 결과가 아니라 **모듈을 직접
# 임포트해 계산된 값 자체**를 단언한다 (선례: FIX-B-DEADHOOK-TMPFIX-1-a).


def _load_module(env_overrides):
    """훅 모듈을 지정 env 로 새로 임포트해 반환 (import 시점 계산값 관측용)."""
    saved = {k: os.environ.get(k) for k in env_overrides}
    os.environ.update({k: v for k, v in env_overrides.items() if v is not None})
    for k, v in env_overrides.items():
        if v is None:
            os.environ.pop(k, None)
    try:
        spec = importlib.util.spec_from_file_location("_ledger_guard", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _write_answers(tmpdir, body):
    """tmpdir/.claude/harness-answers.yml 작성."""
    claude_dir = os.path.join(tmpdir, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    path = os.path.join(claude_dir, "harness-answers.yml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def test_resolves_to_real_ledger():
    """★ 핵심 단언: env 오버라이드 없이 계산된 LEDGER_PATH 가 **실제 원장**을
    가리킨다.

    비교 대상이 픽스처면 안 된다 — 경로를 주입하는 순간 검증하려던 계산식이
    우회되어 이 결함을 영원히 놓친다(자기모순 구조).

    ※ 이 단언은 실 워크스페이스 배치(harness-answers.yml 의 learning_path 가
    가리키는 원장 실재)에 의존한다. 픽스처 격리 원칙의 의도적 위반이며,
    검증 대상이 "로직이 맞는가"가 아니라 "이 설정이 이 환경에서 실제로
    도달하는가"이기 때문에 타당하다. 원장이 없는 환경(신규 클론·타 프로젝트)
    에서는 검증 자체가 성립하지 않으므로 skip 한다.
    """
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj or not os.path.isfile(
        os.path.join(proj, ".claude", "harness-answers.yml")
    ):
        print("  SKIP: 실 워크스페이스 아님(harness-answers.yml 부재) — 배치 의존")
        return
    module = _load_module({"COMPREHENSION_LEDGER_PATH": None})
    assert os.path.isfile(module.LEDGER_PATH), (
        f"계산된 원장 경로가 실재하지 않음: {module.LEDGER_PATH} "
        "(learning_path SSOT 또는 경로 해석 결함)"
    )
    print(f"  PASS: 운영 조건 LEDGER_PATH → 실제 원장 도달 ({module.LEDGER_PATH})")


def test_missing_learning_path_falls_back_to_default():
    """learning_path 필드 부재 → 기본값 'plans/learning' (하위 호환).

    plan_tier 미기재를 "2" 로 간주하는 것과 동일한 패턴.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_answers(tmpdir, 'project_repo: "x"\n')
        module = _load_module({
            "CLAUDE_PROJECT_DIR": tmpdir,
            "COMPREHENSION_LEDGER_PATH": None,
        })
        expected = os.path.join(
            tmpdir, "plans", "learning", "comprehension_ledger.md"
        )
        assert os.path.normpath(module.LEDGER_PATH) == os.path.normpath(expected), (
            f"기본값 폴백 실패: {module.LEDGER_PATH} != {expected}"
        )
    print("  PASS: learning_path 부재 → 기본값 plans/learning 폴백")


def test_absolute_learning_path_respected():
    """learning_path 가 절대경로면 CLAUDE_PROJECT_DIR 와 결합하지 않고 그대로 사용."""
    with tempfile.TemporaryDirectory() as tmpdir:
        abs_learn = os.path.join(tmpdir, "abs_learn")
        _write_answers(
            tmpdir, f'learning_path: "{abs_learn.replace(os.sep, "/")}"\n'
        )
        module = _load_module({
            "CLAUDE_PROJECT_DIR": tmpdir,
            "COMPREHENSION_LEDGER_PATH": None,
        })
        expected = os.path.join(abs_learn, "comprehension_ledger.md")
        assert os.path.normpath(module.LEDGER_PATH) == os.path.normpath(expected), (
            f"절대경로 미존중: {module.LEDGER_PATH} != {expected}"
        )
    print("  PASS: 절대경로 learning_path 존중")


def test_missing_answers_yml_falls_back():
    """harness-answers.yml 자체 부재 → 기본값 폴백 (fail-open, 크래시 없음)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        module = _load_module({
            "CLAUDE_PROJECT_DIR": tmpdir,
            "COMPREHENSION_LEDGER_PATH": None,
        })
        # cwd 폴백 후보가 잡힐 수 있으므로 '크래시 없이 원장 파일명으로 끝남'만 단언
        assert module.LEDGER_PATH.endswith("comprehension_ledger.md"), (
            f"yml 부재 시 해석 실패: {module.LEDGER_PATH}"
        )
    print("  PASS: harness-answers.yml 부재 → 크래시 없이 폴백")


def test_simple_parser_without_pyyaml():
    """PyYAML 미설치 대비 간이 파서가 learning_path 스칼라를 추출한다(주석 제거 포함)."""
    module = _load_module({"COMPREHENSION_LEDGER_PATH": None})
    parse = module._simple_parse_learning_path
    commented = 'learning_path: "../plans/learning"   # 형제 배치'
    assert parse(commented) == "../plans/learning"
    assert parse("learning_path: plan/learning") == "plan/learning"
    assert parse('project_repo: "x"\n') is None
    print("  PASS: PyYAML 미설치 간이 파서 — 주석·따옴표 제거 후 추출")


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
        # 경로 해석 단언 (HARNESS-LEDGER-PATH-1)
        test_resolves_to_real_ledger,
        test_missing_learning_path_falls_back_to_default,
        test_absolute_learning_path_respected,
        test_missing_answers_yml_falls_back,
        test_simple_parser_without_pyyaml,
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
