#!/usr/bin/env python3
"""전 시험 실행기 — **수집 누락을 실패로 만든다** (HARNESS-TEST-RUNNER-1, 2026-09-25).

## 왜 이게 있는가

`python -m unittest discover` 는 이 디렉터리에서 **`Ran 65 tests ... OK`** 를
출력한다. 그런데 파일에 적힌 `def test_*` 는 **141개**다. 76개가 조용히 빠진다.

원인은 시험이 두 양식으로 갈려 있기 때문이다:

  ① `unittest.TestCase` 형  — `discover` 가 수집한다
  ② **스크립트형**          — `TestCase` 없이 모듈 레벨 `def test_*()` 를 두고
                              `if __name__ == "__main__"` 에서 직접 돌린다.
                              `unittest` 는 **수집 자체를 못 한다**

②를 실행하려면 파일을 직접 돌려야 한다. 문제는 안 돌려도 **실패가 아니라
초록불**이라는 것이다 — 모수가 줄어도 알 방법이 없다.

## 이 러너의 계약

**정적으로 센 `def test_` 수 ≠ 실제 실행 수 이면 실패한다.**

통과/실패만 보는 게 아니라 **몇 개를 돌렸는지**를 검증한다. 새 시험 파일이
어느 양식으로 들어오든, 수집에서 빠지면 여기서 걸린다.

＊`skill_usage_aggregator.py` 처럼 `test_` 로 시작하지 않는 모듈은 대상이 아니다.
＊한 파일이 두 양식을 섞어 쓰면(TestCase + 모듈 레벨 함수) 중복 집계되지 않게
  양식을 **파일 단위로** 판정한다 — `class .*TestCase` 유무가 기준이다.

사용:
    python run_all_tests.py           # 전량 실행 + 개수 검증
    python run_all_tests.py --list    # 파일별 양식·시험 수만 출력
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
# 스크립트형 러너의 마지막 줄: "15/15 passed" 또는 "결과: 16 passed, 0 failed / 16 total"
_SCRIPT_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s+passed|(\d+)\s+passed,\s*(\d+)\s+failed\s*/\s*(\d+)\s+total")
_UNITTEST_RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


def count_static_tests(path: Path) -> int:
    """파일에 적힌 `def test_*` 수 — 클래스 메서드·모듈 함수 모두 센다.

    정규식이 아니라 AST 로 센다. 문자열·주석 안의 `def test_` 를 세지 않기
    위해서다(이 볼트에서 「세는 방법이 틀리는 것」을 여러 번 겪었다).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            n += 1
    return n


def is_unittest_style(path: Path) -> bool:
    """`unittest.TestCase` 를 상속한 클래스가 있으면 unittest 형."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                src = ast.unparse(base)
                if "TestCase" in src:
                    return True
    return False


def run_unittest_file(path: Path) -> tuple[int, bool, str]:
    """(실행 수, 통과 여부, 출력) — `Ran N tests` 를 파싱한다."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", path.stem],
        cwd=HOOKS_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = _UNITTEST_RAN_RE.search(out)
    ran = int(m.group(1)) if m else 0
    return ran, proc.returncode == 0, out


def run_script_file(path: Path) -> tuple[int, bool, str]:
    """(실행 수, 통과 여부, 출력) — 스크립트형은 파일을 직접 돌린다."""
    proc = subprocess.run(
        [sys.executable, path.name],
        cwd=HOOKS_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = 0
    for m in _SCRIPT_COUNT_RE.finditer(out):
        if m.group(2):      # "15/15 passed"
            ran = int(m.group(2))
        elif m.group(5):    # "결과: 16 passed, 0 failed / 16 total"
            ran = int(m.group(5))
    return ran, proc.returncode == 0, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="양식·시험 수만 출력")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = sorted(HOOKS_DIR.glob("test_*.py"))
    if not files:
        print("시험 파일이 없다 — 경로를 의심할 것", file=sys.stderr)
        return 1

    total_static = total_ran = 0
    failures: list[str] = []
    mismatches: list[str] = []

    print(f"{'파일':<44} {'양식':<10} {'정적':>5} {'실행':>5}  결과")
    print("─" * 82)

    for path in files:
        static = count_static_tests(path)
        unittest_style = is_unittest_style(path)
        style = "unittest" if unittest_style else "스크립트"

        if args.list:
            print(f"{path.name:<44} {style:<10} {static:>5} {'-':>5}")
            total_static += static
            continue

        runner = run_unittest_file if unittest_style else run_script_file
        ran, ok, out = runner(path)

        total_static += static
        total_ran += ran

        marks = []
        if not ok:
            marks.append("실패")
            failures.append(f"{path.name}\n{out}")
        if ran != static:
            marks.append(f"수집누락 {static - ran}")
            mismatches.append(f"{path.name}: 정적 {static} ≠ 실행 {ran}")
        verdict = " · ".join(marks) if marks else "OK"

        print(f"{path.name:<44} {style:<10} {static:>5} {ran:>5}  {verdict}")

    print("─" * 82)
    if args.list:
        print(f"{'합계':<44} {'':<10} {total_static:>5}")
        return 0

    print(f"{'합계':<44} {'':<10} {total_static:>5} {total_ran:>5}")

    if mismatches:
        print("\n🔴 수집 누락 — 시험이 있는데 안 돌았다 (초록불이어도 실패로 친다):")
        for m in mismatches:
            print(f"  · {m}")

    if failures:
        print(f"\n🔴 실패 {len(failures)}파일:")
        for f in failures:
            print(f"\n{f}")

    if not mismatches and not failures:
        print(f"\n✅ {total_ran}건 전건 통과 · 수집 누락 0")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
