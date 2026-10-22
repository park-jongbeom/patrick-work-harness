"""comprehension-pending-guard.py 시험 — 답을 기다리는 이해도 질문이 있으면 gate-c·d·e 진입을 막는다."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comprehension-pending-guard.py")

PENDING_DOC = """# 현재 세션 상태

## Gate A — 계획

### 이해 브리핑
- **왜 바꾸나**: 이유

## Gate B — 이해도 게이트

### 질문 1
예산을 넓혀도 0곳이면 무엇을 하나?
- **읽을 곳**: 이해 브리핑 「어떻게 동작하나」
- **평가**: (답변 후 기록)
"""

ANSWERED_DOC = PENDING_DOC.replace("(답변 후 기록)", "통과 — 예산 제외 재필터를 정확히 짚음")
SKIPPED_DOC = PENDING_DOC.replace("(답변 후 기록)", "미답 — 사용자 스킵")


def run_hook(payload, doc=None, raw_stdin=None, transcript=None):
    """transcript: 대화 기록 줄(dict) 목록. "missing" 이면 없는 경로를 준다."""
    with tempfile.TemporaryDirectory() as base:
        if doc is not None:
            with open(os.path.join(base, "CURRENT_SESSION.md"), "w", encoding="utf-8") as f:
                f.write(doc)
        if transcript is not None and payload is not None:
            payload = dict(payload)
            tpath = os.path.join(base, "transcript.jsonl")
            payload["transcript_path"] = tpath
            if transcript != "missing":
                with open(tpath, "w", encoding="utf-8") as f:
                    for line in transcript:
                        f.write(json.dumps(line, ensure_ascii=False) + "\n")
        env = {**os.environ, "COMPREHENSION_PENDING_GUARD_BASE": base, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=raw_stdin if raw_stdin is not None else json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None), proc.stderr


def typed(name):
    return {"hook_event_name": "UserPromptExpansion", "expansion_type": "slash_command",
            "command_name": name, "prompt": f"/{name}"}


def model_call(name):
    return {"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": name}}


def tx_skill(name, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}


def tx_slash(name):
    return {"type": "user", "message": {"role": "user",
            "content": f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>"}}


class TestComprehensionPendingGuard(unittest.TestCase):

    def test_typed_gate_c_blocked_while_pending(self):
        rc, out, _ = run_hook(typed("gate-c"), PENDING_DOC)
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "block")
        self.assertIn("질문 1", out["reason"])
        self.assertIn("스킵", out["reason"])

    def test_model_skill_call_denied_while_pending(self):
        rc, out, _ = run_hook(model_call("gate-c"), PENDING_DOC)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("질문 1", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_plugin_prefixed_name_is_guarded(self):
        _, out, _ = run_hook(model_call("patrick-work-harness:gate-d"), PENDING_DOC)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_answered_or_skipped_passes(self):
        for doc in (ANSWERED_DOC, SKIPPED_DOC):
            rc, out, _ = run_hook(typed("gate-c"), doc)
            self.assertEqual((rc, out), (0, None))

    def test_other_skills_pass(self):
        for payload in (typed("gate-b"), model_call("code-review"), typed("gate-a")):
            rc, out, _ = run_hook(payload, PENDING_DOC)
            self.assertEqual((rc, out), (0, None), payload)

    def test_other_tools_pass(self):
        rc, out, _ = run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                               "tool_input": {"command": "ls"}}, PENDING_DOC)
        self.assertEqual((rc, out), (0, None))

    # ── 대화 기록으로 「지금 계획의 질문인가」 판정 (S3a, 2026-10-22) ──────────────
    # 마지막 gate-a 뒤에 gate-b 가 없으면 문서의 미답 질문은 이전 계획의 것이다.

    def test_stale_question_from_an_earlier_plan_passes_with_notice(self):
        for payload in (typed("gate-c"), model_call("gate-c")):
            rc, out, _ = run_hook(payload, PENDING_DOC, transcript=[tx_slash("gate-a")])
            self.assertEqual(rc, 0)
            self.assertIsNotNone(out, payload)
            self.assertNotIn("decision", out)
            self.assertNotIn("hookSpecificOutput", out)
            self.assertIn("이전", out["systemMessage"])

    def test_new_plan_after_old_question_passes_with_notice(self):
        tx = [tx_slash("gate-a"), tx_slash("gate-b"), tx_skill("gate-a")]
        _, out, _ = run_hook(typed("gate-c"), PENDING_DOC, transcript=tx)
        self.assertIn("systemMessage", out)
        self.assertNotIn("decision", out)

    def test_question_asked_after_the_latest_plan_still_blocks(self):
        tx = [tx_slash("gate-a"), tx_skill("gate-b")]
        _, out, _ = run_hook(typed("gate-c"), PENDING_DOC, transcript=tx)
        self.assertEqual(out["decision"], "block")
        _, out, _ = run_hook(model_call("gate-d"), PENDING_DOC, transcript=tx)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_without_gate_history_it_keeps_blocking(self):
        for tx in ("missing", [], [{"type": "user", "message": {"role": "user", "content": "hello"}}]):
            _, out, _ = run_hook(typed("gate-c"), PENDING_DOC, transcript=tx)
            self.assertEqual(out["decision"], "block", tx)

    def test_subagent_gate_b_is_not_the_current_question(self):
        tx = [tx_slash("gate-a"), tx_skill("gate-b", sidechain=True)]
        _, out, _ = run_hook(typed("gate-c"), PENDING_DOC, transcript=tx)
        self.assertNotIn("decision", out)
        self.assertIn("systemMessage", out)

    def test_fail_open_without_document_or_with_bad_input(self):
        self.assertEqual(run_hook(typed("gate-c"), None)[:2], (0, None))
        self.assertEqual(run_hook(None, PENDING_DOC, raw_stdin="{not json")[:2], (0, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
