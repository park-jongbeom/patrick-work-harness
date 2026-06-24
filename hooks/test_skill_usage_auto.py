#!/usr/bin/env python3
"""skill-usage-auto.py throttle 게이팅 단위 테스트.

HARNESS-SKILL-ANALYTICS-2(2026-06-10). should_run()의 mtime 가드만 검증한다
(실제 aggregator subprocess 실행은 테스트 대상 외). 표준 라이브러리만 사용.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 하이픈 파일명은 직접 import 불가 → importlib로 로드.
_SPEC = importlib.util.spec_from_file_location(
    "skill_usage_auto",
    str(Path(__file__).resolve().parent / "skill-usage-auto.py"),
)
auto = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(auto)


def test_missing_output_runs():
    """(1) 출력 md가 없으면 실행해야 한다(True)."""
    now = datetime.now()
    missing = Path(tempfile.mkdtemp()) / "skill_usage_2026-06.md"
    assert auto.should_run(missing, now) is True


def test_fresh_output_skips():
    """(2) mtime이 23h 전(24h 미만)이면 스킵(False)."""
    now = datetime.now()
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        path = Path(f.name)
    os.utime(path, (now.timestamp() - 23 * 3600,) * 2)
    assert auto.should_run(path, now) is False
    path.unlink()


def test_stale_output_runs():
    """(3) mtime이 25h 전(24h 초과)이면 실행(True)."""
    now = datetime.now()
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        path = Path(f.name)
    os.utime(path, (now.timestamp() - 25 * 3600,) * 2)
    assert auto.should_run(path, now) is True
    path.unlink()


def test_output_path_uses_current_month():
    """(4) 출력 경로는 현재 월(YYYY-MM) 파일명을 쓴다."""
    now = datetime(2026, 6, 10)
    assert auto.output_path_for(now).name == "skill_usage_2026-06.md"


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
