#!/usr/bin/env python3
"""gate-e-sync-guard.py 단위 테스트."""

import json
import os
import re
import subprocess
import sys
import tempfile

# Windows cp949 콘솔에서 '—'·'✅' 등 출력 시 UnicodeEncodeError 방지 (Python 3.7+)
sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = os.path.join(os.path.dirname(__file__), "gate-e-sync-guard.py")
MAX_BLOCKS = 3  # gate-e-sync-guard.py 와 동일해야 함


def counter_file(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join(tempfile.gettempdir(), f".gate-e-sync-guard-{safe}.count")


def clear_counter(session_id):
    """기존 불일치 카운터와 Gate D 카운터(`<세션>-gate-d`)를 함께 지운다 — 남으면 다음 실행에서 한도 해제로 통과한다."""
    for sid in (session_id, f"{session_id}-gate-d"):
        try:
            os.remove(counter_file(sid))
        except OSError:
            pass


def run_hook(session_index, current_session, session_id="test-sess",
             write_index=True, write_current=True, stop_hook_active=False, transcript=None):
    """gate-e-sync-guard.py 를 서브프로세스로 실행, (returncode, stderr) 반환.

    transcript: 대화 기록 줄(dict) 목록 — 주면 JSONL 로 써서 transcript_path 로 넘긴다.
    """
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
        if transcript is not None:
            tpath = os.path.join(tmpdir, "transcript.jsonl")
            with open(tpath, "w", encoding="utf-8") as f:
                for event in transcript:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            payload["transcript_path"] = tpath
        if stop_hook_active:
            payload["stop_hook_active"] = True
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
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


GATE_D = "## Gate D 검증\n\n- self-debug 0회 · 수렴\n- FIX-B 0건 · DEP 0건\n"


def wrote(tool, **inp):
    """이 대화에서 모델이 도구로 무언가를 쓴 기록 한 줄."""
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": tool, "input": inp}]}}


def wrote_e(path="/w/CURRENT_SESSION.md"):
    return wrote("Edit", file_path=path, old_string="C (확인 대기)", new_string="✅E 완료 (2026-10-28)")


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


# --- Gate D 기록 없이 ✅E (2026-10-28) ---
# 대조 실험의 「C~E 일괄」 8회 중 2회가 Gate D 블록 없이 ✅E 로 끝났다. Gate D 기록 확인은 자율 레인 가드에만
# 있었다. 이 대화가 ✅E 를 써 넣었을 때만 본다 — 이전 세션이 ✅E 로 남은 프로젝트의 다른 대화를 막지 않는다.

def test_e_without_gate_d_written_this_session_blocks():
    clear_counter("t-nod")
    code, err = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료"),
                         session_id="t-nod", transcript=[wrote_e()])
    assert code == 2, f"expected 2, got {code}"
    assert "Gate D" in err and "self-debug" in err, err
    clear_counter("t-nod")
    print("  PASS: 이 대화가 ✅E 를 썼는데 Gate D 기록 없음 → 차단")


def test_e_with_gate_d_record_allows():
    clear_counter("t-withd")
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료") + GATE_D,
                       session_id="t-withd", transcript=[wrote_e()])
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: Gate D 표지 있음 → 허용")


def test_e_from_earlier_session_allows():
    """✅E 가 이전 대화에서 쓰였다(이 대화 기록에는 ✅E 쓰기가 없다) → 허용."""
    clear_counter("t-old")
    other = wrote("Edit", file_path="/w/src/app.ts", old_string="a", new_string="✅E")   # 다른 파일
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료"),
                       session_id="t-old", transcript=[other])
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 이전 대화의 ✅E → 허용")


def test_e_written_by_bash_heredoc_blocks():
    clear_counter("t-bash")
    cmd = "cat >> CURRENT_SESSION.md <<'EOF'\n> **현재 상태**: ✅ E 완료\nEOF"
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅ E 완료", "✅ E 완료"),
                       session_id="t-bash", transcript=[wrote("Bash", command=cmd)])
    assert code == 2, f"expected 2, got {code}"
    clear_counter("t-bash")
    print("  PASS: Bash 로 ✅E 를 쓴 것도 본다 → 차단")


