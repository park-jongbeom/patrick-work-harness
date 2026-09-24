#!/usr/bin/env python3
"""install.sh 의 디렉터리 보장 구간 시험 (HARNESS-INSTALL-DIRS-1, 2026-09-25).

## 왜 이게 있는가

`install.sh` 에는 **시험이 하나도 없었다** — 142건이 전부 훅 시험이다.
설치는 손으로 돌려 눈으로 확인해왔고, 그래서 설치 결함이 반복해서
출고됐다:

  · v1.4.0 — `comm` 이 로케일 불일치로 죽어 **훅 설치를 건너뛰면서
    성공 메시지를 출력**했다(2026-09-24)
  · v1.5.0 — `skill-usage-auto` 훅이 쓰는 `process_evolution` 디렉터리를
    설치가 만들지 않아, 새 프로젝트에서 **첫 집계부터 매번 실패**했다.
    훅은 항상 exit 0 이라 아무도 몰랐다(2026-09-25)

둘 다 「설치가 성공했다고 말하는데 실제로는 안 된」 형태다. 사람 눈으로는
안 보인다.

## 이 시험이 보는 것

디렉터리 보장 구간만 떼어 검증한다. 설치 전체(다운로드·rsync)는 네트워크와
외부 도구에 의존해 결정론적이지 않으므로, `--no-skills --no-hooks` 로
그 부분을 비활성화하고 **경로 해석과 생성**만 잰다.

계약(실측으로 확인한 것):
  · 답변 파일이 없으면 기본값 `plans/process_evolution`
  · `process_evolution_path` 가 있으면 **그 값을 쓴다**(프로젝트마다 다르다 —
    실측: `docs/process_evolution` 로 지정한 프로젝트가 있다)
  · 절대경로는 그대로, 상대경로는 대상 프로젝트 기준
  · `--dry-run` 은 **만들지 않는다**
  · 재실행해도 **기존 내용을 지우지 않는다**
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = _ROOT / "install.sh"


def _pinned_version() -> str:
    """시험이 받을 릴리스 태그 — `plugin.json` 을 따른다.

    하드코딩하면 다음 릴리스에서 썩는다. 읽지 못하면 조회로 되돌린다.
    """
    try:
        import json
        v = json.loads((_ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
        return v if v.startswith("v") else f"v{v}"
    except Exception:
        return "latest"


PINNED_VERSION = _pinned_version()


BASH = shutil.which("bash")


def _have_bash() -> bool:
    """`'bash'` 문자열이 아니라 **`which` 가 준 절대경로**를 써야 한다.

    실측(2026-09-25): `subprocess.run(["bash", ...])` 로 부르면 PATH 탐색
    결과가 Git Bash 가 아닌 다른 bash(`/bin/bash`)로 잡혀 `/d/...` 경로를
    못 찾고 rc=127 로 죽었다. 같은 명령을 `which` 경로로 부르면 정상이다.
    """
    return BASH is not None


def _sh(path: Path) -> str:
    """bash 에 넘길 경로 문자열 — Windows 경로를 MSYS 형식으로 바꾼다.

    두 번 틀렸던 자리다(실측 2026-09-25):
      · `D:\\Users\\...` 그대로 → 백슬래시가 이스케이프로 먹혀
        `D:Usersparjkkjihyun...` 이 된다
      · `D:/Users/...` (as_posix) → Git Bash 가 드라이브 문자를 경로로
        해석하지 못해 "No such file or directory"

    Git Bash(MSYS)는 `/d/Users/...` 형식을 쓴다. POSIX 환경에서는 경로가
    이미 그 형태이므로 변환이 일어나지 않는다.
    """
    p = path.as_posix()
    if len(p) > 2 and p[1] == ":":
        return f"/{p[0].lower()}{p[2:]}"
    return p


@unittest.skipUnless(INSTALL_SH.is_file(), "install.sh 가 없다")
@unittest.skipUnless(_have_bash(), "bash 가 없다 (Windows 순정 환경)")
class InstallDirsTestBase(unittest.TestCase):

    def setUp(self):
        self.target = Path(tempfile.mkdtemp(prefix="inst_"))
        (self.target / ".claude").mkdir()

    def tearDown(self):
        shutil.rmtree(self.target, ignore_errors=True)

    def write_answers(self, body: str) -> None:
        (self.target / ".claude" / "harness-answers.yml").write_text(
            body, encoding="utf-8")

    def run_install(self, *extra: str) -> str:
        """설치 실행 — 네트워크·rsync 의존 구간은 최대한 끈다.

        `--version` 을 명시해 **릴리스 조회 API 를 건너뛴다**. 이걸 안 주면
        매 시험이 `api.github.com` 을 때려 **레이트 리밋(403)** 에 걸리고,
        그러면 코드가 멀쩡해도 시험이 무더기로 실패한다(실측 2026-09-25 —
        변이 시험을 반복하다 복원 후에도 8건이 실패해 한참을 헤맸다).

        tarball 다운로드는 남으므로, 그마저 막히면 **실패가 아니라
        skip** 한다. 네트워크 사정으로 초록불이 빨개지면 아무도 안 본다.
        """
        proc = subprocess.run(
            [BASH, _sh(INSTALL_SH), "--target", _sh(self.target),
             "--version", PINNED_VERSION,
             "--no-skills", "--no-hooks", *extra],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if "curl:" in out or "403" in out:
            self.skipTest(f"네트워크로 tarball 을 못 받았다 (환경 문제)\n{out[:200]}")
        return out


class TestDefaultPath(InstallDirsTestBase):

    def test_creates_default_dir_when_no_answers(self):
        """답변 파일이 없으면 훅과 같은 기본값으로 만든다."""
        out = self.run_install()
        self.assertTrue(
            (self.target / "plans" / "process_evolution").is_dir(),
            f"기본 경로가 안 생겼다\n{out}")

    def test_reports_creation(self):
        out = self.run_install()
        self.assertIn("사용량 기록 경로", out, "생성 사실을 알리지 않는다")


class TestAnswersPath(InstallDirsTestBase):

    def test_respects_configured_path(self):
        """🔴 기본값을 박으면 안 된다 — 프로젝트마다 다르다.

        실측: `docs/process_evolution` 로 지정한 프로젝트가 있다.
        기본값을 강제하면 훅이 쓰는 곳과 **다른 자리**를 만들어,
        디렉터리는 생겼는데 집계는 계속 실패하는 상태가 된다.
        """
        self.write_answers('process_evolution_path: "docs/process_evolution"\n')
        out = self.run_install()
        self.assertTrue((self.target / "docs" / "process_evolution").is_dir(),
                        f"지정 경로가 안 생겼다\n{out}")
        self.assertFalse((self.target / "plans").exists(),
                         "지정이 있는데 기본 경로를 만들었다")

    def test_strips_quotes_and_comments(self):
        """YAML 값의 따옴표·주석을 벗겨야 경로가 맞는다."""
        self.write_answers(
            "process_evolution_path: 'docs/pe'   # 여기에 쌓인다\n")
        out = self.run_install()
        self.assertTrue((self.target / "docs" / "pe").is_dir(),
                        f"따옴표·주석 처리가 안 됐다\n{out}")

    def test_absolute_path_used_as_is(self):
        """절대경로는 대상 프로젝트 밑으로 붙이지 않는다."""
        outside = Path(tempfile.mkdtemp(prefix="inst_abs_"))
        target_dir = outside / "pe"
        try:
            self.write_answers(
                f'process_evolution_path: "{target_dir.as_posix()}"\n')
            out = self.run_install()
            self.assertTrue(target_dir.is_dir(), f"절대경로에 안 생겼다\n{out}")
            self.assertFalse((self.target / "plans").exists(),
                             "절대경로인데 프로젝트 밑에도 만들었다")
        finally:
            shutil.rmtree(outside, ignore_errors=True)


class TestProvenance(InstallDirsTestBase):
    """🔴 `_engine_version` 이 없는 답변 파일에서 설치가 죽던 자리.

    `set -euo pipefail` 아래에서 `grep` 은 매치 실패 시 rc=1 이다.
    `init` 스킬이 막 만든 답변 파일에는 이 필드가 없을 수 있고(템플릿
    본문에 없다), 그러면 설치가 **`[5/5]` 에서 끊긴 채 조용히 rc=1 로
    종료**한다 — provenance 갱신·디렉터리 생성·완료 메시지가 전부 날아간다.
    """

    def test_survives_missing_engine_version(self):
        self.write_answers('process_evolution_path: "docs/pe"\n')
        out = self.run_install()
        self.assertIn("설치 완료", out, f"필드 부재로 설치가 죽었다\n{out}")
        self.assertTrue((self.target / "docs" / "pe").is_dir(),
                        "설치가 끊겨 디렉터리 단계까지 못 왔다")

    def test_appends_engine_version_when_absent(self):
        """🔴 `sed` 는 **있는 줄만** 바꾼다 — 없으면 추가해야 한다.

        실측: 「provenance 갱신: 미기재 → 1.5.0」 을 출력하고도 파일은
        그대로였다. 말과 행동이 다른 형태라 로그로는 알 수 없다.
        """
        self.write_answers('process_evolution_path: "docs/pe"\n')
        self.run_install()
        body = (self.target / ".claude" / "harness-answers.yml").read_text(
            encoding="utf-8")
        self.assertIn("_engine_version:", body,
                      "갱신했다고 말해놓고 필드를 안 적었다")

    def test_preserves_other_answers(self):
        """버전만 손대고 사용자 응답은 그대로 둬야 한다."""
        self.write_answers(
            'stack: "python"\nprocess_evolution_path: "docs/pe"\n')
        self.run_install()
        body = (self.target / ".claude" / "harness-answers.yml").read_text(
            encoding="utf-8")
        self.assertIn('stack: "python"', body, "다른 응답이 사라졌다")


class TestSafety(InstallDirsTestBase):

    def test_dry_run_creates_nothing(self):
        """--dry-run 이 디스크를 건드리면 그 옵션의 의미가 없다."""
        out = self.run_install("--dry-run")
        self.assertFalse((self.target / "plans").exists(),
                         f"--dry-run 인데 만들었다\n{out}")

    def test_rerun_preserves_existing_contents(self):
        """재설치가 쌓인 기록을 지우면 안 된다."""
        self.run_install()
        kept = self.target / "plans" / "process_evolution" / "skill_usage_2026-09.md"
        kept.write_text("기존 산출물", encoding="utf-8")

        out = self.run_install()
        self.assertTrue(kept.is_file(), f"재설치가 기존 파일을 지웠다\n{out}")
        self.assertEqual(kept.read_text(encoding="utf-8"), "기존 산출물")

    def test_rerun_reports_confirmation_not_creation(self):
        """이미 있으면 「생성」이 아니라 「확인」이라고 말해야 한다.

        매번 「생성」이라고 하면 로그를 읽는 사람이 **덮어썼다고 오해**한다.
        """
        self.run_install()
        out = self.run_install()
        self.assertIn("확인", out, f"재실행인데 생성이라고 말한다\n{out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
