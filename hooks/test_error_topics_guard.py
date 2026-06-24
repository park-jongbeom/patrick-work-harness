#!/usr/bin/env python3
"""error-topics-guard.py 단위 테스트."""

import json
import os
import re
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "error-topics-guard.py")
MAX_BLOCKS = 3  # error-topics-guard.py 와 동일해야 함


def counter_file(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".error-topics-guard-{safe}.count")


def clear_counter(session_id):
    try:
        os.remove(counter_file(session_id))
    except OSError:
        pass


def run_hook(current_session_content, session_id="test-sess",
             index_content="", topics=None, write_current=True,
             stop_hook_active=False):
    """
    error-topics-guard.py 를 서브프로세스로 실행, (returncode, stderr) 반환.

    topics: { repo_name: { topic_file: content } } — error_topics/*.md 픽스처.
    """
    with tempfile.TemporaryDirectory() as base_dir, \
            tempfile.TemporaryDirectory() as repo_root:
        if write_current:
            with open(os.path.join(base_dir, "CURRENT_SESSION.md"), "w",
                      encoding="utf-8") as f:
                f.write(current_session_content)
        with open(os.path.join(base_dir, "SESSION_INDEX.md"), "w",
                  encoding="utf-8") as f:
            f.write(index_content)

        # error_topics 픽스처 생성
        for repo, files in (topics or {}).items():
            tdir = os.path.join(repo_root, repo, "docs", "rules", "error_topics")
            os.makedirs(tdir, exist_ok=True)
            for fname, content in files.items():
                with open(os.path.join(tdir, fname), "w", encoding="utf-8") as f:
                    f.write(content)

        env = os.environ.copy()
        env["ERROR_TOPICS_GUARD_BASE"] = base_dir
        env["ERROR_TOPICS_GUARD_REPO_ROOT"] = repo_root
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

def current_md(session_id, done=True, repos="ga-api-platform", trace="self-debug 1회"):
    """CURRENT_SESSION.md 픽스처."""
    state = "✅E 완료 (2026-05-22)" if done else "B (확인 대기)"
    gate_cell = "**✅E 완료**" if done else "**B (확인 대기)**"
    return (
        "# 현재 세션 상태\n\n"
        f"> **세션 ID**: {session_id}\n"
        f"> **현재 상태**: {state}\n\n"
        "## 대시보드\n\n"
        "| 항목 | 값 |\n"
        "|------|-----|\n"
        f"| 현재 Gate | {gate_cell} |\n"
        f"| 저장소 | {repos} |\n"
        f"| 비고 | {trace} · FIX-B/DEP 0 |\n"
    )


# --- 테스트 ---

def test_missing_current_allows():
    """CURRENT_SESSION.md 부재 → fail-open 허용."""
    clear_counter("t-nocur")
    code, _ = run_hook("", session_id="t-nocur", write_current=False)
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: CURRENT_SESSION 부재 → fail-open")


