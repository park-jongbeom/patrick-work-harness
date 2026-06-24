#!/usr/bin/env python3
"""
이해도 ledger 만료 자동 감지 — Claude Code Stop Hook (비차단 알림).

harness_runtime_charter §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

배경 (COMPREHEND-GATE-1-b, 2026-06-21):
  COMPREHEND-GATE-1 이 만든 이해도 게이트 증적 원장
  (plans/learning/comprehension_ledger.md)은 각 항목의 exp(만료 조건)이
  지나면 재검증이 필요하다. 그러나 현재는 comprehend-gate 게이트가
  '발동'한 세션의 Step 1 에서만 수동으로 만료를 조회한다 — 게이트가
  발동하지 않는 세션에서는 만료를 놓친다. 본 훅이 응답 종료 시점에
  원장을 스캔해 exp(N개월) 날짜가 지난 항목을 surface 한다.

차단 정책 (COMPREHEND-GATE-1-b Gate A 사용자 결정):
  **비차단** — 만료 항목 발견 시 stderr 안내만 출력하고 exit 0.
  ledger 만료는 단일 응답 턴에서 고칠 수 없는 '재검증 프로세스'이고
  (다음 gate-a/comprehend-gate Step 1 에서 수행), 기존 stale-guard 처럼
  exit 2 로 매 세션 차단하면 무관한 세션을 모두 막아 부적합하다.
  비차단이라 무한 루프 위험이 없어 연속 차단 카운터를 두지 않는다.

감지 범위 (COMPREHEND-GATE-1-b Gate A 사용자 결정):
  exp 의 'N개월' 날짜 경과만 자동 감지한다. SKILL 의 또 다른 만료
  조건인 'scope 파일 실질변경 시'는 워크스페이스가 git 이 아니라
  mtime 기반 추정만 가능해(취약·YAGNI) comprehend-gate Step 1 의
  수동 판정으로 남긴다.

프로토콜 (Claude Code Stop Hook):
  - 입력: stdin JSON — { session_id, stop_hook_active, ... }
  - 비차단 알림: stderr 메시지 + exit 0 (종료를 막지 않음)
  - 허용: exit 0

방어 원칙: 파일 부재·파싱 실패·예외·만료 0건은 무조건 exit 0
  (오탐 알림 금지). progress-report-stale-guard.py 와 동일.
"""

import calendar
import json
import os
import re
import sys
from datetime import date

# R-4-2-a: CLAUDE_PROJECT_DIR 기반 이식성 폴백 (env 부재 시 절대경로 유지)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
_default_ledger = (
    str(Path(_proj).parent / "plans" / "learning" / "comprehension_ledger.md")
    if _proj
    else os.environ.get("COMPREHENSION_LEDGER_PATH", "plans/learning/comprehension_ledger.md")
)
LEDGER_PATH = os.environ.get("COMPREHENSION_LEDGER_PATH", _default_ledger)


def allow():
    """응답 종료 허용 — exit 0."""
    sys.exit(0)


def notify(reason):
    """비차단 알림 — stderr 출력 후 exit 0 (종료를 막지 않음)."""
    print(reason, file=sys.stderr)
    sys.exit(0)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def parse_iso_date(value):
    """'YYYY-MM-DD' → date. 실패 시 None (백틱·공백 제거)."""
    try:
        return date.fromisoformat(value.strip().strip("`").strip())
    except Exception:
        return None


def add_months(d, n):
    """date 에 n개월 가산 (일자 보존·말일 보정·stdlib만)."""
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def expired_entries(ledger_text, today):
    """
    증적 표에서 만료된(exp 'N개월' 경과) 항목 목록 반환.

    각 행 형식: | verified | scope | exp | 설명 주체 | 결과 | 설명 요약 |
    - verified 가 YYYY-MM-DD 로 파싱되고 exp 에 'N개월'이 있는 행만 평가.
    - 헤더·구분선·템플릿(_..._)·'실질변경 시'(월수 없음) 행은 자동 skip.
    반환: [(verified_str, scope, n_months, expiry, days_over), ...]
    """
    expired = []
    for line in ledger_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        verified = parse_iso_date(cells[0])
        if verified is None:
            continue  # 헤더·구분선·템플릿 행
        m = re.search(r"(\d+)\s*개월", cells[2])
        if not m:
            continue  # 'N개월' 만료 조건 없음 (scope 변경형 → 수동 판정)
        n_months = int(m.group(1))
        expiry = add_months(verified, n_months)
        if today > expiry:
            expired.append(
                (cells[0], cells[1], n_months, expiry, (today - expiry).days)
            )
    return expired


def main():
    # ── stdin payload (실패해도 진행 — exit 0 폴백) ──
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # ── Stop 훅 재발동 중이면 즉시 통과 (중복 알림 방지·공식 BP) ──
    if payload.get("stop_hook_active"):
        allow()

    # ── 원장 로드 (부재 시 검증 불가 → 허용) ──
    ledger_text = read_text(LEDGER_PATH)
    if ledger_text is None:
        allow()

    # ── 만료 항목 스캔 (개별 행 파싱 실패는 내부에서 skip) ──
    try:
        expired = expired_entries(ledger_text, date.today())
    except Exception:
        allow()

    if not expired:
        allow()

    # ── 만료 ≥1건 — 비차단 알림 ──
    lines = [
        f"[COMPREHENSION-LEDGER-STALE] 이해도 ledger 만료 항목 {len(expired)}건 "
        f"— 재검증 권장 (비차단·종료 막지 않음)"
    ]
    for verified, scope, n_months, expiry, days_over in expired:
        lines.append(
            f"  - scope '{scope}': verified {verified} + {n_months}개월 "
            f"→ 만료 {expiry.isoformat()} ({days_over}일 경과)"
        )
    lines.append(
        "  조치: 해당 scope 작업 재개 시 comprehend-gate Step 1 에서 재검증하세요 "
        "(간격 둔 재인출 = 기억 강화)."
    )
    notify("\n".join(lines))


if __name__ == "__main__":
    main()