def test_gate_d_block_releases_after_max():
    clear_counter("t-dmax")
    args = (index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료"))
    codes = [run_hook(*args, session_id="t-dmax", transcript=[wrote_e()])[0] for _ in range(MAX_BLOCKS + 1)]
    assert codes == [2] * MAX_BLOCKS + [0], codes
    clear_counter("t-dmax")
    print(f"  PASS: Gate D 차단도 {MAX_BLOCKS}회 뒤 해제")


def test_gate_d_marker_needs_both_counts():
    """표지 하나만 있으면 기록으로 보지 않는다(자율 레인 가드와 같은 판정)."""
    clear_counter("t-half")
    half = current_md("SESS-1", "✅E 완료", "✅E 완료") + "## Gate D 검증\n\n- self-debug 1회\n"
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), half, session_id="t-half", transcript=[wrote_e()])
    assert code == 2, f"expected 2, got {code}"
    clear_counter("t-half")
    print("  PASS: 표지 하나만 → 차단")


def test_e_in_index_only_without_session_doc_blocks():
    """CURRENT_SESSION.md 를 쓰지 않고 SESSION_INDEX.md 에만 ✅E 를 쓴 경우(재생 실험 1회) → 차단."""
    clear_counter("t-idx")
    stub = "# 현재 세션 상태\n\n> **현재 상태**: 세션 없음\n"
    row = wrote("Edit", file_path="/w/SESSION_INDEX.md", old_string="| X |", new_string="| AI-REF-1 | t | repo | ✅E (완료) |")
    code, err = run_hook(index_yaml("AI-REF-1", "✅E"), stub, session_id="t-idx", transcript=[row])
    assert code == 2 and "Gate D" in err, f"expected 2, got {code}: {err}"
    clear_counter("t-idx")
    print("  PASS: SESSION_INDEX 에만 ✅E, 세션 문서 없음 → 차단")


def test_gate_d_markers_moved_to_archive_allows():
    """doc-cleanup 등으로 본문이 아카이브로 옮겨졌어도 이 대화가 D 표지를 썼으면 기록으로 본다."""
    clear_counter("t-arch")
    arch = wrote("Write", file_path="/w/tasks/archive/ARCHIVE_X.md", content=GATE_D)
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료"),
                       session_id="t-arch", transcript=[wrote_e(), arch])
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 이 대화가 아카이브에 D 표지를 씀 → 허용")


def test_doc_cleanup_in_this_conversation_allows():
    clear_counter("t-clean")
    skill = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill",
                                                           "input": {"skill": "patrick-work-harness:doc-cleanup"}}]}}
    code, _ = run_hook(index_yaml("SESS-1", "✅E"), current_md("SESS-1", "✅E 완료", "✅E 완료"),
                       session_id="t-clean", transcript=[wrote_e(), skill])
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 이 대화가 doc-cleanup 을 부름(본문이 옮겨짐) → 허용")


def test_mention_of_previous_e_in_new_session_allows():
    """새 세션(A)을 열며 「직전 세션: … ✅E」만 썼다 → 이 대화가 세션을 닫은 것이 아니다 → 허용 (2026-10-29 실사용 오탐)."""
    clear_counter("t-mention")
    cur = wrote("Write", file_path="/w/CURRENT_SESSION.md",
                content="> **현재 상태**: A (승인 대기)\n> **직전 세션**: SESS-0 ✅E (2026-10-29)\n")
    idx = wrote("Edit", file_path="/w/SESSION_INDEX.md", old_string='gate: "✅E"',
                new_string='gate: "A (승인 대기) — 직전 SESS-0 ✅E"')
    code, err = run_hook(index_yaml("SESS-1", "A (승인 대기)"), current_md("SESS-1", "A (승인 대기)", "A (승인 대기)"),
                         session_id="t-mention", transcript=[cur, idx])
    assert code == 0, f"expected 0, got {code}: {err}"
    clear_counter("t-mention")
    print("  PASS: 새 세션에서 직전 세션 ✅E 언급만 → 허용")


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
        # Gate D 기록 없이 ✅E (2026-10-28)
        test_e_without_gate_d_written_this_session_blocks,
        test_e_with_gate_d_record_allows,
        test_e_from_earlier_session_allows,
        test_e_written_by_bash_heredoc_blocks,
        test_gate_d_block_releases_after_max,
        test_gate_d_marker_needs_both_counts,
        test_e_in_index_only_without_session_doc_blocks,
        test_gate_d_markers_moved_to_archive_allows,
        test_doc_cleanup_in_this_conversation_allows,
        test_mention_of_previous_e_in_new_session_allows,
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