def test_not_done_allows():
    """진행 중(✅E 아님) 세션 → 검사 제외 허용."""
    clear_counter("t-inprog")
    code, _ = run_hook(
        current_md("FIX-B-SAMPLE-1", done=False),
        session_id="t-inprog",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 진행 중 세션 → 검사 제외 허용")


def test_doc_only_repo_allows():
    """문서 전용 저장소(코드 저장소 없음) → 검사 제외 허용."""
    clear_counter("t-doconly")
    code, _ = run_hook(
        current_md("FIX-B-DOC-1", repos="plans + ai-consulting-plans"),
        session_id="t-doconly",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 문서 전용 저장소 → 검사 제외 허용")


def test_no_error_trace_allows():
    """오류 흔적 없음(self-debug 0 + FIX-B/DEP 0) → 허용."""
    clear_counter("t-clean")
    code, _ = run_hook(
        current_md("GA-REVAMP-9-x", trace="self-debug 0"),
        session_id="t-clean",
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 오류 흔적 없음 → 허용")


def test_other_session_trace_in_index_allows():
    """SESSION_INDEX에 타 세션 self-debug N회 + 현재 세션 self-debug 0 → 허용.

    회귀(HARNESS-ERRTOPICS-SCOPE-1): idx_text 전역 스캔이 직전 완료 세션들의
    "self-debug N회"를 현재 세션(self-debug 0) 것으로 오인해 차단하던 오탐.
    """
    clear_counter("t-crosssess")
    index = (
        "| **SEC-ADMIN-ROLE-1** | ... · self-debug 1회 · ... | ✅E |\n"
        "| **SEC-SECRET-PURGE-1** | ... · self-debug 2회 · ... | ✅E |\n"
        "| **GA-CLEAN-2** | ... · self-debug 0 · FIX-B/DEP 0 | ✅E |\n"
    )
    code, _ = run_hook(
        current_md("GA-CLEAN-2", trace="self-debug 0"),
        session_id="t-crosssess",
        index_content=index,
    )
    assert code == 0, f"expected 0 (타 세션 흔적 무시), got {code}"
    clear_counter("t-crosssess")
    print("  PASS: 타 세션 흔적 in index + 현재 self-debug 0 → 허용")


def test_megaline_history_trace_allows():
    """메가라인(한 줄에 현재+이력 혼재) + 현재 self-debug 0 → 허용.

    회귀(HARNESS-ERRTOPICS-SCOPE-2): priority_note/next_action 는 현재 세션
    (self-debug 0)과 "이전: … self-debug N회" 과거 이력을 한 줄에 담는다.
    SCOPE-1 라인 스코핑은 라인 전체를 보므로 이력의 self-debug 를 현재 것으로
    오인해 차단(오탐 3회 재발). strip_history head 절단으로 허용되어야 한다.
    """
    clear_counter("t-megaline")
    index = (
        "priority_note: \"**GA-MEGA-1 ✅E 완료** — 작업 요약 self-debug 0 · "
        "FIX-B/DEP 0. 이전: **PREV-X ✅E** — 수정 self-debug 2회 처리.\"\n"
    )
    code, _ = run_hook(
        current_md("GA-MEGA-1", trace="self-debug 0"),
        session_id="t-megaline",
        index_content=index,
    )
    assert code == 0, f"expected 0 (메가라인 이력 흔적 무시), got {code}"
    clear_counter("t-megaline")
    print("  PASS: 메가라인 이력 흔적 + 현재 self-debug 0 → 허용")


def test_megaline_current_trace_blocks():
    """메가라인 현재 세션 head 에 진짜 흔적(self-debug 3회) + 미적재 → 차단.

    과잉 억제 회귀 방지: strip_history 가 head 를 잘라내도 현재 세션 부분은
    여전히 스캔되어야 한다(이력만 제외).
    """
    clear_counter("t-megacur")
    index = (
        "priority_note: \"**GA-MEGACUR-1 ✅E 완료** — 구현 self-debug 3회 발생. "
        "이전: **PREV-Y ✅E** — 무관 self-debug 0 처리.\"\n"
    )
    code, err = run_hook(
        current_md("GA-MEGACUR-1", trace="self-debug 0"),
        session_id="t-megacur",
        index_content=index,
        topics={"ga-api-platform": {"testing.md": "무관 내용\n"}},
    )
    assert code == 2, f"expected 2 (현재 head 흔적 차단), got {code}"
    assert "GA-MEGACUR-1" in err
    clear_counter("t-megacur")
    print("  PASS: 메가라인 현재 head 흔적 + 미적재 → 차단(exit 2)")


def test_logged_allows():
    """오류 흔적 有 + error_topics 적재됨 → 허용."""
    clear_counter("t-logged")
    code, _ = run_hook(
        current_md("FIX-B-SPOTLESS-9"),
        session_id="t-logged",
        topics={"ga-api-platform": {
            "testing.md": "## [2026-05-22] FIX-B-SPOTLESS-9 — spotless 위반\n",
        }},
    )
    assert code == 0, f"expected 0, got {code}"
    print("  PASS: 오류 흔적 有 + 적재됨 → 허용")


def test_unlogged_fixb_prefix_blocks():
    """오류 흔적(세션ID FIX-B prefix) + 미적재 → 차단(exit 2)."""
    clear_counter("t-unlogged")
    code, err = run_hook(
        current_md("FIX-B-SPOTLESS-3"),
        session_id="t-unlogged",
        topics={"ga-api-platform": {
            "testing.md": "## [2026-05-21] LSE-CLEANUP-1-d — 무관 항목\n",
        }},
    )
    assert code == 2, f"expected 2, got {code}"
    assert "ERROR-TOPICS" in err, f"expected guard message, got: {err}"
    assert "FIX-B-SPOTLESS-3" in err, "expected session id in message"
    clear_counter("t-unlogged")
    print("  PASS: FIX-B prefix 미적재 → 차단(exit 2)")


def test_unlogged_selfdebug_blocks():
    """오류 흔적(self-debug 1회 본문) + 미적재 → 차단(exit 2)."""
    clear_counter("t-sd")
    code, err = run_hook(
        current_md("DETEKT-CI-FIX-9", trace="self-debug 1회"),
        session_id="t-sd",
        topics={"ga-api-platform": {"testing.md": "무관 내용\n"}},
    )
    assert code == 2, f"expected 2, got {code}"
    assert "DETEKT-CI-FIX-9" in err
    clear_counter("t-sd")
    print("  PASS: self-debug 1회 미적재 → 차단(exit 2)")


def test_loop_guard_releases_after_max():
    """연속 차단 한도 초과 시 fail-open (무한 루프 방지)."""
    clear_counter("t-loop")
    cur = current_md("FIX-B-LOOP-1")
    topics = {"ga-api-platform": {"testing.md": "무관\n"}}
    for i in range(MAX_BLOCKS):
        code, _ = run_hook(cur, session_id="t-loop", topics=topics)
        assert code == 2, f"call {i + 1}: expected 2, got {code}"
    code, _ = run_hook(cur, session_id="t-loop", topics=topics)
    assert code == 0, f"after MAX: expected 0, got {code}"
    clear_counter("t-loop")
    print("  PASS: 연속 차단 한도 초과 → fail-open 탈출")


def test_stop_hook_active_allows():
    """stop_hook_active=True → 미적재(차단 조건)여도 즉시 허용 (무한 루프 1차 방어)."""
    clear_counter("t-active3")
    code, _ = run_hook(
        current_md("FIX-B-ACTIVE-1"),  # FIX-B prefix + 미적재 = 원래라면 차단
        session_id="t-active3",
        topics={"ga-api-platform": {"testing.md": "무관 내용\n"}},
        stop_hook_active=True,
    )
    assert code == 0, f"expected 0, got {code}"
    clear_counter("t-active3")
    print("  PASS: stop_hook_active → 차단 조건 성립해도 즉시 허용")


if __name__ == "__main__":
    tests = [
        test_missing_current_allows,
        test_not_done_allows,
        test_doc_only_repo_allows,
        test_no_error_trace_allows,
        test_other_session_trace_in_index_allows,
        test_megaline_history_trace_allows,
        test_megaline_current_trace_blocks,
        test_logged_allows,
        test_unlogged_fixb_prefix_blocks,
        test_unlogged_selfdebug_blocks,
        test_loop_guard_releases_after_max,
        test_stop_hook_active_allows,
    ]
    print(f"error-topics-guard.py 테스트 ({len(tests)}건)")
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
