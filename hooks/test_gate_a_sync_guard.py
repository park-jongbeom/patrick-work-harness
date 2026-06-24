#!/usr/bin/env python3
"""gate-a-sync-guard.py 단위 테스트.

HARNESS-GATE-A-GUARD-1(2026-06-03). test_gate_e_sync_guard.py 하네스 복제.
가드는 CURRENT_SESSION.md 만 읽으므로 SESSION_INDEX 픽스처 불필요.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "gate-a-sync-guard.py")
MAX_BLOCKS = 3  # gate-a-sync-guard.py 와 동일해야 함


def counter_file(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".gate-a-sync-guard-{safe}.count")


def clear_counter(session_id):
    try:
        os.remove(counter_file(session_id))
    except OSError:
        pass


def run_hook(current_session, session_id="test-sess",
             write_current=True, stop_hook_active=False):
    """gate-a-sync-guard.py 를 서브프로세스로 실행, (returncode, stderr) 반환."""
    with tempfile.TemporaryDirectory() as tmpdir:
        if write_current:
            with open(os.path.join(tmpdir, "CURRENT_SESSION.md"), "w",
                      encoding="utf-8") as f:
                f.write(current_session)

        env = os.environ.copy()
        env["GATE_A_GUARD_BASE"] = tmpdir
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

def current_md(session_id, status, gate_cell,
               topic="테스트 세션 주제", intent="테스트 작업 의도 1~2문장.",
               gate_progress="A⏳ → B☐ → C☐ → E☐", start_date="2026-06-03"):
    """CURRENT_SESSION.md 픽스처. 의도 2줄·Gate 진행·착수일 기본 채움."""
    topic_line = f"> **세션 주제**: {topic}\n" if topic is not None else ""
    intent_line = f"> **작업 의도**: {intent}\n" if intent is not None else ""
    gp_row = (
        f"| Gate 진행 | {gate_progress} |\n" if gate_progress is not None else ""
    )
    sd_row = f"| 착수일 | {start_date} |\n" if start_date is not None else ""
    return (
        "# 현재 세션 상태\n\n"
        f"> **세션 ID**: {session_id} (테스트)\n"
        f"{topic_line}"
        f"{intent_line}"
        f"> **현재 상태**: {status}\n\n"
        "## 대시보드\n\n"
        "| 항목 | 값 |\n"
        "|------|-----|\n"
        f"| 현재 Gate | **{gate_cell}** |\n"
        f"{gp_row}"
        f"{sd_row}"
    )


# --- 테스트 ---

def test_gate_a_complete_allows():
    """Gate A 진행 중 + 필수 필드 전부 채움 → 허용."""
    clear_counter("t-a-ok")
    code, _ = run_hook(
        current_md("SESS-1", "A (승인 대기)", "A (승인 대기)"),
        session_id="t-a-ok",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: Gate A + 필드 완비 → 허용")


def test_gate_a_missing_intent_blocks():
    """Gate A 진행 중인데 '작업 의도' 누락 → 차단(exit 2)."""
    clear_counter("t-a-noint")
    code, err = run_hook(
        current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", intent=None),
        session_id="t-a-noint",
    )
    assert code == 2, f"expected 2, got {code}"
    assert "GATE-A-SYNC" in err, f"expected guard message, got: {err}"
    assert "작업 의도" in err, f"expected 누락 필드 명시, got: {err}"
    clear_counter("t-a-noint")
    print("  PASS: Gate A + 작업 의도 누락 → 차단(exit 2)")


def test_gate_a_missing_topic_blocks():
    """Gate A 진행 중인데 '세션 주제' 누락 → 차단."""
    clear_counter("t-a-notop")
    code, err = run_hook(
        current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", topic=None),
        session_id="t-a-notop",
    )
    assert code == 2, f"expected 2, got {code}"
    assert "세션 주제" in err, f"expected 누락 필드 명시, got: {err}"
    clear_counter("t-a-notop")
    print("  PASS: Gate A + 세션 주제 누락 → 차단")


def test_gate_a_missing_gate_progress_blocks():
    """Gate A 진행 중인데 'Gate 진행' 행 누락 → 차단."""
    clear_counter("t-a-nogp")
    code, err = run_hook(
        current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", gate_progress=None),
        session_id="t-a-nogp",
    )
    assert code == 2, f"expected 2, got {code}"
    assert "Gate 진행" in err, f"expected 누락 필드 명시, got: {err}"
    clear_counter("t-a-nogp")
    print("  PASS: Gate A + Gate 진행 누락 → 차단")


def test_gate_b_phase_allows():
    """Gate B 단계(A 아님) → 의도 누락이어도 발동 안 함(허용)."""
    clear_counter("t-b")
    code, _ = run_hook(
        current_md("SESS-1", "B (확인 대기)", "B (확인 대기)", intent=None),
        session_id="t-b",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: Gate B 단계 → 발동 안 함(허용)")


def test_gate_e_done_allows():
    """✅E 완료 → 발동 안 함(허용)."""
    clear_counter("t-e")
    code, _ = run_hook(
        current_md("SESS-1", "✅E 완료 (2026-06-03)", "✅E 완료", intent=None),
        session_id="t-e",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: ✅E 완료 → 발동 안 함(허용)")


def test_missing_file_allows():
    """CURRENT_SESSION.md 부재 → fail-open 허용."""
    clear_counter("t-nofile")
    code, _ = run_hook("", session_id="t-nofile", write_current=False)
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: CURRENT_SESSION 부재 → fail-open")


def test_malformed_allows():
    """구조 미탐지(세션 ID·Gate 없음) → 판정 불가 → 허용."""
    clear_counter("t-mal")
    code, _ = run_hook("# 빈 문서\n구조 없음\n", session_id="t-mal")
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 구조 미탐지 → fail-open")


def test_loop_guard_releases_after_max():
    """연속 차단 한도 초과 시 fail-open (무한 루프 방지)."""
    clear_counter("t-loop")
    cur = current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", intent=None)
    for i in range(MAX_BLOCKS):
        code, _ = run_hook(cur, session_id="t-loop")
        assert code == 2, f"call {i + 1}: expected 2, got {code}"
    code, _ = run_hook(cur, session_id="t-loop")
    assert code == 0, f"after MAX: expected 0, got {code}"
    clear_counter("t-loop")
    print("  PASS: 연속 차단 한도 초과 → fail-open 탈출")


def test_stop_hook_active_allows():
    """stop_hook_active=True → 차단 조건 성립해도 즉시 허용 (무한 루프 1차 방어)."""
    clear_counter("t-sha")
    code, _ = run_hook(
        current_md("SESS-1", "A (승인 대기)", "A (승인 대기)", intent=None),
        session_id="t-sha",
        stop_hook_active=True,
    )
    assert code == 0, f"expected 0, got {code}"
    clear_counter("t-sha")
    print("  PASS: stop_hook_active → 차단 조건 성립해도 즉시 허용")


if __name__ == "__main__":
    tests = [
        test_gate_a_complete_allows,
        test_gate_a_missing_intent_blocks,
        test_gate_a_missing_topic_blocks,
        test_gate_a_missing_gate_progress_blocks,
        test_gate_b_phase_allows,
        test_gate_e_done_allows,
        test_missing_file_allows,
        test_malformed_allows,
        test_loop_guard_releases_after_max,
        test_stop_hook_active_allows,
    ]
    print(f"gate-a-sync-guard.py 테스트 ({len(tests)}건)")
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
