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

    # 훅 파일은 복사의 삭제 단계로 사라지는데 배선이 남으면, Stop 은 응답마다 훅 오류를 남기고 PreToolUse 는 막는다.
    def prepare(self):
        hooks_dir = self.hooks_dir
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        self.retired = f"python3 {hooks_dir}/comprehension-ledger-stale-guard.py"
        self.other_copy = "python3 /w/plans/hooks/comprehension-ledger-stale-guard.py"
        self.mine = "python3 /w/my-hook.py"
        old_guard = f"python3 {hooks_dir}/claude-gate-guard.py"
        usage = f"python3 {hooks_dir}/skill-usage-auto.py"
        os.makedirs(os.path.dirname(self.settings), exist_ok=True)
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump({"theme": "dark", "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": self.retired}, {"type": "command", "command": self.mine}]},
                         {"hooks": [{"type": "command", "command": self.other_copy}]},
                         {"matcher": ".*", "hooks": [{"type": "command", "command": usage}]}],
                "PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": old_guard}]}],
            }}, f)

    def commands(self):
        with open(self.settings, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg, [h["command"] for groups in cfg["hooks"].values() for g in groups for h in g["hooks"]]

    def test_reinstall_removes_only_the_wiring_of_this_install(self):
        self.prepare()
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        cfg, commands = self.commands()
        self.assertEqual(cfg["theme"], "dark")
        self.assertNotIn(self.retired, commands)
        self.assertFalse([c for c in commands if "claude-gate-guard" in c or "skill-usage-auto" in c])
        self.assertIn(self.mine, commands, "같은 항목에 있던 사용자 훅이 함께 지워짐")
        self.assertIn(self.other_copy, commands, "다른 사본을 가리키는 배선은 이 설치의 몫이 아님")

    def test_reinstall_moves_the_commit_guard_to_the_wider_matcher(self):
        """v1.17.6 까지는 commit-msg-guard 를 Bash 에만 걸었다. 다시 설치하면 옛 항목을 지우고 PowerShell 까지 건다 —
        옛 항목이 남으면 Bash 커밋을 두 번 검사한다 (2026-11-06)."""
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        cfg, _ = self.commands()
        for entry in cfg["hooks"]["PreToolUse"]:
            if any("commit-msg-guard.py" in h["command"] for h in entry["hooks"]):
                entry["matcher"] = "Bash"            # 옛 설치의 배선
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        cfg, _ = self.commands()
        wired = [e["matcher"] for e in cfg["hooks"]["PreToolUse"] for h in e["hooks"] if "commit-msg-guard.py" in h["command"]]
        self.assertEqual(wired, ["Bash|PowerShell"])

    def test_removal_is_backed_up_and_reported(self):
        self.prepare()
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.assertIn("은퇴한 훅 배선 제거", out)
        names = os.listdir(os.path.dirname(self.settings))
        self.assertTrue([n for n in names if n.startswith("settings.json.bak-")], names)


class TestUnknownSourceFails(unittest.TestCase):

    def test_missing_source_directory_is_an_error(self):
        proc = subprocess.run(["bash", INSTALL, "--source", "/nonexistent-harness-src", "--dry-run"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("/nonexistent-harness-src", proc.stdout + proc.stderr)


FAKE_CURL = """#!/bin/sh
# 가짜 curl — URL 의 마지막 조각을 FAKE_SERVER 폴더에서 찾는다. 없으면 `curl -f` 처럼 22 로 끝난다.
out=""; head=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-w) [ "$1" = "-o" ] && out="$2"; shift 2;;
    --head|-I) head=1; shift;;
    -*) shift;;
    *) url="$1"; shift;;
  esac
done
echo "$url" >> "$FAKE_LOG"
f="$FAKE_SERVER/${url##*/}"
[ -f "$f" ] || exit 22
if [ -n "$head" ]; then printf 'HTTP/2 302\\r\\n\\r\\nHTTP/2 200\\r\\n'; exit 0; fi
if [ -n "$out" ]; then cp "$f" "$out"; else cat "$f"; fi
"""


@unittest.skipIf(os.name == "nt", "가짜 curl 이 sh 스크립트다")
class TestReleaseDownload(unittest.TestCase):
    """릴리스 내려받기 — 자산 압축 파일을 먼저 받고 `.sha256` 으로 검증한다. 전에는 어느 릴리스에도 체크섬이 없어
    검증이 한 번도 돌지 않았다(2026-11-10, 릴리스 30개 모두 자산 0개)."""

    TAG = "v1.19.0"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home, self.proj, self.server, self.bin = (os.path.join(self.root, n) for n in ("home", "proj", "server", "bin"))
        for d in (self.home, self.proj, self.server, self.bin):
            os.makedirs(d)
        with open(os.path.join(self.bin, "curl"), "w") as f:
            f.write(FAKE_CURL)
        os.chmod(os.path.join(self.bin, "curl"), 0o755)
        self.log = os.path.join(self.root, "fetched.log")

    def tarball(self, name):
        import tarfile
        path = os.path.join(self.server, name)
        prefix = "patrick-work-harness-" + self.TAG[1:]
        with tarfile.open(path, "w:gz") as tar:
            for item in ("plugin.json", ".claude-plugin", "skills", "hooks"):
                tar.add(os.path.join(ROOT, item), arcname=f"{prefix}/{item}",
                        filter=lambda t: None if "__pycache__" in t.name else t)
        return path

    def checksum(self, path, wrong=False):
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        with open(os.path.join(self.server, f"patrick-work-harness-{self.TAG}.tar.gz.sha256"), "w") as f:
            f.write(("0" * 64 if wrong else digest) + f"  patrick-work-harness-{self.TAG}.tar.gz\n")

    def install(self):
        env = {**os.environ, "HOME": self.home, "PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
               "FAKE_SERVER": self.server, "FAKE_LOG": self.log}
        proc = subprocess.run(["bash", INSTALL, "--version", self.TAG, "--target", self.proj], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env, stdin=subprocess.DEVNULL, timeout=120)
        with open(self.log, encoding="utf-8") as f:
            fetched = f.read()
        return proc.returncode, proc.stdout + proc.stderr, fetched

    def installed(self):
        return os.path.isfile(os.path.join(self.home, ".claude", "hooks", "patrick-work-harness", "harness_report.py"))

    def test_release_asset_is_checked_and_installed(self):
        self.checksum(self.tarball(f"patrick-work-harness-{self.TAG}.tar.gz"))
        rc, out, fetched = self.install()
        self.assertEqual(rc, 0, out)
        self.assertIn("SHA256 검증 완료", out)
        self.assertIn(f"releases/download/{self.TAG}/patrick-work-harness-{self.TAG}.tar.gz", fetched)
        self.assertNotIn("archive/refs/tags", fetched)
        self.assertTrue(self.installed())

    def test_mismatch_stops_before_anything_is_installed(self):
        self.checksum(self.tarball(f"patrick-work-harness-{self.TAG}.tar.gz"), wrong=True)
        rc, out, _ = self.install()
        self.assertEqual(rc, 1)
        self.assertIn("SHA256 체크섬 불일치", out)
        self.assertFalse(self.installed())

    def test_old_release_without_assets_falls_back_and_says_the_check_was_skipped(self):
        self.tarball(f"{self.TAG}.tar.gz")                    # GitHub 소스 압축본 이름(archive/refs/tags/<태그>.tar.gz)
        rc, out, fetched = self.install()
        self.assertEqual(rc, 0, out)
        self.assertIn("자산 압축 파일이 없다", out)
        self.assertIn("체크섬 파일 없음", out)
        self.assertIn(f"archive/refs/tags/{self.TAG}.tar.gz", fetched)
        self.assertTrue(self.installed())


@unittest.skipUnless(shutil.which("git") and shutil.which("gzip") and shutil.which("sha256sum"), "git·gzip·sha256sum 이 없다")
class TestReleaseAssetsScript(unittest.TestCase):
    """release-assets.sh — 같은 태그는 다시 만들어도 같은 바이트여야 올린 체크섬을 누구나 대조할 수 있다."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        git = ["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        with open(os.path.join(self.repo, "plugin.json"), "w") as f:
            f.write('{"version": "0.0.1"}\n')
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-qm", "init"], check=True)
        subprocess.run(git + ["tag", "v0.0.1"], check=True)

    def build(self, tag="v0.0.1"):
        proc = subprocess.run(["bash", os.path.join(ROOT, "release-assets.sh"), tag], cwd=self.repo, capture_output=True,
                              text=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=60)
        out = proc.stdout.strip().splitlines()
        return proc.returncode, (out[-1] if out else ""), proc.stdout + proc.stderr

    def test_same_tag_builds_the_same_bytes_and_a_checksum_that_verifies(self):
        hashes = []
        for _ in range(2):
            rc, folder, out = self.build()
            self.addCleanup(shutil.rmtree, folder, True)
            self.assertEqual(rc, 0, out)
            # 체크섬 이름은 `<압축 파일>.sha256` 뿐이다 — `…-v0.0.1.sha256` 이 생기면 옛 install.sh 가 소스 압축본과 비교해 멈춘다
            self.assertEqual(sorted(os.listdir(folder)), ["patrick-work-harness-v0.0.1.tar.gz",
                                                          "patrick-work-harness-v0.0.1.tar.gz.sha256"])
            with open(os.path.join(folder, "patrick-work-harness-v0.0.1.tar.gz.sha256"), encoding="utf-8") as f:
                line = f.read()
            self.assertTrue(line.endswith("  patrick-work-harness-v0.0.1.tar.gz\n"), line)
            with open(os.path.join(folder, "patrick-work-harness-v0.0.1.tar.gz"), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), line.split()[0])
            hashes.append(line.split()[0])
        self.assertEqual(hashes[0], hashes[1])

    def test_bad_tag_is_refused(self):
        self.assertEqual(self.build("1.0")[0], 2)
        self.assertEqual(self.build("v9.9.9")[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
