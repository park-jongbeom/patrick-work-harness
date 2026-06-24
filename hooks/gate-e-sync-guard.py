#!/usr/bin/env python3
"""
Gate E CURRENT_SESSION 갱신 강제 — Claude Code Stop Hook.

harness_runtime_charter §4: "기계가 막을 수 있는 것은 기계에 맡긴다"

배경 (GATE-E-ENFORCE-1, 2026-05-18):
  Haiku로 Gate E 실행 시 SESSION_INDEX.md는 ✅E로 갱신하면서
  CURRENT_SESSION.md 대시보드 갱신을 누락하는 사례가 간헐 발생.
  본 훅이 응답 종료 시점에 두 문서의 ✅E 일관성을 검증해 강제한다.

프로토콜 (Claude Code Stop Hook):
  - 입력: stdin JSON — { session_id, ... }
  - 차단: stderr 메시지 + exit 2 (Claude가 종료를 멈추고 계속 작업)
  - 허용: exit 0

차단 조건 (3중 AND):
  (1) CURRENT_SESSION.md 세션 ID 추출 성공
  (2) SESSION_INDEX.md 활성 표에서 그 세션 ID 행의 상태가 ✅E
  (3) CURRENT_SESSION.md 현재 상태/현재 Gate 가 ✅E 아님

파서 복구 (HARNESS-GATE-A-GUARD-1, 2026-06-03):
  기존 (1)(2)는 SESSION_INDEX.md YAML `sessions:` 블록 최상단을 정본으로 삼았으나,
  인덱스 구조 변경(세션 목록 YAML → 마크다운 표 이동)으로 latest_index_session()
  이 항상 (None, None) 반환 → 파싱 실패 → 무조건 허용으로 빠져 no-op 무력화됐다.
  비교 정본을 CURRENT_SESSION.md 세션 ID 로 전환하고, SESSION_INDEX 는
  활성 표에서 '그 세션 ID 행'의 ✅E 여부만 조회한다 (방향 동일: INDEX 완료 ↔
  CURRENT 미완료 불일치 차단).

방어 원칙: 파일 부재·파싱 실패·예외는 무조건 exit 0 (오탐 차단 금지).
무한 루프 방지: 세션별 연속 차단 횟수를 임시 파일에 기록, MAX 초과 시 exit 0.
"""

import json
import os
import re
import sys

# 정본 절대경로 — R-4-2-b: 3단 우선순위 (① GATE_E_GUARD_BASE[테스트] → ② CLAUDE_PROJECT_DIR → ③ 절대경로 폴백)
_proj = os.environ.get("CLAUDE_PROJECT_DIR")
BASE_DIR = (
    os.environ.get("GATE_E_GUARD_BASE")
    or (_proj if _proj else None)
    or os.environ.get("CLAUDE_PROJECT_DIR", ".")
)
SESSION_INDEX = os.path.join(BASE_DIR, "SESSION_INDEX.md")
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


def has_e_done(text):
    """문자열에 ✅E (공백 변형 포함) 가 있는지."""
    return bool(re.search(r"✅\s*E", text))


def index_row_is_e(index_text, session_id):
    """
    SESSION_INDEX.md '활성·예정 세션' 마크다운 표에서 session_id 가 등장하는
    행을 찾아 그 행(상태 열)에 ✅E 표기가 있는지 반환.

    표준 라이브러리만 사용 — 정규식 파싱 (YAML 의존 없음).
    세션 ID 미발견 시 None (판정 불가 → 호출부에서 허용 처리).
    표 행은 취소선(`~~**ID**~~`)·볼드(`**ID**`) 등 장식이 섞이므로 ID 부분
    문자열 포함으로 행을 특정한다.
    """
    if not session_id:
        return None
    for line in index_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        # 표의 첫 칸(세션 ID 열)에 해당 ID 가 포함된 행만 대상
        first_cell = line.split("|")[1] if line.count("|") >= 2 else ""
        if session_id in first_cell:
            return has_e_done(line)
    return None


def current_session_state(cur_text):
    """
    CURRENT_SESSION.md 에서 (세션 ID, ✅E 여부) 추출.
    ✅E 여부는 헤더 '현재 상태' + 대시보드 '현재 Gate' 두 곳을 모두 확인.
    구조 미탐지 시 (sid, None) — 판정 불가로 처리.
    """
    m_id = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z0-9][\w\-]*)", cur_text)
    sid = m_id.group(1) if m_id else None

    fields = []
    m_status = re.search(r"\*\*현재 상태\*\*:\s*(.+)", cur_text)
    if m_status:
        fields.append(m_status.group(1))
    m_gate = re.search(r"현재 Gate\s*\|\s*([^|\n]+)", cur_text)
    if m_gate:
        fields.append(m_gate.group(1))

    if not fields:
        return sid, None
    return sid, any(has_e_done(f) for f in fields)


def counter_path(session_id):
    safe = re.sub(r"[^\w\-]", "_", session_id or "nosession")
    return os.path.join("/tmp", f".gate-e-sync-guard-{safe}.count")


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
    index_text = read_text(SESSION_INDEX)
    cur_text = read_text(CURRENT_SESSION)
    if index_text is None or cur_text is None:
        clear_counter(cpath)
        allow()

    # ── 파싱 (실패 시 검증 불가 → 허용) ──
    cur_id, cur_is_e = current_session_state(cur_text)
    index_is_e = index_row_is_e(index_text, cur_id)
    if not cur_id or cur_is_e is None or index_is_e is None:
        clear_counter(cpath)
        allow()

    # ── 차단 조건 (3중 AND) ──
    # (1) CURRENT 세션 ID 확보 (2) 그 ID 의 INDEX 표 행 = ✅E (3) CURRENT 미완료
    mismatch = index_is_e and (not cur_is_e)

    if not mismatch:
        clear_counter(cpath)
        allow()

    # ── 불일치 — 무한 루프 방지 (연속 차단 한도) ──
    attempts = read_counter(cpath) + 1
    write_counter(cpath, attempts)

    if attempts > MAX_BLOCKS:
        print(
            f"[GATE-E-SYNC] ⚠️ {MAX_BLOCKS}회 연속 차단에도 미해소 — 강제 종료 허용.\n"
            f"  CURRENT_SESSION.md 대시보드를 수동으로 ✅E 갱신하세요.",
            file=sys.stderr,
        )
        clear_counter(cpath)
        allow()

    block(
        f"[GATE-E-SYNC] Gate E 미완료 — CURRENT_SESSION.md 갱신 누락 "
        f"({attempts}/{MAX_BLOCKS})\n"
        f"  SESSION_INDEX.md : 세션 '{cur_id}' 표 행 = ✅E\n"
        f"  CURRENT_SESSION.md: 동일 세션이나 대시보드가 아직 ✅E 아님\n"
        f"  조치: CURRENT_SESSION.md 를 ✅E 로 갱신 —\n"
        f"    ① 헤더 '현재 상태' → ✅E 완료\n"
        f"    ② 대시보드 '현재 Gate' → ✅E 완료\n"
        f"    ③ 대시보드 'Gate 진행' 행 → 마지막 E 를 E✅ 로\n"
        f"  Gate E 스킬 Step 5(3문서 ✅E 상태 전환) 미수행분입니다."
    )


if __name__ == "__main__":
    main()
