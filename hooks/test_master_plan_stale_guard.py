#!/usr/bin/env python3
"""master-plan-stale-guard.py 단위 테스트."""

import json
import os
import re
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "master-plan-stale-guard.py")
MAX_BLOCKS = 3  # master-plan-stale-guard.py 와 동일해야 함


def counter_file(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".master-plan-stale-guard-{safe}.count")


def clear_counter(session_id):
    try:
        os.remove(counter_file(session_id))
    except OSError:
        pass


def run_hook(current_session_content, master_plan_content, session_id="test-sess",
             write_current=True, write_plan=True, stop_hook_active=False):
    """master-plan-stale-guard.py 를 서브프로세스로 실행, (returncode, stderr) 반환.

    HARNESS-GATE-A-GUARD-1(2026-06-03) 파서 복구에 맞춰 비교 정본을
    SESSION_INDEX.md → CURRENT_SESSION.md 로 전환. 인자 1은 CURRENT_SESSION 내용.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        if write_current:
            with open(os.path.join(tmpdir, "CURRENT_SESSION.md"), "w",
                      encoding="utf-8") as f:
                f.write(current_session_content)
        if write_plan:
            with open(os.path.join(tmpdir, "00_MASTER_PLAN.md"), "w",
                      encoding="utf-8") as f:
                f.write(master_plan_content)

        env = os.environ.copy()
        env["MASTER_PLAN_GUARD_BASE"] = tmpdir
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

def current_md(session_id):
    """CURRENT_SESSION.md 헤더 '**세션 ID**' 픽스처 (복구 후 SSOT)."""
    return (
        '# 현재 세션 상태\n\n'
        f'> **세션 ID**: {session_id} (테스트)\n'
        '> **현재 상태**: A (승인 대기)\n'
    )


def master_plan_md(session_id, extra_desc="현재 작업 설명"):
    return (
        '---\n'
        'name: "Go Almond 작업 계획 인덱스"\n'
        'version: 7.1\n'
        f'status: "{session_id} {extra_desc} · 파일 N개."\n'
        '---\n'
        '\n'
        '# Go Almond 작업 계획 인덱스\n'
    )


# --- 테스트 ---

def test_fresh_allows():
    """CURRENT_SESSION 세션 ID == L7 status 첫 토큰 → 허용."""
    clear_counter("t-fresh")
    code, _ = run_hook(
        current_md("HARNESS-STALE-GUARD-1"),
        master_plan_md("HARNESS-STALE-GUARD-1"),
        session_id="t-fresh",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 신선 (일치) → 허용")


def test_stale_blocks():
    """CURRENT_SESSION 세션 ID != L7 status 첫 토큰 → 차단(exit 2)."""
    clear_counter("t-stale")
    code, err = run_hook(
        current_md("HARNESS-STALE-GUARD-1"),
        master_plan_md("PLAN-SYNC-13"),  # 구버전 세션 ID
        session_id="t-stale",
    )
    assert code == 2, f"expected 2, got {code}"
    assert "MASTER-PLAN-STALE" in err, f"expected guard message, got: {err}"
    assert "HARNESS-STALE-GUARD-1" in err, f"expected new session id in message"
    assert "PLAN-SYNC-13" in err, f"expected stale session id in message"
    clear_counter("t-stale")
    print("  PASS: 스테일 (불일치) → 차단(exit 2)")


def test_missing_current_allows():
    """CURRENT_SESSION.md 부재 → fail-open 허용."""
    clear_counter("t-noindex")
    code, _ = run_hook(
        "", master_plan_md("PLAN-SYNC-13"),
        session_id="t-noindex", write_current=False,
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: CURRENT_SESSION 부재 → fail-open")


def test_missing_plan_allows():
    """00_MASTER_PLAN.md 부재 → fail-open 허용."""
    clear_counter("t-noplan")
    code, _ = run_hook(
        current_md("HARNESS-STALE-GUARD-1"), "",
        session_id="t-noplan", write_plan=False,
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 00_MASTER_PLAN 부재 → fail-open")


def test_malformed_plan_allows():
    """L7 status 파싱 불가 → fail-open 허용."""
    clear_counter("t-malformed")
    code, _ = run_hook(
        current_md("HARNESS-STALE-GUARD-1"),
        "# 빈 문서\nstatus 없음\n",
        session_id="t-malformed",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: L7 status 파싱 불가 → fail-open")


def test_status_multi_session_ids_uses_first():
    """status에 여러 세션 ID 등장해도 첫 토큰만으로 비교."""
    clear_counter("t-multi")
    # 첫 토큰이 CURRENT_SESSION 세션 ID와 일치 → 허용
    plan = (
        '---\n'
        'status: "HARNESS-STALE-GUARD-1 Gate A 승인 대기 (PLAN-SYNC-14 ✅E 직후). "\n'
        '---\n'
    )
    code, _ = run_hook(
        current_md("HARNESS-STALE-GUARD-1"),
        plan,
        session_id="t-multi",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: status 다중 세션 ID → 첫 토큰만 비교, 일치 시 허용")


def test_loop_guard_releases_after_max():
    """연속 차단 한도 초과 시 fail-open (무한 루프 방지)."""
    clear_counter("t-loop")
    idx = current_md("HARNESS-STALE-GUARD-1")
    plan = master_plan_md("PLAN-SYNC-13")
    for i in range(MAX_BLOCKS):
        code, _ = run_hook(idx, plan, session_id="t-loop")
        assert code == 2, f"call {i + 1}: expected 2, got {code}"
    code, _ = run_hook(idx, plan, session_id="t-loop")
    assert code == 0, f"after MAX: expected 0, got {code}"
    clear_counter("t-loop")
    print("  PASS: 연속 차단 한도 초과 → fail-open 탈출")


def test_stop_hook_active_allows():
    """stop_hook_active=True → 스테일(불일치)이어도 즉시 허용 (무한 루프 1차 방어)."""
    clear_counter("t-active")
    code, _ = run_hook(
        current_md("HARNESS-STALE-GUARD-1"),
        master_plan_md("PLAN-SYNC-13"),  # 불일치 = 원래라면 차단
        session_id="t-active",
        stop_hook_active=True,
    )
    assert code == 0, f"expected 0, got {code}"
    clear_counter("t-active")
    print("  PASS: stop_hook_active → 차단 조건 성립해도 즉시 허용")


if __name__ == "__main__":
    tests = [
        test_fresh_allows,
        test_stale_blocks,
        test_missing_current_allows,
        test_missing_plan_allows,
        test_malformed_plan_allows,
        test_status_multi_session_ids_uses_first,
        test_loop_guard_releases_after_max,
        test_stop_hook_active_allows,
    ]
    print(f"master-plan-stale-guard.py 테스트 ({len(tests)}건)")
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
