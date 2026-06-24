#!/usr/bin/env python3
"""스킬 사용 통계(skill_usage_aggregator)를 Stop 훅에서 자동 갱신한다.

HARNESS-SKILL-ANALYTICS-2 (2026-06-10) — 자동화(갭 c).
HSA-1 aggregator는 수동 월별 실행이었다. 본 throttle 래퍼는 Stop 훅 배열에
등록되어 매 세션 종료 시 호출되되, 출력 md의 mtime을 보고 **하루 1회만**
실제 집계를 돌린다.

근거: aggregator 1회 = 약 4.4초·JSONL 1150개·628MB 스캔(실측). 매 Stop마다
직접 등록하면 매 세션 종료에 4.4초가 부과되므로, mtime ≤1일1회 가드로 제한한다.
실패는 무해(session-dashboard-sync.py 패턴 계승) — stderr만, 항상 exit 0.

표준 라이브러리만 사용.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# R-4-2-a: CLAUDE_PROJECT_DIR 기반 이식성 폴백 (env 부재 시 절대경로 유지)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
PROCESS_EVOLUTION_DIR = (
    Path(_proj).parent / "plans" / "process_evolution"
    if _proj
    else Path(os.environ.get("HARNESS_PLANS_DIR", "."), "process_evolution")
)
AGGREGATOR = PROCESS_EVOLUTION_DIR / "skill_usage_aggregator.py"
MAX_AGE_HOURS = 24


def output_path_for(now: datetime) -> Path:
    """현재 월 기준 출력 md 경로 (aggregator 기본 파일명 규약과 동일)."""
    return PROCESS_EVOLUTION_DIR / f"skill_usage_{now.strftime('%Y-%m')}.md"


def should_run(output_path: Path, now: datetime,
               max_age_hours: int = MAX_AGE_HOURS) -> bool:
    """출력 md가 없거나 mtime이 max_age_hours를 초과하면 True(=집계 실행)."""
    if not output_path.exists():
        return True
    age_seconds = now.timestamp() - output_path.stat().st_mtime
    return age_seconds > max_age_hours * 3600


def main() -> int:
    try:
        now = datetime.now()
        output_path = output_path_for(now)
        if not should_run(output_path, now):
            return 0  # 24h 내 갱신본 존재 → 즉시 종료(0초)
        subprocess.run(
            [sys.executable, str(AGGREGATOR), "--output", str(output_path)],
            check=False, capture_output=True, timeout=120,
        )
    except Exception as exc:  # 무해 실패 — Stop 훅 블로킹 금지
        print(f"skill-usage-auto skip: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
