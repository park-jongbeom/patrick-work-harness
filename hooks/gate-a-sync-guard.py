#!/usr/bin/env python3
"""
Gate A 대시보드 갱신 강제 — Claude Code Stop Hook.

harness_runtime_charter §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

배경 (HARNESS-GATE-A-GUARD-1, 2026-06-03):
  session-dashboard-sync.py(Stop 훅 #0)는 CURRENT_SESSION.md 를 무조건 HTML 로
  굽는 렌더러일 뿐, Gate A 가 그 파일을 실제로 새 세션 정보로 갱신했는지는
  검증하지 않는다. Gate A 응답에서 갱신을 누락하면 옛 내용이 그대로 구워져
  "대시보드가 안 바뀐다"로 보인다. 본 훅이 응답 종료 시점에 Gate A 진행 중인데
  대시보드 배너 필수 필드가 누락됐는지 검사해 강제한다.
  (gate-e-sync-guard.py 와 대칭 — 발동 시점만 Gate A 로 다름.)

프로토콜 (Claude Code Stop Hook):
  - 입력: stdin JSON — { session_id, stop_hook_active, ... }
  - 차단: stderr 메시지 + exit 2 (Claude 가 종료를 멈추고 계속 작업)
  - 허용: exit 0

차단 조건 (3중 AND):
  (1) CURRENT_SESSION.md 가 'Gate A 진행 중' 신호 — 현재 Gate(또는 현재 상태)에
      'A' 가 명시되고 ✅E/B/C/D 가 아님
  (2) 세션 ID 추출 성공
  (3) 배너·대시보드 필수 필드 중 하나라도 누락 —
      '세션 주제' / '작업 의도'(DASHBOARD-INTENT-1 의무 2줄) / 'Gate 진행' / '착수일'

방어 원칙: 파일 부재·파싱 실패·예외·Gate A 아님은 무조건 exit 0 (오탐 차단 금지).
무한 루프 방지: 세션별 연속 차단 횟수를 임시 파일에 기록, MAX 초과 시 exit 0.
"""

import json
import os
import re
import sys

# 정본 절대경로 — R-4-2-b: 3단 우선순위 (① GATE_A_GUARD_BASE[테스트] → ② CLAUDE_PROJECT_DIR → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
BASE_DIR = (
    os.environ.get("GATE_A_GUARD_BASE")
    or (_proj if _proj else None)
    or os.environ.get("CLAUDE_PROJECT_DIR", ".")
)
CURRENT_SESSION = os.path.join(BASE_DIR, "CURRENT_SESSION.md")

# 연속 차단 한도 (무한 루프 방지)
MAX_BLOCKS = 3


def allow():
    """응답 종료 허용 — exit 0."""
    sys.exit(0)


