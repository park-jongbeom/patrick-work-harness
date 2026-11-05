#!/usr/bin/env python3
"""master-plan-stale-guard.py 단위 테스트."""

import json
import os
import re
import subprocess
import sys
import tempfile

# Windows cp949 콘솔에서 '—'·'✅' 등 출력 시 UnicodeEncodeError 방지 (Python 3.7+)
sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = os.path.join(os.path.dirname(__file__), "master-plan-stale-guard.py")
MAX_BLOCKS = 3  # master-plan-stale-guard.py 와 동일해야 함


def counter_file(session_id):
    """master-plan-stale-guard.py counter_path() 와 동일 경로여야 clear_counter 가 유효."""
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join(tempfile.gettempdir(), f".master-plan-stale-guard-{safe}.count")


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
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
        return proc.returncode, proc.stderr.strip()


# --- 픽스처 ---

def run_with(files, session_id="test-sess"):
    """파일 여러 개({상대경로: 내용})를 둔 프로젝트에서 실행 — 설정 파일·다른 이름의 인덱스용."""
    clear_counter(session_id)
    with tempfile.TemporaryDirectory() as tmpdir:
        for rel, content in files.items():
            path = os.path.join(tmpdir, rel.replace("<ROOT>", tmpdir)) if not rel.startswith("<ROOT>") else rel.replace("<ROOT>", tmpdir)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content.replace("<ROOT>", tmpdir))
        env = os.environ.copy()
        env["MASTER_PLAN_GUARD_BASE"] = tmpdir
        proc = subprocess.run([sys.executable, SCRIPT], input=json.dumps({"session_id": session_id}),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    clear_counter(session_id)
    return proc.returncode


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
        'name: "작업 계획 인덱스"\n'
        'version: 7.1\n'
        f'status: "{session_id} {extra_desc} · 파일 N개."\n'
        '---\n'
        '\n'
        '# 작업 계획 인덱스\n'
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


def test_loop_guard_stays_released_after_max():
    clear_counter("t-cycle")
    idx = current_md("HARNESS-STALE-GUARD-1")
    plan = master_plan_md("PLAN-SYNC-13")
    codes = [run_hook(idx, plan, session_id="t-cycle")[0] for _ in range(MAX_BLOCKS + 5)]
    assert codes == [2] * MAX_BLOCKS + [0] * 5, codes
    clear_counter("t-cycle")
    print("  PASS: 한도 뒤 다시 막지 않는다")


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


def test_session_topic_field_fallback_allows():
    """'**세션 ID**' 없고 '**세션 주제**'만 있는 세션 → 2단 폴백으로 정확히 추출, 일치 시 허용."""
    clear_counter("t-topic")
    current = (
        '# 현재 세션 상태\n\n'
        '> **현재 상태**: A (승인 대기)\n'
        '> **세션 주제**: FIX-B-STALE-GUARD-PARSER-1 — 파서 오탐 수리\n'
    )
    code, _ = run_hook(
        current,
        master_plan_md("FIX-B-STALE-GUARD-PARSER-1"),
        session_id="t-topic",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: '**세션 주제**' 필드 폴백 → 정확 추출, 허용")


def test_body_heading_no_longer_misparsed():
    """'**세션 주제**' 필드가 있으면, 본문에 먼저 나오는 '## Gate A 계획' 같은
    소제목이 있어도 그것으로 오인 캡처하지 않는다 (HARNESS-WIN-PORT-3-a 재현 케이스)."""
    clear_counter("t-body-heading")
    current = (
        '# 현재 세션 상태\n\n'
        '> **현재 상태**: ✅E 완료 (2026-07-27)\n'
        '> **세션 주제**: HARNESS-WIN-PORT-3-a — Docker 명령 경로 치환\n\n'
        '## Gate A 계획 (승인됨)\n\n'
        '내용...\n'
    )
    code, _ = run_hook(
        current,
        master_plan_md("HARNESS-WIN-PORT-3-a"),
        session_id="t-body-heading",
    )
    assert code == 0, f"expected 0 (no false-positive), got {code}"
    clear_counter("t-body-heading")
    print("  PASS: 본문 소제목 오탐 방지 — '**세션 주제**' 폴백이 우선 적용")


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


def test_underscore_session_id_is_the_same_session():
    """인덱스 쪽이 밑줄 앞에서 잘려 같은 세션을 불일치로 막았다(2026-11-05 재현: FEAT_LOGIN-1 대 FEAT)."""
    assert run_with({"CURRENT_SESSION.md": current_md("FEAT_LOGIN-1"),
                     "00_MASTER_PLAN.md": master_plan_md("FEAT_LOGIN-1")}) == 0
    assert run_with({"CURRENT_SESSION.md": current_md("FEAT_LOGIN-2"),
                     "00_MASTER_PLAN.md": master_plan_md("FEAT_LOGIN-1")}) == 2
    print("  PASS: 밑줄 세션 ID 를 끝까지 읽는다")


def test_completed_status_is_not_read_as_an_id():
    assert run_with({"CURRENT_SESSION.md": current_md("FEAT-2"),
                     "00_MASTER_PLAN.md": master_plan_md("✅E", "완료")}) == 0
    print("  PASS: 완료 표기는 세션 ID 가 아니다")


def test_configured_index_name_is_guarded():
    """`master_plan_file` 을 다른 이름으로 둔 프로젝트에서 가드가 조용히 꺼져 있었다."""
    yml = 'plan_tier: "2"\nmaster_plan_file: "docs/PLAN_INDEX.md"   # 인덱스\n'
    assert run_with({".claude/harness-answers.yml": yml, "CURRENT_SESSION.md": current_md("NEW-2"),
                     "docs/PLAN_INDEX.md": master_plan_md("OLD-1")}) == 2
    assert run_with({".claude/harness-answers.yml": yml, "CURRENT_SESSION.md": current_md("NEW-2"),
                     "docs/PLAN_INDEX.md": master_plan_md("NEW-2")}) == 0
    print("  PASS: 설정한 인덱스 파일을 본다")


def test_absolute_index_path():
    yml = "master_plan_file: <ROOT>/elsewhere/INDEX.md\n"
    assert run_with({".claude/harness-answers.yml": yml, "CURRENT_SESSION.md": current_md("NEW-2"),
                     "<ROOT>/elsewhere/INDEX.md": master_plan_md("OLD-1")}) == 2
    print("  PASS: 절대경로 인덱스")


def test_single_plan_tier_has_no_index():
    """plan_tier 1 은 인덱스 문서가 없다 — 남은 00_MASTER_PLAN.md 를 보고 막지 않는다."""
    assert run_with({".claude/harness-answers.yml": 'plan_tier: "1"\n', "CURRENT_SESSION.md": current_md("NEW-2"),
                     "00_MASTER_PLAN.md": master_plan_md("OLD-1")}) == 0
    print("  PASS: 단일 계획 문서 프로젝트는 보지 않는다")


def test_unfilled_placeholder_falls_back_to_the_default_name():
    yml = 'master_plan_file: "${MASTER_PLAN_FILE}"\n'
    assert run_with({".claude/harness-answers.yml": yml, "CURRENT_SESSION.md": current_md("NEW-2"),
                     "00_MASTER_PLAN.md": master_plan_md("OLD-1")}) == 2
    print("  PASS: 채우지 않은 자리표시는 기본 이름으로")


if __name__ == "__main__":
    tests = [
        test_fresh_allows,
        test_stale_blocks,
        test_missing_current_allows,
        test_missing_plan_allows,
        test_malformed_plan_allows,
        test_status_multi_session_ids_uses_first,
        test_loop_guard_releases_after_max,
        test_loop_guard_stays_released_after_max,
        test_session_topic_field_fallback_allows,
        test_body_heading_no_longer_misparsed,
        test_stop_hook_active_allows,
        test_underscore_session_id_is_the_same_session,
        test_completed_status_is_not_read_as_an_id,
        test_configured_index_name_is_guarded,
        test_absolute_index_path,
        test_single_plan_tier_has_no_index,
        test_unfilled_placeholder_falls_back_to_the_default_name,
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
