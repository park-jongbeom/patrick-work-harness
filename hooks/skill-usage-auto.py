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

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# 필드 부재 시 기본값 — learning_path 와 동일한 하위 호환 패턴
_DEFAULT_PROCESS_EVOLUTION_PATH = "plans/process_evolution"


def _find_answers_yml():
    """harness-answers.yml 경로 탐색 (CLAUDE_PROJECT_DIR → cwd).

    docker-command-guard.py:44-54 와 동일 패턴 (정본 재사용).
    """
    candidates = []
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        candidates.append(os.path.join(proj, ".claude", "harness-answers.yml"))
    candidates.append(
        os.path.join(os.getcwd(), ".claude", "harness-answers.yml")
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _simple_parse_process_evolution_path(text):
    """PyYAML 미설치 대비 간이 파서 — process_evolution_path 스칼라만 추출."""
    import re
    m = re.search(
        r"^process_evolution_path\s*:\s*[\"']?([^\"'#\r\n]+?)[\"']?\s*(?:#.*)?$",
        text,
        re.MULTILINE,
    )
    return m.group(1).strip() if m else None


def _load_process_evolution_path():
    """harness-answers.yml → process_evolution_path. 미설정·실패 시 기본값(fail-open)."""
    path = _find_answers_yml()
    if not path:
        return _DEFAULT_PROCESS_EVOLUTION_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        if _YAML_AVAILABLE:
            data = yaml.safe_load(raw) or {}
            value = data.get("process_evolution_path")
        else:
            value = _simple_parse_process_evolution_path(raw)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return _DEFAULT_PROCESS_EVOLUTION_PATH
    except Exception:
        return _DEFAULT_PROCESS_EVOLUTION_PATH


def _resolve_process_evolution_dir():
    """기록 디렉터리 3단 우선순위 해석.

    ① SKILL_USAGE_PROCESS_EVOLUTION_DIR env (테스트 오버라이드)
    ② harness-answers.yml process_evolution_path (SSOT)
    ③ 기본값 "plans/process_evolution" (필드 부재 시 하위 호환)

    ②③ 의 상대경로는 CLAUDE_PROJECT_DIR(부재 시 cwd) 기준으로 해석한다.
    comprehension-ledger-stale-guard.py 의 learning_path 해석과 동형(정본 재사용).

    HARNESS-SYNC-RECONCILE-2-b (2026-08-07): 종전에는 `Path(_proj).parent / "plans"` 로
    워크스페이스 형제 배치를 코드에 가정하고, env 부재 시 사설 절대경로로 폴백했다.
    경로가 빗나가도 훅이 조용히 통과해 스킬 사용 이력이 아무 데도 쌓이지 않았다.
    """
    override = os.environ.get("SKILL_USAGE_PROCESS_EVOLUTION_DIR")
    if override:
        return Path(override)
    target = Path(_load_process_evolution_path())
    if not target.is_absolute():
        base = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        target = base / target
    return target


PROCESS_EVOLUTION_DIR = _resolve_process_evolution_dir()
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
