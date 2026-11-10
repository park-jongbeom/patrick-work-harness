"""test-write-guard.py 시험 — Gate D 중 시험 파일 쓰기는 ask, 그 밖은 통과."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-write-guard.py")


def session(status):
    return f"# 현재 세션 상태\n\n> **세션 ID**: S-1\n> **현재 상태**: {status}\n\n| 항목 | 내용 |\n|---|---|\n| 현재 Gate | {status} |\n"


def skill_call(name, sidechain=False, tid=None):
    """대화 기록의 Skill 도구 호출 한 줄. tid 를 주면 결과 줄과 짝지을 수 있다."""
    block = {"type": "tool_use", "name": "Skill", "input": {"skill": name}}
    if tid:
        block["id"] = tid
    return {"type": "assistant", "isSidechain": sidechain, "message": {"role": "assistant", "content": [block]}}


def tool_result(tid, error, text="ok"):
    """도구 호출의 결과 줄. 훅이 막은 호출은 `is_error: true` 로 남는다. error=None 이면 키를 뺀다 —
    실제 기록의 성공 결과는 대개 이 키가 없다."""
    block = {"type": "tool_result", "tool_use_id": tid, "content": text}
    if error is not None:
        block["is_error"] = error
    return {"type": "user", "message": {"role": "user", "content": [block]}}


#: 실제 기록 그대로의 막힘 결과. 「gate-」 글자가 없어도 읽어야 한다.
BLOCKED = "PreToolUse:Skill hook error: [레인] Gate D 기록 없음 — CURRENT_SESSION.md 에 `## Gate D` 블록이 없다"


def slash(name):
    """사용자가 `/gate-x` 를 직접 입력해 펼쳐진 한 줄."""
    return {"type": "user", "message": {"role": "user", "content":
            f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>"}}


def run_hook(tool, path, status=None, raw=None, transcript=None):
    """transcript: 대화 기록 줄(dict 또는 그대로 쓸 문자열) 목록. "missing" 이면 없는 경로를 준다."""
    with tempfile.TemporaryDirectory() as base:
        if status is not None:
            with open(os.path.join(base, "CURRENT_SESSION.md"), "w", encoding="utf-8") as f:
                f.write(session(status))
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
                   "tool_input": {"file_path": os.path.join(base, path) if path else ""}}
        if transcript == "missing":
            payload["transcript_path"] = os.path.join(base, "no-such.jsonl")
        elif transcript is not None:
            tpath = os.path.join(base, "transcript.jsonl")
            with open(tpath, "w", encoding="utf-8") as f:
                for line in transcript:
                    f.write((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n")
            payload["transcript_path"] = tpath
        proc = subprocess.run(
            [sys.executable, SCRIPT], input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "TEST_WRITE_GUARD_BASE": base, "PYTHONIOENCODING": "utf-8"},
        )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


class TestTestWriteGuard(unittest.TestCase):

    def test_gate_d_test_file_asks(self):
        for path in ("tests/test_x.py", "src/test/kotlin/AT.kt", "web/a.spec.ts", "hooks/test_guard.py"):
            rc, out = run_hook("Edit", path, "D (확인 대기)")
            self.assertEqual(rc, 0)
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", path)
            self.assertIn("명세와 시험이 실제로 충돌", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_write_and_multiedit_also_covered(self):
        for tool in ("Write", "MultiEdit"):
            _, out = run_hook(tool, "tests/test_x.py", "D (진행 중)")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_other_gates_pass(self):
        for status in ("C (확인 대기)", "A (승인 대기)", "✅E 완료 (2026-10-15)"):
            self.assertEqual(run_hook("Edit", "tests/test_x.py", status), (0, None), status)

    def test_non_test_files_pass_in_gate_d(self):
        for path in ("hooks/guard.py", "README.md", "skills/gate-d/SKILL.md"):
            self.assertEqual(run_hook("Edit", path, "D (확인 대기)"), (0, None), path)

    # ── 대화 기록 판정 (S1, 2026-10-22) ─────────────────────────────────────
    # gate-d 는 루프가 끝난 뒤 Step 6 에서야 상태를 「D (확인 대기)」로 쓴다. 루프 동안 상태는
    # gate-c 가 남긴 「C (확인 대기)」라서, 상태만 보면 지켜야 할 루프에서 가드가 꺼진다.

    def test_last_gate_d_in_transcript_asks_while_status_is_still_c(self):
        _, out = run_hook("Edit", "tests/test_x.py", "C (확인 대기)",
                          transcript=[skill_call("gate-c"), skill_call("gate-d")])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_slash_command_and_plugin_prefix_count(self):
        for line in (slash("gate-d"), skill_call("patrick-work-harness:gate-d"),
                     slash("patrick-work-harness:gate-d")):
            _, out = run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=[skill_call("gate-c"), line])
            self.assertIsNotNone(out, line)
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", line)

    def test_later_gate_ends_the_window(self):
        tx = [skill_call("gate-d"), skill_call("gate-e")]
        self.assertEqual(run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=tx), (0, None))
        tx = [skill_call("gate-d"), slash("gate-a")]
        self.assertEqual(run_hook("Edit", "tests/test_x.py", "A (승인 대기)", transcript=tx), (0, None))

    # ── 막힌 호출 (2026-11-10) ───────────────────────────────────────────────
    # 훅이 막은 Skill 호출은 실행되지 않았다. Gate D 루프 중 /gate-e 가 막혀도 창은 그대로다.
    # 재현: 막힌 /gate-e 한 줄 뒤에 Gate C 가 만든 새 시험을 고쳐도 묻지 않았다.

    def test_blocked_gate_call_does_not_end_the_window(self):
        tx = [skill_call("gate-c"), skill_call("gate-d"),
              skill_call("patrick-work-harness:gate-e", tid="e1"), tool_result("e1", True, BLOCKED)]
        _, out = run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=tx)
        self.assertIsNotNone(out, "막힌 /gate-e 가 Gate D 창을 닫았다")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_blocked_call_in_compact_json_as_written_by_claude_code(self):
        def compact(d):
            return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

        tx =[compact(skill_call("gate-d")), compact(skill_call("gate-e", tid="e1")),
              compact(tool_result("e1", True, BLOCKED))]
        _, out = run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=tx)
        self.assertIsNotNone(out, "막힌 /gate-e 가 Gate D 창을 닫았다")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_gate_call_that_ran_or_has_no_result_yet_still_ends_the_window(self):
        for error in (False, None):     # None: 실제 기록처럼 is_error 키가 없는 성공 결과
            ran = [skill_call("gate-d"), skill_call("gate-e", tid="e1"),
                   tool_result("e1", error, "Launching skill: gate-e")]
            self.assertEqual(run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=ran), (0, None), error)
        # 현재 턴의 결과는 아직 기록되지 않았을 수 있다 — 결과가 없으면 부른 것으로 본다
        pending = [skill_call("gate-d"), skill_call("gate-e", tid="e1")]
        self.assertEqual(run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=pending), (0, None))

    def test_invoked_ignores_blocked_calls(self):
        sys.path.insert(0, os.path.dirname(SCRIPT))
        from gate_transcript import invoked

        cases = {
            "blocked": ([skill_call("doc-cleanup", tid="x1"), tool_result("x1", True, "denied")], False),
            "ran": ([skill_call("doc-cleanup", tid="x1"), tool_result("x1", False)], True),
            "no result yet": ([skill_call("doc-cleanup", tid="x1")], True),
            "blocked, then ran": ([skill_call("doc-cleanup", tid="x1"), tool_result("x1", True, "denied"),
                                   skill_call("doc-cleanup", tid="x2"), tool_result("x2", False)], True),
        }
        for label, (lines, expected) in cases.items():
            with tempfile.TemporaryDirectory() as base:
                path = os.path.join(base, "t.jsonl")
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
                self.assertIs(invoked(path, "doc-cleanup"), expected, label)

    def test_subagent_lines_are_ignored(self):
        tx = [skill_call("gate-c"), skill_call("gate-d", sidechain=True)]
        self.assertEqual(run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript=tx), (0, None))

    def test_unreadable_transcript_falls_back_to_status(self):
        self.assertEqual(run_hook("Edit", "tests/test_x.py", "C (확인 대기)", transcript="missing"), (0, None))
        _, out = run_hook("Edit", "tests/test_x.py", "D (확인 대기)", transcript=["{broken", "\x00"])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_fail_open(self):
        self.assertEqual(run_hook("Edit", "tests/test_x.py", None), (0, None))   # 문서 없음
        self.assertEqual(run_hook("Bash", "tests/test_x.py", "D"), (0, None))    # 다른 도구
        self.assertEqual(run_hook("Edit", "", "D", raw="{oops"), (0, None))      # 깨진 입력


if __name__ == "__main__":
    unittest.main(verbosity=2)
