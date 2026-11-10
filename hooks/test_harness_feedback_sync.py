"""harness-feedback-sync.py 시험 — 작업 PC 의 사용 기록 요약을 조건이 차면 SSH 로 보내고, 받는 쪽은 겹친 세션을 한 번만 센다.

`ssh`·`scp` 는 PATH 앞에 둔 가짜 명령이 대신한다 — 받는 서버의 홈 대신 임시 폴더에 쓰고, 받은 인자를 기록한다.
"""

import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "harness-feedback-sync.py")
ENGINE_HOOK = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/test-tampering-guard.py"'

FAKE_SSH = """#!/bin/sh
echo "ssh $*" >> "$FAKE_LOG"
[ -n "$FAKE_FAIL" ] && { echo "ssh: connect to host x port 22: Connection timed out" >&2; exit 255; }
for last; do :; done
cd "$FAKE_REMOTE" && sh -c "$last"
"""
FAKE_SCP = """#!/bin/sh
echo "scp $*" >> "$FAKE_LOG"
[ -n "$FAKE_FAIL" ] && exit 1
for last; do :; done
src=""
for a; do case "$a" in -*|BatchMode=*|ConnectTimeout=*) ;; *) [ "$a" != "$last" ] && src="$a";; esac; done
cp "$src" "$FAKE_REMOTE/${last#*:}"
"""