def block(reason):
    """응답 종료 차단 — stderr + exit 2."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def is_gate_a_phase(cur_text):
    """
    CURRENT_SESSION.md 가 'Gate A 진행 중' 인지 판정.

    '현재 Gate' 또는 '현재 상태' 값에 'A' 가 명시되고, 이미 다음 Gate(B/C/D/E)
    나 완료(✅E)로 넘어가지 않았을 때만 True.
    Gate A 응답 턴에만 발동하기 위함(HARNESS-GATE-A-GUARD-1 범위: Gate A 한정).
    판정 근거 미탐지 시 False (= 발동 안 함).
    """
    fields = []
    m_gate = re.search(r"현재 Gate\s*\|\s*([^|\n]+)", cur_text)
    if m_gate:
        fields.append(m_gate.group(1))
    m_status = re.search(r"\*\*현재 상태\*\*:\s*(.+)", cur_text)
    if m_status:
        fields.append(m_status.group(1))

    for f in fields:
        # 이미 완료(✅E)나 후속 Gate 면 Gate A 단계 아님
        if re.search(r"✅\s*E", f):
            return False
        # 'A' 가 (승인 대기)·A⏳ 등으로 명시되고 B/C/D/E 표기가 없는 경우
        if re.search(r"\bA\b|A\s*\(|A⏳", f) and not re.search(
            r"\b[BCDE]\b\s*\(|[BCDE]✅", f
        ):
            return True
    return False


def session_id(cur_text):
    """CURRENT_SESSION.md 헤더 '**세션 ID**' 값 추출."""
    m_id = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z0-9][\w\-]*)", cur_text)
    return m_id.group(1) if m_id else None


def missing_fields(cur_text):
    """
    배너·대시보드 필수 필드 중 누락(부재·공백)된 항목 목록 반환.

    - '세션 주제'(배너 제목) · '작업 의도'(배너 본문): DASHBOARD-INTENT-1 의무 2줄
    - 'Gate 진행' · '착수일': 대시보드 필수 행
    """
    checks = [
        ("세션 주제", r"\*\*세션 주제\*\*:\s*(\S.*)"),
        ("작업 의도", r"\*\*작업 의도\*\*:\s*(\S.*)"),
        ("Gate 진행", r"Gate 진행\s*\|\s*(\S[^\n]*)"),
        ("착수일", r"착수일\s*\|\s*(\S[^\n]*)"),
    ]
    missing = []
    for label, pattern in checks:
        m = re.search(pattern, cur_text)
        if not m or not m.group(1).strip():
            missing.append(label)
    return missing


def counter_path(sid):
    safe = re.sub(r"[^\w\-]", "_", sid or "nosession")
    return os.path.join("/tmp", f".gate-a-sync-guard-{safe}.count")


def read_counter(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0


def write_counter(path, value):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(value))
    except Exception:
        pass


def clear_counter(path):
    try:
        os.remove(path)
    except OSError:
        pass


def main():
    # ── stdin payload (실패해도 진행 — exit 0 폴백) ──
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # ── 무한 루프 1차 방어: Stop 훅 재발동 중이면 즉시 통과 (공식 BP) ──
    # 이미 Stop 훅으로 인해 재발동된 호출이면 차단하지 않는다 (Issue #55754).
    # 런타임이 stop_hook_active 미제공 시 .get() falsy → 아래 카운터 2차 방어로 폴백.
    if payload.get("stop_hook_active"):
        allow()

    cpath = counter_path(payload.get("session_id", ""))

    # ── 문서 로드 (부재 시 검증 불가 → 허용) ──
    cur_text = read_text(CURRENT_SESSION)
    if cur_text is None:
        clear_counter(cpath)
        allow()

    # ── Gate A 단계 아님 → 발동 안 함 (범위: Gate A 한정) ──
    if not is_gate_a_phase(cur_text):
        clear_counter(cpath)
        allow()

    # ── 세션 ID 미탐지 → 검증 불가 → 허용 ──
    sid = session_id(cur_text)
    if not sid:
        clear_counter(cpath)
        allow()

    # ── 필수 필드 누락 검사 ──
    missing = missing_fields(cur_text)
    if not missing:
        clear_counter(cpath)
        allow()

    # ── 누락 — 무한 루프 방지 (연속 차단 한도) ──
    attempts = read_counter(cpath) + 1
    write_counter(cpath, attempts)

    if attempts > MAX_BLOCKS:
        print(
            f"[GATE-A-SYNC] ⚠️ {MAX_BLOCKS}회 연속 차단에도 미해소 — 강제 종료 허용.\n"
            f"  CURRENT_SESSION.md 대시보드 필수 필드를 수동으로 채우세요.",
            file=sys.stderr,
        )
        clear_counter(cpath)
        allow()

    block(
        f"[GATE-A-SYNC] Gate A 진행 중 — CURRENT_SESSION.md 대시보드 갱신 누락 "
        f"({attempts}/{MAX_BLOCKS})\n"
        f"  세션 '{sid}' 가 Gate A 단계이나 필수 필드가 비어 있습니다.\n"
        f"  누락 필드: {', '.join(missing)}\n"
        f"  조치: CURRENT_SESSION.md 를 갱신 —\n"
        f"    ① 헤더 '> **세션 주제**:' (배너 제목, 평이 한 줄)\n"
        f"    ② 헤더 '> **작업 의도**:' (배너 본문, 무엇을 왜 1~2문장)\n"
        f"    ③ 대시보드 'Gate 진행' 행 (예: A⏳ → B☐ → C☐ → E☐)\n"
        f"    ④ 대시보드 '착수일' 행\n"
        f"  Gate A 스킬 Step 2(문서 3곳 갱신) 미수행분입니다.\n"
        f"  ※ 갱신 후 session-dashboard.html 은 Stop 훅이 자동 재생성합니다."
    )


if __name__ == "__main__":
    main()
