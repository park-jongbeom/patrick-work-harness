"""session_ledger.py 시험 — Gate E 가 모든 세션의 결과를 한 줄로 남긴다.

대화 기록에는 무엇이 바뀌었는지, 사람이 무엇을 바로잡았는지가 남지 않는다. 그 결과를 세션 문서·git 에서 읽어
`<archive_path>/session-ledger.jsonl` 에 덧붙인다. 임시 git 저장소로 실제 실행한다.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "session_ledger.py")
sys.path.insert(0, HERE)
import session_ledger as sl  # noqa: E402

DOC = """# 현재 세션 상태

> **세션 ID**: T-LEDGER-1
> **현재 상태**: E (진행 중)

## 대시보드

| 항목 | 값 |
|------|-----|
| 현재 Gate | E |
| Gate 진행 | A✅ B✅ C✅ D✅ E⏳ |
| R/V/D 분해 | R=0 / V=1 / D=1 |

## Gate C 구현

> 일괄 실행: C~E (승인 문구: 「C~E 일괄」)

## Gate D 검증

- self-debug 1회 · FIX-B 2건 · DEP 0건
"""


def sh(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


class LedgerCase(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        sh(self.repo, "init", "-q")
        sh(self.repo, "config", "user.email", "t@t")
        sh(self.repo, "config", "user.name", "t")
        self.write("src/a.py", "x = 1\n")
        self.write(".claude/harness-answers.yml", '_engine_version: "1.11.0"\narchive_path: "docs/archive"\n')
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", "base")
        self.base = sh(self.repo, "rev-parse", "--short", "HEAD")
        self.write("CURRENT_SESSION.md", DOC)
        self.write("src/a.py", "x = 2\ny = 3\n")
        self.write("tests/test_a.py", "def test_a():\n    assert True\n")

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, SCRIPT, "append", "--repo", self.repo, *args], capture_output=True,
                              text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return proc.returncode, proc.stdout + proc.stderr

    def ledger(self):
        with open(os.path.join(self.repo, "docs", "archive", "session-ledger.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class TestAppend(LedgerCase):

    def test_record_reads_the_session_document_and_the_diff(self):
        rc, out = self.run_cli("--base", self.base, "--model", "claude-sonnet-5-5",
                               "--finding", "보고서 숫자 3건을 1건으로 정정", "--finding", "경로 인용 오류")
        self.assertEqual(rc, 0, out)
        (r,) = self.ledger()
        self.assertEqual((r["kind"], r["session_id"], r["lane"]), ("session", "T-LEDGER-1", "검토"))
        self.assertEqual(r["gate_progress"], "A✅ B✅ C✅ D✅ E⏳")
        self.assertEqual(r["rvd"], "R=0 / V=1 / D=1")
        self.assertEqual(r["batch"], "C~E")
        self.assertEqual((r["self_debug"], r["fix_b"], r["dep"]), (1, 2, 0))
        self.assertEqual(r["model"], {"value": "claude-sonnet-5-5", "source": "모델 기록"})
        self.assertEqual(r["human_findings"]["count"], 2)
        self.assertEqual(r["human_findings"]["source"], "모델 기록")
        self.assertEqual(r["base"], self.base)
        self.assertEqual(r["changed"]["files"], 2)              # src/a.py, tests/test_a.py — 세션 문서는 뺀다
        self.assertEqual(r["changed"]["by_category"], {"code": 1, "tests": 1})
        self.assertEqual(r["changed"]["lines"], 5)              # a.py 1삭제+2추가, 새 시험 2줄
        self.assertEqual(r["engine_version"]["value"], sl.engine_version(self.repo)["value"])

    def test_no_findings_is_recorded_as_zero_not_missing(self):
        self.run_cli("--base", self.base)
        self.assertEqual(self.ledger()[0]["human_findings"], {"count": 0, "items": [], "source": "모델 기록"})

    def test_without_base_the_diff_is_marked_unknown(self):
        self.run_cli()
        r = self.ledger()[0]
        self.assertIsNone(r["changed"])
        self.assertIn("기준 커밋 없음", " ".join(r["flags"]))

    def test_missing_markers_are_flagged(self):
        self.write("CURRENT_SESSION.md", DOC.split("## Gate D 검증")[0])
        self.run_cli("--base", self.base)
        r = self.ledger()[0]
        self.assertIsNone(r["self_debug"])
        self.assertIn("Gate D 표지 없음", " ".join(r["flags"]))

    def test_append_only(self):
        self.run_cli("--base", self.base)
        self.run_cli("--base", self.base)
        self.assertEqual(len(self.ledger()), 2)

    def test_missing_archive_path_fails_loudly(self):
        self.write(".claude/harness-answers.yml", "project: t\n")
        rc, out = self.run_cli("--base", self.base)
        self.assertNotEqual(rc, 0)
        self.assertIn("archive_path", out)

    def test_autonomous_session_links_its_card_verdict(self):
        lane_ledger = os.path.join(self.repo, "docs", "archive", "lane-ledger.jsonl")
        os.makedirs(os.path.dirname(lane_ledger), exist_ok=True)
        with open(lane_ledger, "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "card", "card_id": "T-LEDGER-1@x", "session_id": "T-LEDGER-1"}) + "\n")
            f.write(json.dumps({"kind": "verdict", "card_id": "T-LEDGER-1@x", "session_id": "T-LEDGER-1", "verdict": "경미"}) + "\n")
        self.run_cli("--base", self.base)
        self.assertEqual(self.ledger()[0]["lane_card"], {"card_id": "T-LEDGER-1@x", "verdict": "경미"})


class TestEngineVersion(unittest.TestCase):

    def test_falls_back_to_the_answers_file_when_no_manifest_is_shipped(self):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        os.makedirs(os.path.join(repo, ".claude"))
        with open(os.path.join(repo, ".claude", "harness-answers.yml"), "w", encoding="utf-8") as f:
            f.write('_engine_version: "1.8.0"\n')
        v = sl.engine_version(repo, manifest_dirs=[repo])
        self.assertEqual(v, {"value": "1.8.0", "source": "harness-answers.yml"})

    def test_reads_the_manifest_install_sh_puts_next_to_the_scripts(self):
        """install.sh 는 plugin.json 을 훅 폴더 안에 둔다. 그 위 폴더만 보면 설치된 판을 못 읽고 프로젝트 설정의 옛 값을
        낸다(2026-11-11 — 대시보드에 버전을 넣으며 확인: 전송 스크립트는 훅 폴더도 보는데 이 함수만 보지 않았다)."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        hooks = os.path.join(base, "hooks", "patrick-work-harness")
        os.makedirs(hooks)
        for name in ("session_ledger.py", "lane_card.py"):
            shutil.copy(os.path.join(HERE, name), hooks)
        with open(os.path.join(hooks, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump({"version": "9.9.9"}, f)
        repo = os.path.join(base, "project")
        os.makedirs(os.path.join(repo, ".claude"))
        with open(os.path.join(repo, ".claude", "harness-answers.yml"), "w", encoding="utf-8") as f:
            f.write('_engine_version: "1.8.0"\n')
        code = "import json, sys; sys.path.insert(0, sys.argv[1]); import session_ledger as m; print(json.dumps(m.engine_version(sys.argv[2])))"
        p = subprocess.run([sys.executable, "-c", code, hooks, repo], capture_output=True, text=True, encoding="utf-8",
                           stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"value": "9.9.9", "source": "plugin.json"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
