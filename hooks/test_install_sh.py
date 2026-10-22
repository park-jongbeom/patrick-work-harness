"""install.sh 끝에서 끝까지 — 로컬 원본(--source)으로 임시 HOME·프로젝트에 실제로 설치해 본다 (A1, 2026-10-22).

왜: 스킬은 `${CLAUDE_PLUGIN_ROOT}/hooks/<스크립트>` 를 부른다. 플러그인 스킬에서는 이 변수가 실제 경로로 바뀌지만,
install.sh 가 프로젝트에 복사한 스킬에서는 **빈 문자열**이다(Claude Code 2.1.307 실측: `ROOT=[]`). 그러면
Gate E 검토 카드·세션 원장, Gate D 사실 블록 명령이 `python3 "/hooks/…"` 로 실패한다. install.sh 는 스킬을 복사할 때
그 경로를 훅 설치 폴더로 바꿔 써야 한다.

install.sh 는 rsync 가 있으면 rsync 로, 없으면 python3 으로 복사한다. rsync 경로의 시험은 rsync 가 없으면 이유를 밝히고
건너뛰고, python3 경로는 `TestInstallWithoutRsync` 가 어디서나 본다.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "install.sh")
HAS_RSYNC = shutil.which("rsync") is not None


def tree_digest(path):
    h = hashlib.sha256()
    for base, _, files in sorted(os.walk(path)):
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(base, name)
            h.update(p[len(path):].encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


@unittest.skipUnless(HAS_RSYNC, "rsync 가 없다 — rsync 경로의 설치는 이 환경에서 확인하지 못한다(python3 경로는 따로 돈다)")
class TestInstallFromLocalSource(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.proj = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(shutil.rmtree, self.proj, True)
        self.hooks_dir = os.path.join(self.home, ".claude", "hooks", "patrick-work-harness")

    def install(self, *extra):
        env = {**os.environ, "HOME": self.home}
        proc = subprocess.run(["bash", INSTALL, "--source", ROOT, "--target", self.proj, *extra],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                              stdin=subprocess.DEVNULL, timeout=120)
        return proc.returncode, proc.stdout + proc.stderr

    def skill_texts(self):
        out = {}
        for base, _, files in os.walk(os.path.join(self.proj, ".claude", "skills")):
            for name in files:
                if name.endswith(".md"):
                    with open(os.path.join(base, name), encoding="utf-8") as f:
                        out[os.path.join(base, name)] = f.read()
        return out

    def test_installed_skills_point_at_the_installed_hooks(self):
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        texts = self.skill_texts()
        self.assertTrue(texts, "스킬이 설치되지 않음")
        # 경로로 쓰인 것(`${CLAUDE_PLUGIN_ROOT}/…`)만 본다. 「설정에 이 변수를 쓰지 말라」처럼 이름으로 부르는 문장은 그대로 남아야 맞다.
        left = [p for p, t in texts.items() if "${CLAUDE_PLUGIN_ROOT}/" in t]
        self.assertEqual(left, [], "설치된 스킬에 빈 문자열이 될 경로가 남음")
        referenced = set()
        for t in texts.values():
            referenced.update(re.findall(re.escape(self.hooks_dir) + r"/([\w.-]+)", t))
        for name in ("lane_card.py", "session_ledger.py", "report_facts.py", "plugin.json"):
            self.assertIn(name, referenced, f"스킬이 {name} 를 설치 폴더 경로로 부르지 않음")
        missing = [n for n in referenced if not os.path.isfile(os.path.join(self.hooks_dir, n))]
        self.assertEqual(missing, [], "스킬이 부르는 파일이 설치 폴더에 없음")

    def test_installed_plugin_manifest_carries_the_version(self):
        self.install()
        with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as f:
            want = json.load(f)["version"]
        with open(os.path.join(self.hooks_dir, "plugin.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], want)

    def test_source_tree_is_not_modified(self):
        before = tree_digest(os.path.join(ROOT, "skills"))
        self.install()
        self.assertEqual(tree_digest(os.path.join(ROOT, "skills")), before, "설치가 원본 스킬을 바꿨다")

    def test_dry_run_writes_nothing(self):
        rc, out = self.install("--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".claude")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))
        self.assertIn("경로", out)

    def test_no_hooks_warns_that_skill_commands_need_the_scripts(self):
        rc, out = self.install("--no-hooks")
        self.assertEqual(rc, 0, out)
        self.assertIn("--no-hooks", out)
        self.assertFalse(os.path.isdir(self.hooks_dir))

    def test_hooks_are_still_registered(self):
        self.install()
        with open(os.path.join(self.home, ".claude", "settings.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        commands = [h["command"] for groups in cfg["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertTrue(any("lane-scope-guard.py" in c for c in commands))
        for c in commands:
            script = c.split()[-1].strip('"')
            self.assertTrue(os.path.isfile(script), f"등록된 훅 파일이 없음: {script}")


class TestInstallWithoutRsync(unittest.TestCase):
    """rsync 가 없는 곳(Git Bash, 최소 컨테이너)에서도 설치한다 — python3 으로 같은 규칙(제외·삭제)을 따른다.

    `HARNESS_INSTALL_NO_RSYNC=1` 로 rsync 가 있어도 대체 경로를 강제한다. 이 시험은 어디서나 돈다(건너뛰지 않는다).
    """

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.proj = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(shutil.rmtree, self.proj, True)
        self.hooks_dir = os.path.join(self.home, ".claude", "hooks", "patrick-work-harness")

    def install(self):
        env = {**os.environ, "HOME": self.home, "HARNESS_INSTALL_NO_RSYNC": "1"}
        proc = subprocess.run(["bash", INSTALL, "--source", ROOT, "--target", self.proj], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, stdin=subprocess.DEVNULL, timeout=120)
        return proc.returncode, proc.stdout + proc.stderr

    def test_fallback_copy_installs_skills_and_hooks(self):
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.assertIn("rsync 없이", out)
        gate_e = open(os.path.join(self.proj, ".claude", "skills", "gate-e", "SKILL.md"), encoding="utf-8").read()
        self.assertIn(self.hooks_dir + "/lane_card.py", gate_e)
        names = set(os.listdir(self.hooks_dir))
        self.assertIn("lane_card.py", names)
        self.assertIn("plugin.json", names)
        self.assertFalse([n for n in names if n.startswith("test_")], "시험 파일은 설치하지 않는다")
        self.assertNotIn("__pycache__", names)
        with open(os.path.join(self.home, ".claude", "settings.json"), encoding="utf-8") as f:
            self.assertIn("lane-scope-guard.py", f.read())

    def test_fallback_reinstall_removes_stale_hooks_but_keeps_the_owner_mark(self):
        self.install()
        stale = os.path.join(self.hooks_dir, "old-retired-guard.py")
        with open(stale, "w") as f:
            f.write("# 옛 훅\n")
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(stale), "배포본에 없는 옛 훅은 지운다(rsync --delete 와 같은 규칙)")
        self.assertTrue(os.path.exists(os.path.join(self.hooks_dir, ".harness-owned")))
        self.assertTrue(os.path.exists(os.path.join(self.hooks_dir, "plugin.json")))


class TestUnknownSourceFails(unittest.TestCase):

    def test_missing_source_directory_is_an_error(self):
        proc = subprocess.run(["bash", INSTALL, "--source", "/nonexistent-harness-src", "--dry-run"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("/nonexistent-harness-src", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
