#!/usr/bin/env python3
"""gate-e-sync-guard.py 단위 테스트."""

import json
import os
import re
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "gate-e-sync-guard.py")
MAX_BLOCKS = 3  # gate-e-sync-guard.py 와 동일해야 함


def counter_file(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".gate-e-sync-guard-{safe}.count")


def clear_counter(session_id):
    try:
        os.remove(counter_file(session_id))
    except OSError:
        pass


def run_hook(session_index, current_session, session_id="test-sess",
             write_index=True, write_current=True, stop_hook_active=False):
    """gate-e-sync-guard.py 를 서브프로세스로 실행, (returncode, stderr) 반환."""
    with tempfile.TemporaryDirectory() as tmpdir:
        if write_index:
            with open(os.path.join(tmpdir, "SESSION_INDEX.md"), "w",
                      encoding="utf-8") as f:
                f.write(session_index)
        if write_current:
            with open(os.path.join(tmpdir, "CURRENT_SESSION.md"), "w",
                      encoding="utf-8") as f:
                f.write(current_session)

        env = os.environ.copy()
        env["GATE_E_GUARD_BASE"] = tmpdir
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

def index_yaml(session_id, gate):
    """SESSION_INDEX.md '활성·예정 세션' 마크다운 표 픽스처.

    HARNESS-GATE-A-GUARD-1(2026-06-03) 파서 복구에 맞춰 YAML `sessions:` 블록 →
    마크다운 표로 전환(가드가 표에서 세션 ID 행의 ✅E 여부를 조회). 함수명은
    호출부 호환을 위해 유지. `gate` 인자 문자열을 상태 열에 그대로 기재한다.
    """
    return (
        '---\n'
        'project: "Test"\n'
        '---\n'
        '# 세션 인덱스\n\n'
        '## 활성·예정 세션\n\n'
        '| 세션 ID | 제목 | 저장소 | 상태 |\n'
        '|---------|------|--------|------|\n'
        f'| **{session_id}** | T | repo | {gate} |\n\n'
        '## 최근 완료\n'
    )


def current_md(session_id, status, gate_cell):
    return (
        '# 현재 세션 상태\n\n'
        f'> **세션 ID**: {session_id} (테스트)\n'
        f'> **현재 상태**: {status}\n\n'
        '## 대시보드\n\n'
        '| 항목 | 값 |\n'
        '|------|-----|\n'
        f'| 현재 Gate | **{gate_cell}** |\n'
    )


# --- 테스트 ---

def test_active_session_allows():
    """활성 세션(양쪽 비-✅E) → 허용."""
    clear_counter("t-active")
    code, _ = run_hook(
        index_yaml("SESS-1", "B (확인 대기, 2026-05-18)"),
        current_md("SESS-1", "B (확인 대기)", "B (확인 대기)"),
        session_id="t-active",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 활성 세션 → 허용")


def test_completed_consistent_allows():
    """완료 세션 — SESSION_INDEX·CURRENT_SESSION 모두 ✅E → 허용."""
    clear_counter("t-done")
    code, _ = run_hook(
        index_yaml("SESS-1", "✅E (2026-05-18, PASS)"),
        current_md("SESS-1", "✅E 완료 (2026-05-18)", "✅E 완료"),
        session_id="t-done",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 완료·일관 → 허용")


def test_mismatch_blocks():
    """SESSION_INDEX ✅E 인데 CURRENT_SESSION 미갱신 → 차단(exit 2)."""
    clear_counter("t-mismatch")
    code, err = run_hook(
        index_yaml("SESS-1", "✅E (2026-05-18, PASS)"),
        current_md("SESS-1", "D (확인 대기)", "D (확인 대기)"),
        session_id="t-mismatch",
    )
    assert code == 2, f"expected 2, got {code}"
    assert "GATE-E-SYNC" in err, f"expected guard message, got: {err}"
    clear_counter("t-mismatch")
    print("  PASS: 불일치 → 차단(exit 2)")


def test_different_session_allows():
    """SESSION_INDEX 최신 세션 ≠ CURRENT_SESSION 세션 → 차단 안 함."""
    clear_counter("t-diff")
    code, _ = run_hook(
        index_yaml("SESS-2", "✅E (2026-05-18, PASS)"),
        current_md("SESS-1", "B (확인 대기)", "B (확인 대기)"),
        session_id="t-diff",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 세션 ID 불일치 → 허용")


def test_missing_index_allows():
    """SESSION_INDEX.md 부재 → fail-open 허용."""
    clear_counter("t-noindex")
    code, _ = run_hook(
        "", current_md("SESS-1", "D (확인 대기)", "D (확인 대기)"),
        session_id="t-noindex", write_index=False,
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: SESSION_INDEX 부재 → fail-open")


def test_malformed_current_allows():
    """CURRENT_SESSION.md 대시보드 미탐지 → 판정 불가 → 허용."""
    clear_counter("t-malformed")
    code, _ = run_hook(
        index_yaml("SESS-1", "✅E (2026-05-18, PASS)"),
        "# 빈 문서\n구조 없음\n",
        session_id="t-malformed",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 대시보드 미탐지 → fail-open")


def test_loop_guard_releases_after_max():
    """연속 차단 한도 초과 시 fail-open (무한 루프 방지)."""
    clear_counter("t-loop")
    idx = index_yaml("SESS-1", "✅E (2026-05-18, PASS)")
    cur = current_md("SESS-1", "D (확인 대기)", "D (확인 대기)")
    for i in range(MAX_BLOCKS):
        code, _ = run_hook(idx, cur, session_id="t-loop")
        assert code == 2, f"call {i + 1}: expected 2, got {code}"
    code, _ = run_hook(idx, cur, session_id="t-loop")
    assert code == 0, f"after MAX: expected 0, got {code}"
    clear_counter("t-loop")
    print("  PASS: 연속 차단 한도 초과 → fail-open 탈출")


def test_stop_hook_active_allows():
    """stop_hook_active=True → 불일치(차단 조건)여도 즉시 허용 (무한 루프 1차 방어)."""
    clear_counter("t-active2")
    code, _ = run_hook(
        index_yaml("SESS-1", "✅E (2026-05-18, PASS)"),
        current_md("SESS-1", "D (확인 대기)", "D (확인 대기)"),  # 원래라면 차단
        session_id="t-active2",
        stop_hook_active=True,
    )
    assert code == 0, f"expected 0, got {code}"
    clear_counter("t-active2")
    print("  PASS: stop_hook_active → 차단 조건 성립해도 즉시 허용")


if __name__ == "__main__":
    tests = [
        test_active_session_allows,
        test_completed_consistent_allows,
        test_mismatch_blocks,
        test_different_session_allows,
        test_missing_index_allows,
        test_malformed_current_allows,
        test_loop_guard_releases_after_max,
        test_stop_hook_active_allows,
    ]
    print(f"gate-e-sync-guard.py 테스트 ({len(tests)}건)")
    print("=" * 50)
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
    print("=" * 50)
    print(f"결과: {passed} passed, {failed} failed / {len(tests)} total")
    sys.exit(1 if failed else 0)
