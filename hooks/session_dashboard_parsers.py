"""세션 대시보드 마크다운 파서 모듈

`CURRENT_SESSION.md`·`SESSION_INDEX.md`에서 대시보드 렌더링에 필요한
정보를 추출한다. HSA-2(2026-05-28)에서 `session-dashboard-sync.py`로부터
분리: 진입점은 파일명 불변 강제, 파싱 책임만 본 모듈로 이동.
"""

import re


def _strip_history(text):
    """priority_note 메가라인에서 현재 세션 head만 반환.

    이력 체인의 구조적 prepend 구분자(개행 선행 ``> (이전 ``) 이후는 과거
    세션 이력 → 배너에 덤프되지 않도록 절단. 현재 head의 ``직전: X ✅E``
    종결 라인은 구분자 이전이므로 보존된다.

    DASHBOARD-BANNER-FIX-1은 콜론 앵커(``이전:|직전:``)로 차단했으나, 세션
    중간(A/B/C) head는 ``직전:`` 종결자가 없어(종결자는 Gate E 완료 시
    prepend) 콜론 정규식이 head를 지나쳐 첫 과거 항목의 콜론까지 과포착 →
    "head+직전1건 잔존"(실측 1602자)이 남았다. FIX-2: 이력 구분자를 앵커로
    전환해 어떤 Gate 상태에서도 현재 head만 남긴다. 개행 선행 조건은 현재
    head prose 내 ``> (이전 `` 백틱 인용을 구분자로 오인하지 않게 한다
    (priority_note는 단일행 YAML이라 개행이 리터럴 ``\\n``으로 저장됨).

    정본 선례 error-topics-guard.py:110 strip_history는 콜론 앵커 유지
    (보수적 과탐·별 블래스트)이므로 본 파서만 구조적 앵커로 분기한다.

    FIX-3: 수량자를 ``\\n``(백슬래시 1개)→``\\+n``(1개+)으로 변경. 실 파일
    구분자는 백슬래시 2개형(``\\\\n``)이 다수라 1개형 앵커로는 절단점이 둘째
    백슬래시 앞에 떨어져 trailing 백슬래시 1개가 잔존했다(코스메틱).
    """
    m = re.search(r"\\+n> \(이전 ", text)
    return text[: m.start()] if m else text


