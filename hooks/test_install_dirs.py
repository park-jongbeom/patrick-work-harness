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

디렉터리 보장 구간은 집계 훅을 빼면서 함께 뺐다(2026-11-05). 지금은 provenance 갱신과, 설치가 쓰는 곳 없는 폴더를
만들지 않는다는 것을 본다. 설치 전체(다운로드·rsync)는 `--no-skills --no-hooks` 로 끈다.
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

    두 번 틀렸던 자리다(실측 2026-09-25). 아래 예시는 드라이브 문자를
    `<D>` 로 적는다 — 실제 표기로 쓰면 배포 전 사설 경로 검사
    (`sync-from-source.sh` 의 `LEAK_PATTERN`)에 걸려 동기화가 막힌다:
      · `<D>:\\Users\\<user>\\...` 그대로 → 백슬래시가 이스케이프로 먹혀
        구분자가 사라진 한 덩어리가 된다
      · `<D>:/Users/<user>/...` (as_posix) → Git Bash 가 드라이브 문자를
        경로로 해석하지 못해 "No such file or directory"

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
        """설치 실행 — 네트워크·rsync 의존 구간을 끈다.

        `--source` 로 이 저장소 체크아웃에서 설치한다(2026-10-22). 예전에는 `--version` 으로 릴리스
        tarball 을 내려받았는데, `--no-skills --no-hooks` 라 받은 것을 쓰지도 않으면서 네트워크가
        없으면 11건이 통째로 건너뛰어졌다(깨끗한 컨테이너에는 curl 이 없다). 버전은 원본의
        `plugin.json` 에서 읽으므로 `PINNED_VERSION` 과 같다.

        그래도 네트워크 오류 문구가 보이면 **실패가 아니라 skip** 한다.
        """
        proc = subprocess.run(
            [BASH, _sh(INSTALL_SH), "--target", _sh(self.target),
             "--source", _sh(_ROOT),
             "--no-skills", "--no-hooks", *extra],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if "curl:" in out or "403" in out:
            self.skipTest(f"네트워크로 tarball 을 못 받았다 (환경 문제)\n{out[:200]}")
        return out


class TestProvenance(InstallDirsTestBase):
    """🔴 `_engine_version` 이 없는 답변 파일에서 설치가 죽던 자리.

    `set -euo pipefail` 아래에서 `grep` 은 매치 실패 시 rc=1 이다.
    `init` 스킬이 막 만든 답변 파일에는 이 필드가 없을 수 있고(템플릿
    본문에 없다), 그러면 설치가 **`[5/5]` 에서 끊긴 채 조용히 rc=1 로
    종료**한다 — provenance 갱신·완료 메시지가 전부 날아간다.
    """

    def test_survives_missing_engine_version(self):
        self.write_answers('process_evolution_path: "docs/pe"\n')
        out = self.run_install()
        self.assertIn("설치 완료", out, f"필드 부재로 설치가 죽었다\n{out}")
        answers = (self.target / ".claude" / "harness-answers.yml").read_text(encoding="utf-8")
        self.assertIn("_engine_version:", answers, "설치가 끊겨 provenance 단계까지 못 왔다")

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


class TestNoUsageDirectory(InstallDirsTestBase):
    """집계 훅을 뺐으므로 쓰는 곳이 없다 — 설치가 프로젝트에 폴더를 만들 이유가 없다(2026-11-05)."""

    def test_install_makes_no_usage_directory(self):
        self.run_install()
        self.assertFalse((self.target / "plans").exists(), "쓰는 곳 없는 폴더를 프로젝트에 만들었다")

    def test_configured_path_is_not_created_either(self):
        self.write_answers('process_evolution_path: "docs/pe"\n')
        self.run_install()
        self.assertFalse((self.target / "docs" / "pe").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
