#!/usr/bin/env python3
"""commit-msg-guard.py 시험 (HARNESS-TEST-GAP-1, 2026-09-24).

이 훅은 `hooks.json` 에 PreToolUse 로 등록돼 **실제로 차단(exit 2)하는데**
시험이 하나도 없었다. 차단형 가드가 조용히 망가지면 「통과시켜야 할 것을
막거나」·「막아야 할 것을 통과시키거나」 둘 다 눈에 띄지 않는다.

계약:
  - exit 0 = 통과, exit 2 = 차단(사유는 stderr)
  - 판정 불가(메시지 추출 실패·JSON 파싱 실패)는 **통과**한다 — 오탐 차단 회피
"""

import json
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "commit-msg-guard.py")


def run_hook(command=None, tool_name="Bash", raw_stdin=None):
    """훅을 서브프로세스로 실행, (returncode, stderr) 반환."""
    if raw_stdin is None:
        payload = {"tool_name": tool_name, "tool_input": {"command": command or ""}}
        raw_stdin = json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=raw_stdin,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, proc.stderr


class TestCommitMsgGuard(unittest.TestCase):

    # ── 통과해야 하는 것 ────────────────────────────────
    def test_valid_type_and_scope(self):
        rc, err = run_hook('git commit -m "feat(school): 학교 임베딩 추가"')
        self.assertEqual(rc, 0, err)

    def test_valid_without_scope(self):
        rc, err = run_hook('git commit -m "docs: 설치 절차 정정"')
        self.assertEqual(rc, 0, err)

    def test_all_valid_types_pass(self):
        for t in ("feat", "fix", "refactor", "test", "docs", "chore", "style", "perf"):
            with self.subTest(type=t):
                rc, err = run_hook(f'git commit -m "{t}: 제목"')
                self.assertEqual(rc, 0, f"{t} 가 막혔다: {err}")

    def test_heredoc_multiline_checks_first_line_only(self):
        """본문이 여러 줄이어도 첫 줄만 본다 — 실제로 쓰는 형태다."""
        cmd = (
            'git commit -m "$(cat <<\'EOF\'\n'
            'fix(hooks): 로케일 차이로 훅 설치가 건너뛰던 문제\n'
            '\n'
            '본문 줄은 형식 검사 대상이 아니다.\n'
            'EOF\n'
            ')"'
        )
        rc, err = run_hook(cmd)
        self.assertEqual(rc, 0, err)

    # ── 차단해야 하는 것 ────────────────────────────────
    def test_missing_type_blocks(self):
        rc, err = run_hook('git commit -m "학교 임베딩 추가"')
        self.assertEqual(rc, 2, "타입 없는 메시지가 통과했다")
        self.assertIn("형식 위반", err)

    def test_unknown_type_blocks(self):
        rc, err = run_hook('git commit -m "update: 제목"')
        self.assertEqual(rc, 2, "허용되지 않은 타입이 통과했다")

    def test_missing_colon_space_blocks(self):
        rc, err = run_hook('git commit -m "feat 제목"')
        self.assertEqual(rc, 2, "구분자 없는 메시지가 통과했다")

    def test_block_reason_goes_to_stderr(self):
        """exit 2 일 때 Claude 에게 전달되는 통로는 stderr 다."""
        rc, err = run_hook('git commit -m "잘못된 형식"')
        self.assertEqual(rc, 2)
        self.assertIn("올바른 형식", err)
        self.assertIn("허용 타입", err)

    # ── 판정하지 않고 통과시켜야 하는 것 (오탐 차단 회피) ──
    def test_non_bash_tool_passes(self):
        rc, _ = run_hook('git commit -m "잘못된 형식"', tool_name="Edit")
        self.assertEqual(rc, 0, "Bash 가 아닌 도구를 판정했다")

    def test_non_commit_command_passes(self):
        rc, _ = run_hook('git status')
        self.assertEqual(rc, 0, "commit 이 아닌 명령을 판정했다")

    def test_unparsable_message_passes(self):
        """메시지를 못 뽑으면 통과 — 추출 실패로 막으면 오탐이 된다."""
        rc, _ = run_hook('git commit --amend --no-edit')
        self.assertEqual(rc, 0, "메시지 없는 commit 을 막았다")

    def test_malformed_stdin_passes(self):
        """깨진 stdin 에 죽지 않는다 — 가드 크래시는 곧 무력화다."""
        rc, _ = run_hook(raw_stdin="{not json")
        self.assertEqual(rc, 0, "깨진 stdin 에서 통과하지 않았다")

    def test_empty_stdin_passes(self):
        rc, _ = run_hook(raw_stdin="")
        self.assertEqual(rc, 0, "빈 stdin 에서 통과하지 않았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
