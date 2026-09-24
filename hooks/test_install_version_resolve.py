#!/usr/bin/env python3
"""install.sh 의 버전 조회 실패 안내 시험 (HARNESS-INSTALL-RATELIMIT-1, 2026-09-25).

## 왜 이게 있는가

`install.sh` 는 `--version` 을 안 주면 `api.github.com` 에 최신 태그를 묻는다.
이 API 는 **비인증 호출 시 IP 당 시간당 60회** 제한이라 공용 IP·CI·잦은
재설치 환경에서 403 이 난다.

문제는 걸렸을 때의 화면이었다(실측 2026-09-25):

    [1/5] 최신 릴리즈 버전 조회 중...
    curl: (22) The requested URL returned error: 403

이게 전부다. **친절한 `[ERROR]` 안내가 코드에 이미 적혀 있었는데 한 번도
출력되지 않았다** — `set -euo pipefail` 아래에서 `curl -f` 를 대입문에 직접
쓰면 403 에서 rc=22 로 끝나고, 대입 실패가 곧 스크립트 종료라 그 아래
안내 줄에 **도달하지 못한다**. 적어두고 실행되지 않던 자리다.

## 재는 방법

`curl` 을 **PATH 에 가짜로 앞세워** HTTP 코드를 흉내낸다. 실제 API 를
때리면 ⓐ 레이트 리밋에 걸려 시험이 비결정적이고 ⓑ 200 이 아닌 경로를
의도적으로 만들 수 없다(실측: 404 분기를 재려다 403 이 먼저 걸렸다).

`install.sh` 는 `curl` 을 이름으로 부르므로(절대경로 호출 0곳) 이 방식이
성립한다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = _ROOT / "install.sh"
BASH = shutil.which("bash")


def _sh(path: Path) -> str:
    """Windows 경로를 MSYS 형식으로 (test_install_dirs 와 동일 규칙)."""
    p = path.as_posix()
    if len(p) > 2 and p[1] == ":":
        return f"/{p[0].lower()}{p[2:]}"
    return p


@unittest.skipUnless(INSTALL_SH.is_file(), "install.sh 가 없다")
@unittest.skipUnless(BASH is not None, "bash 가 없다")
class VersionResolveTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vres_"))
        self.target = self.tmp / "proj"
        self.target.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub_curl(self, http_code: str, body: str = "") -> None:
        """가짜 `curl` 을 PATH 앞에 둔다.

        install.sh 는 `-w '%{http_code}'` 로 코드를, `-o <파일>` 로 본문을
        받는다. 그 계약만 흉내내면 된다.
        """
        script = self.bin / "curl"
        script.write_text(
            "#!/bin/sh\n"
            "# 시험용 가짜 curl — -o 다음 인자를 본문 파일로 본다\n"
            "out=''\n"
            "while [ $# -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    -o) out=\"$2\"; shift 2 ;;\n"
            "    *)  shift ;;\n"
            "  esac\n"
            "done\n"
            f"[ -n \"$out\" ] && printf '%s' '{body}' > \"$out\"\n"
            f"printf '{http_code}'\n",
            encoding="utf-8", newline="\n")
        script.chmod(0o755)

    def run_install(self, *extra: str) -> tuple[str, int]:
        env = dict(os.environ)
        env["PATH"] = f"{_sh(self.bin)}:{env.get('PATH','')}"
        proc = subprocess.run(
            [BASH, _sh(INSTALL_SH), "--target", _sh(self.target),
             "--no-skills", "--no-hooks", *extra],
            capture_output=True, text=True, env=env,
            encoding="utf-8", errors="replace", timeout=300,
        )
        return (proc.stdout or "") + (proc.stderr or ""), proc.returncode


class TestRateLimitGuidance(VersionResolveTestBase):
    """🔴 403 에서 사용자가 다음에 뭘 할지 알 수 있어야 한다."""

    def test_403_reaches_the_error_message(self):
        """가장 중요한 계약 — 안내가 **출력된다**.

        종전에는 `set -e` 가 먼저 죽여 이 줄에 도달하지 못했다.
        """
        self.stub_curl("403")
        out, rc = self.run_install()
        self.assertIn("[ERROR]", out, f"안내에 도달하지 못했다\n{out}")
        self.assertEqual(rc, 1, "실패인데 rc 가 1 이 아니다")

    def test_403_explains_cause_and_limit(self):
        self.stub_curl("403")
        out, _ = self.run_install()
        self.assertIn("403", out, "HTTP 코드를 알려주지 않는다")
        self.assertIn("60", out, "한도(시간당 60회)를 알려주지 않는다")

    def test_403_offers_the_workaround(self):
        """우회책을 모르면 거기서 멈춘다 — `--version` 을 반드시 안내한다."""
        self.stub_curl("403")
        out, _ = self.run_install()
        self.assertIn("--version", out, "우회 명령을 안내하지 않는다")

    def test_429_uses_same_guidance(self):
        """429 도 한도 초과다 — 같은 안내를 준다."""
        self.stub_curl("429")
        out, _ = self.run_install()
        self.assertIn("--version", out)


class TestOtherFailures(VersionResolveTestBase):

    def test_network_failure_is_distinguished(self):
        """000(연결 실패)을 한도 초과로 잘못 안내하면 엉뚱한 곳을 보게 된다."""
        self.stub_curl("000")
        out, _ = self.run_install()
        self.assertIn("--version", out, "우회책은 여기서도 유효하다")
        self.assertNotIn("60", out, "연결 실패인데 한도 이야기를 한다")

    def test_unexpected_code_still_guides(self):
        """404 등 예상 밖 코드에서도 멈추지 말고 안내한다."""
        self.stub_curl("404")
        out, rc = self.run_install()
        self.assertIn("404", out, "실제 코드를 알려주지 않는다")
        self.assertIn("--version", out)
        self.assertEqual(rc, 1)


class TestSuccessPathIntact(VersionResolveTestBase):
    """안내를 넣느라 **정상 경로를 깨뜨리지 않았는지**가 핵심이다."""

    def test_200_resolves_tag_and_proceeds(self):
        self.stub_curl("200", '{"tag_name": "v9.9.9"}')
        out, _ = self.run_install()
        self.assertIn("v9.9.9", out, f"태그를 파싱하지 못했다\n{out}")
        self.assertNotIn("[ERROR]", out.split("v9.9.9")[0],
                         "성공인데 에러 안내가 먼저 나왔다")

    def test_explicit_version_skips_the_query(self):
        """`--version` 을 주면 조회 자체를 안 한다 — 403 이어도 진행된다."""
        self.stub_curl("403")
        out, _ = self.run_install("--version", "v1.2.3")
        self.assertIn("v1.2.3", out)
        self.assertNotIn("[ERROR]", out, f"조회를 건너뛰지 않았다\n{out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