def parse_current_session(content):
    """CURRENT_SESSION.md에서 핵심 정보 추출"""
    data = {
        "session_id": "",
        "work_topic": "",
        "intent_title": "",
        "intent_note": "",
        "status": "",
        "gate_progress": "",
        "repos": [],
        "files_changed": "",
        "start_date": "",
        "end_date": "",
        "test_result": "",
        "model_rec": "",
    }

    # 세션 ID + 괄호 안 작업 주제 (예: "PLAN-SYNC-18 (audit 10회차 산출물 흡수 — ...)")
    match = re.search(r"\*\*세션 ID\*\*:\s*([A-Z0-9\-]+)(?:\s*\(([^)]+)\))?", content)
    if match:
        data["session_id"] = match.group(1)
        if match.group(2):
            data["work_topic"] = match.group(2).strip()

    # 세션 주제 (배너 제목용 평이 한 줄) — work_topic 캡처 패턴 1:1
    match = re.search(r"\*\*세션 주제\*\*:\s*(.*?)(?:\n|$)", content)
    if match:
        data["intent_title"] = match.group(1).strip()

    # 작업 의도 (배너 본문용 평이 1~2문장)
    match = re.search(r"\*\*작업 의도\*\*:\s*(.*?)(?:\n|$)", content)
    if match:
        data["intent_note"] = match.group(1).strip()

    # 현재 상태
    match = re.search(r"\*\*현재 상태\*\*:\s*(.*?)(?:\n|$)", content)
    if match:
        data["status"] = match.group(1).strip()

    # Gate 진행
    match = re.search(r"Gate 진행\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        data["gate_progress"] = match.group(1).strip()

    # 저장소
    match = re.search(r"저장소\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        repos_str = match.group(1).strip()
        data["repos"] = [r.strip() for r in repos_str.split(",")]

    # 변경 파일
    match = re.search(r"변경 파일\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        data["files_changed"] = match.group(1).strip()

    # 착수일
    match = re.search(r"착수일\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        data["start_date"] = match.group(1).strip()

    # 완료일
    match = re.search(r"완료일\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        data["end_date"] = match.group(1).strip()

    # 테스트 결과
    match = re.search(r"R/V/D 분해\s*\|\s*(.*?)(?:\n|$)", content)
    if match:
        data["test_result"] = match.group(1).strip()

    # 권장 모델 (두 필드명 모두 허용 — 과거 세션 호환)
    match = re.search(
        r"(?:Gate별 권장 모델|권장 모델)\s*\|\s*(.*?)(?:\n|$)", content
    )
    if match:
        data["model_rec"] = match.group(1).strip()

    return data


def parse_session_index(content):
    """SESSION_INDEX.md에서 세션 목록 추출"""
    sessions = {
        "active": [],
        "completed": [],
    }

    # YAML 헤더에서 project 추출
    project = ""
    proj_match = re.search(r'project:\s*"([^"]+)"', content)
    if proj_match:
        project = proj_match.group(1)

    # YAML 헤더에서 last_updated 추출
    last_updated = ""
    match = re.search(r'last_updated:\s*"([^"]+)"', content)
    if match:
        last_updated = match.group(1)

    # YAML 헤더에서 현재(첫) 세션의 사람이 읽는 목적(title) 추출
    # sessions: 블록 첫 항목의 `- id: "..." \n title: "..."` 쌍
    current_title = ""
    title_match = re.search(
        r'-\s*id:\s*"[^"]+"\s*\n\s*title:\s*"([^"]+)"', content
    )
    if title_match:
        current_title = title_match.group(1)

    # 목적 보조 설명용 priority_note 추출
    priority_note = ""
    note_match = re.search(r'priority_note:\s*"([^"]+)"', content)
    if note_match:
        priority_note = _strip_history(note_match.group(1))

    # 현재 세션 (활성)
    active_match = re.search(
        r"## 현재 세션\n\n\|\s*세션 ID.*?\n(.*?)(?:\n## )",
        content,
        re.DOTALL,
    )
    if active_match:
        rows = active_match.group(1).strip().split("\n")
        # group(1) 첫 줄은 separator(`|---|...|`) 1줄. 그 다음부터 데이터 행.
        for row in rows[1:]:  # separator 1줄 스킵
            if row.strip() and "|" in row:
                parts = [p.strip() for p in row.split("|")]
                if len(parts) >= 4:
                    sessions["active"].append(
                        {
                            "id": parts[1],
                            "title": parts[2],
                            "repo": parts[3],
                            "status": parts[4] if len(parts) > 4 else "",
                        }
                    )

    # 최근 완료 세션
    completed_match = re.search(
        r"## 최근 완료 세션\n\n\|\s*세션 ID.*?\n(.*?)(?:\n##|$)",
        content,
        re.DOTALL,
    )
    if completed_match:
        rows = completed_match.group(1).strip().split("\n")
        for row in rows[1:]:  # separator 1줄 스킵 (활성 표와 동일 사유)
            if row.strip() and "|" in row:
                parts = [p.strip() for p in row.split("|")]
                if len(parts) >= 5:
                    sessions["completed"].append(
                        {
                            "id": parts[1],
                            "title": parts[2],
                            "repo": parts[3],
                            "status": parts[4],
                        }
                    )

    # 「최근 완료」 표 첫 데이터 행의 제목 (활성 세션 없을 때 배너 폴백용)
    last_completed_title = ""
    if sessions["completed"]:
        last_completed_title = sessions["completed"][0]["title"]

    return (
        sessions,
        last_updated,
        current_title,
        priority_note,
        last_completed_title,
        project,
    )