def load_module():
    spec = importlib.util.spec_from_file_location("harness_feedback_sync", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now_ts(minutes=0):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@unittest.skipIf(os.name == "nt", "가짜 ssh·scp 가 sh 스크립트다")
class FeedbackCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home, self.projects, self.remote = (os.path.join(self.root, n) for n in ("home", "projects", "remote"))
        self.bin, self.log = os.path.join(self.root, "bin"), os.path.join(self.root, "calls.log")
        for d in (self.home, self.projects, self.remote, self.bin):
            os.makedirs(d)
        for name, body in (("ssh", FAKE_SSH), ("scp", FAKE_SCP)):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(body)
            os.chmod(path, 0o755)

    def env(self, fail=False):
        env = {**os.environ, "HARNESS_FEEDBACK_HOME": self.home, "HARNESS_FEEDBACK_PROJECTS": self.projects,
               "HARNESS_FEEDBACK_FOREGROUND": "1", "PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
               "FAKE_LOG": self.log, "FAKE_REMOTE": self.remote, "PYTHONIOENCODING": "utf-8"}
        env.pop("FAKE_FAIL", None)
        if fail:
            env["FAKE_FAIL"] = "1"
        return env

    def run_script(self, *args, fail=False, stdin='{"hook_event_name": "Stop"}'):
        p = subprocess.run([sys.executable, SCRIPT, *args], input=stdin, capture_output=True, text=True,
                           encoding="utf-8", env=self.env(fail))
        return p.returncode, p.stdout.strip()

    def write(self, name, data):
        with open(os.path.join(self.home, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def read(self, name):
        try:
            with open(os.path.join(self.home, name), encoding="utf-8") as f:
                return f.read() if name.endswith(".log") else json.load(f)
        except OSError:
            return None

    def session(self, sid, lines, project="-w-proj"):
        d = os.path.join(self.projects, project)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def plain(self, sid, minutes=5):
        self.session(sid, [{"type": "user", "timestamp": now_ts(minutes), "cwd": "/w/proj", "message": {"content": "일"}}])

    def errored(self, sid):
        att = {"type": "hook_non_blocking_error", "hookName": "Stop", "hookEvent": "Stop", "command": ENGINE_HOOK,
               "stderr": "Traceback", "durationMs": 40}
        self.session(sid, [{"type": "user", "timestamp": now_ts(), "cwd": "/w/proj", "message": {"content": "일"}},
                           {"type": "attachment", "timestamp": now_ts(), "attachment": att}])

    def configured(self, set_up_days_ago=0, **state):
        self.write("config.json", {"address": "me@server:harness-inbox"})
        t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=set_up_days_ago)
        self.write("state.json", {"set_up": t.strftime("%Y-%m-%dT%H:%M:%SZ"), **state})

    def received(self):
        folder = os.path.join(self.remote, "harness-inbox")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class TestHookDecides(FeedbackCase):

    def test_without_an_address_the_hook_does_nothing(self):
        self.errored("s1")
        self.assertEqual(self.run_script(), (0, ""))
        self.assertIsNone(self.read("state.json"))
        self.assertFalse(os.path.exists(self.log))

    def test_checks_at_most_once_every_six_hours(self):
        self.errored("s1")
        recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.configured(last_check=recent)
        self.assertEqual(self.run_script(), (0, ""))
        self.assertEqual(self.received(), [])
        self.assertIsNone(self.read("send.log"))

    def test_an_internal_error_sends_and_the_server_gets_meta_and_rows(self):
        self.errored("s1")
        self.plain("s2")
        self.configured()
        self.assertEqual(self.run_script(), (0, ""))              # 훅은 아무것도 출력하지 않는다
        files = self.received()
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.remote, "harness-inbox", files[0]), encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        self.assertEqual(lines[0]["_meta"]["reason"], "내부 오류 1건")
        self.assertEqual(sorted(r["session"] for r in lines[1:]), ["s1", "s2"])
        state = self.read("state.json")
        self.assertTrue(state["last_sent"])
        self.assertEqual(sorted(state["sent"]), ["s1", "s2"])
        self.assertIn("보냄 — 내부 오류 1건", self.read("send.log"))
        with open(self.log) as f:
            calls = f.read()
        self.assertIn("BatchMode=yes", calls)                     # 암호를 묻지 않는다 — 응답 뒤에서 멈추지 않게

    def test_sent_sessions_do_not_trigger_again(self):
        self.errored("s1")
        self.configured()
        self.run_script()
        state = self.read("state.json")
        state["last_check"] = "2000-01-01T00:00:00Z"
        self.write("state.json", state)
        self.run_script()
        self.assertEqual(len(self.received()), 1)
        self.assertIn("보낼 조건 아님(바뀐 세션 0개)", self.read("send.log"))

    def test_ten_changed_sessions_send(self):
        for i in range(10):
            self.plain(f"s{i}")
        self.configured()
        self.run_script()
        self.assertIn("보냄 — 바뀐 세션 10개", self.read("send.log"))

    def test_fewer_sessions_wait_until_fourteen_days(self):
        self.plain("s1")
        self.configured()
        self.run_script()
        self.assertEqual(self.received(), [])
        self.assertIn("보낼 조건 아님(바뀐 세션 1개)", self.read("send.log"))
        self.configured(set_up_days_ago=15)
        self.run_script()
        self.assertIn("보냄 — 마지막 전송 뒤 15일", self.read("send.log"))

    def test_failed_send_keeps_state_and_tries_again_later(self):
        self.errored("s1")
        self.configured()
        self.assertEqual(self.run_script(fail=True), (0, ""))
        self.assertNotIn("last_sent", self.read("state.json"))
        self.assertIn("실패 — 내부 오류 1건", self.read("send.log"))
        self.assertIn("Connection timed out", self.read("send.log"))

    def test_a_running_check_is_not_doubled(self):
        self.errored("s1")
        self.configured()
        open(os.path.join(self.home, "lock"), "w").close()
        self.run_script()
        self.assertEqual(self.received(), [])

    def test_real_hook_returns_at_once_and_sends_from_a_detached_process(self):
        """출력 통로를 물려받으면 Claude Code 가 그 프로세스가 끝날 때까지 기다린다 — 느린 ssh 로 확인한다."""
        import time

        slow = FAKE_SSH.replace('echo "ssh $*"', 'sleep 3; echo "ssh $*"')
        with open(os.path.join(self.bin, "ssh"), "w") as f:
            f.write(slow)
        self.errored("s1")
        self.configured()
        env = {k: v for k, v in self.env().items() if k != "HARNESS_FEEDBACK_FOREGROUND"}
        start = time.monotonic()
        p = subprocess.run([sys.executable, SCRIPT], input="{}", capture_output=True, text=True, env=env)
        took = time.monotonic() - start
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertLess(took, 2.5, "훅이 뒤쪽 전송을 기다렸다")
        for _ in range(100):
            if self.received():
                break
            time.sleep(0.2)
        self.assertEqual(len(self.received()), 1, self.read("send.log"))

    def test_broken_files_never_break_the_response(self):
        with open(os.path.join(self.home, "config.json"), "w") as f:
            f.write("{oops")
        self.assertEqual(self.run_script(stdin="not json"), (0, ""))
        self.write("config.json", {"address": "me@server"})
        with open(os.path.join(self.home, "state.json"), "w") as f:
            f.write("[]")
        self.assertEqual(self.run_script(), (0, ""))


class TestCommands(FeedbackCase):

    def test_setup_saves_the_address_and_tests_the_folder(self):
        rc, out = self.run_script("setup", "me@server:~/harness-inbox")
        self.assertEqual(rc, 0, out)
        self.assertIn("통과", out)
        self.assertEqual(self.read("config.json")["address"], "me@server:harness-inbox")
        self.assertTrue(os.path.isdir(os.path.join(self.remote, "harness-inbox")))
        rc, out = self.run_script("setup", "me@server", fail=True)
        self.assertEqual(rc, 1)
        self.assertIn("실패", out)
        self.assertEqual(self.run_script("setup", "me@server:'; rm -rf ~'")[0], 2)    # 따옴표·공백이 든 폴더는 받지 않는다

    def test_send_now_and_dry_run(self):
        self.plain("s1")
        self.assertEqual(self.run_script("send")[0], 2)                          # 주소 없음
        self.configured()
        rc, out = self.run_script("send", "--dry-run")
        self.assertEqual((rc, self.received()), (0, []))
        self.assertIn("보낼 예정", out)
        rc, out = self.run_script("send")
        self.assertEqual(rc, 0, out)
        self.assertIn("보냄 — 직접 실행 · 세션 1개", out)
        self.assertEqual(len(self.received()), 1)

    def test_status_reports_the_condition(self):
        self.errored("s1")
        self.configured()
        rc, out = self.run_script("status")
        self.assertEqual(rc, 0)
        self.assertIn("지금 보낼 조건: 내부 오류 1건", out)

    def test_receive_strips_meta_and_counts_a_resent_session_once(self):
        sys.path.insert(0, HERE)
        import harness_report as hr

        self.plain("s1")
        row = hr.collect(self.projects)["sessions"][0]                    # 노트북의 보고서 도구가 만드는 행 그대로
        inbox, out = os.path.join(self.root, "inbox"), os.path.join(self.root, "out")
        os.makedirs(inbox)
        for i, (last, prompts) in enumerate((("2026-11-01T10:00:00Z", 1), ("2026-11-03T10:00:00Z", 4))):
            with open(os.path.join(inbox, f"pc-{i}.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"_meta": {"pc": "pc", "sent_at": f"2026-11-0{i + 1}T00:00:00Z", "reason": "r",
                                              "engine_version": "1.18.0"}}) + "\n")
                f.write(json.dumps({**row, "last": last, "user_prompts": prompts}, ensure_ascii=False) + "\n")
        rc, printed = self.run_script("receive", "--inbox", inbox, "--out", out)
        self.assertEqual(rc, 0, printed)
        self.assertIn("pc: 마지막 전송 2026-11-02T00:00:00Z", printed)
        with open(os.path.join(out, "sessions.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        self.assertEqual([(r["session"], r["user_prompts"]) for r in rows], [("s1", 4)])


class TestAddress(unittest.TestCase):

    def test_address_forms(self):
        mod = load_module()
        self.assertEqual(mod.split_address("me@server"), ("me@server", "harness-inbox"))
        self.assertEqual(mod.split_address("server:inbox/laptop"), ("server", "inbox/laptop"))
        self.assertEqual(mod.split_address("me@server:~/harness-inbox/"), ("me@server", "harness-inbox"))
        for bad in ("", "me server", "me@server:'x'", "ssh://me@server", "me@server:a b"):
            self.assertIsNone(mod.split_address(bad), bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
