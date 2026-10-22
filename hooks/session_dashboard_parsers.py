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


def split_table_cells(line):
    """마크다운 표 한 줄 → 칸 목록(앞뒤 공백 제거).

    `\\|` 와 백틱 안의 `|` 는 칸 구분이 아니다 — 그냥 `split("|")` 하면 SKILL.md
    표를 다루는 계획처럼 칸 안에 파이프가 든 행에서 열이 밀린다(코드 리뷰 실측).
    백틱이 짝이 안 맞으면 백틱을 무시하고 다시 나눈다.
    """
    s = line.strip()

    def _split(code_aware):
        cells, cur, in_code, k = [], [], False, 0
        while k < len(s):
            ch = s[k]
            if ch == "\\" and k + 1 < len(s) and s[k + 1] == "|":
                cur.append("|")
                k += 2
                continue
            if code_aware and ch == "`":
                in_code = not in_code
            if ch == "|" and not in_code:
                cells.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
            k += 1
        cells.append("".join(cur))
        return cells, in_code

    cells, unbalanced = _split(True)
    if unbalanced:
        cells, _ = _split(False)
    if s.startswith("|"):
        cells = cells[1:]
    if s.endswith("|") and not s.endswith("\\|") and cells:
        cells = cells[:-1]
    return [c.strip() for c in cells]


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
    match = re.search(r"\*\*세션 ID\*\*:\s*([A-Za-z0-9\-]+)(?:\s*\(([^)]+)\))?", content)
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

    # YAML 헤더에서 gate 상태 추출
    gate_status = ""
    gate_match = re.search(r'gate:\s*"([^"]+)"', content)
    if gate_match:
        gate_status = gate_match.group(1)

    # YAML 헤더에서 next_action 추출
    next_action = ""
    action_match = re.search(r'next_action:\s*"([^"]+)"', content)
    if action_match:
        next_action = action_match.group(1)

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
        gate_status,
        next_action,
    )


# ─────────────────────────────────────────────────────────────────────
# Gate A 계획 파싱 (DASHBOARD-PLAN-VIZ-1, 2026-09-25)
#
# 왜 별도 함수인가: `parse_current_session`·`parse_session_index` 는 반환
# 계약(8-tuple·키 집합)이 시험으로 고정돼 있다. 계획 파싱을 그 안에 넣으면
# 언패킹 길이가 바뀌어 sync 가 죽는다 — 그래서 **덧붙이기**만 한다.
#
# 방어 원칙: 계획 블록은 사람이 자유롭게 쓰는 산문이다. 못 찾으면 빈 dict 를
# 돌려주고, 호출부는 섹션을 통째로 생략한다(대시보드는 계속 뜬다).
# ─────────────────────────────────────────────────────────────────────

# 실측 근거: 원본 작업공간의 Gate A 계획 289개 파일에서 헤딩 빈도를 세어
# 정했다(2026-09-25). 표기 흔들림이 커서 **고정 문자열이 아니라 부분일치**다.
#   변경 파일: "변경 파일 목록" 39 · "변경 파일" 37 · "실제 변경 파일" 20 · "변경 파일 (N개)" 다수
#   리스크:   "리스크 및 대응" 56 · "리스크" 26 · "리스크와 대응" 8 · "리스크·대응" 2
#   실행순서: "실행 순서" 45 · "실행 순서 (의존 기반)" 8
_SECTION_ALIASES = {
    "files": ("변경 파일", "변경파일", "변경/도입 파일", "변경·도입 파일",
              "도입 파일", "파일 목록", "파일별", "변경 예상 파일",
              "변경 계획"),
    "steps": ("실행 순서", "구현 Step", "실행 Step", "Step 계획", "구현 순서",
              "작업 순서"),
    "risks": ("리스크", "위험"),
    "refs": ("기존 구현 참조", "기존 참조"),
    "verify": ("Gate D 예상", "Gate D 판단", "테스트 계획", "검증 계획",
               "검증 방법", "테스트 방법", "완료 게이트", "완료 조건"),
}


def _plan_block(content):
    """`## Gate A ...` 블록 본문만 잘라 반환. 없으면 빈 문자열.

    실측 표기 변형(289개 기준): "## Gate A 계획" 119 · "## Gate A 블록" 23 ·
    "## Gate A 계획 요약" 17 · "## Gate A 계획 (승인 완료)" 16 · "## Gate A — 계획" 11.
    → `^## Gate A` 접두 매치로 전부 흡수한다.

    종료는 **같은 레벨(`## `)의 다음 헤딩**이다. `### ` 하위 절은 계획의
    일부이므로 넘기면 안 된다.
    """
    return _gate_block(content, "A")[1]


def _gate_block(content, letter):
    """`## Gate <letter> ...` 블록 → (헤딩 원문, 본문). 없으면 ("", "").

    `_plan_block` 의 절단 규칙을 Gate 글자만 바꿔 쓸 수 있게 뺀 것이다
    (DASHBOARD-FULL-PLAN, 2026-10-11). 계획 전문 패널이 A~D 블록을 같은
    규칙으로 자른다.
    """
    m = re.search(rf"^##\s+(Gate {letter}[^\n]*)\n", content, re.MULTILINE)
    if not m:
        return "", ""
    rest = content[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return m.group(1).strip(), (rest[: nxt.start()] if nxt else rest)


def _fence_spans(text):
    """``` 코드 블록이 차지하는 (시작, 끝) 문자 범위들. 닫히지 않으면 끝까지."""
    spans, start, pos = [], None, 0
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            if start is None:
                start = pos
            else:
                spans.append((start, pos + len(line)))
                start = None
        pos += len(line)
    if start is not None:
        spans.append((start, len(text)))
    return spans


def _outside_fences(matches, text):
    """코드 블록 안에서 걸린 제목 매치를 뺀다 — 계획이 인용한 템플릿의 `### 질문 N`
    이 절을 쪼개 블록을 반으로 자르던 것(코드 리뷰 실측)."""
    spans = _fence_spans(text)
    return [m for m in matches if not any(a <= m.start() < b for a, b in spans)]


def parse_gate_documents(content):
    """Gate A~D 블록을 **마크다운 원문 그대로** 절 단위로 넘긴다.

    왜 `parse_gate_a_plan` 과 따로 두는가: 그쪽은 다섯 가지를 골라 한 줄씩으로
    납작하게 만든다. 요약에는 맞지만, 계획의 배경·근거·중첩 항목은 거기서
    사라진다 — 실측(2026-10-11)으로 계획 한 건의 줄·표 칸 135개 중 26개만
    화면에 남았다. 사람이 화면 하나로 계획을 이해하려면 **고르지 않은 원문**이
    필요하다. 그래서 여기서는 아무것도 고르지 않고, 다듬지도 않는다.

    반환: `[{"gate": "A", "heading": "...", "sections": [(제목, 본문), ...]}, ...]`
    `###` 앞에 놓인 글은 제목이 `""` 인 절로 넘긴다 — 버리면 화면에서 사라진다.
    `####` 이하는 절 본문의 일부다. 블록이 없으면 빈 목록.
    """
    docs = []
    if not content:
        return docs
    for letter in "ABCD":
        heading, block = _gate_block(content, letter)
        if not block.strip():
            continue
        marks = _outside_fences(
            list(re.finditer(r"^###[ \t]+([^\n]+)$", block, re.MULTILINE)), block
        )
        sections = []
        lead = block[: marks[0].start()] if marks else block
        if lead.strip():
            sections.append(("", lead.strip("\n")))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
            sections.append((m.group(1).strip(), block[m.end(): end].strip("\n")))
        docs.append({"gate": letter, "heading": heading, "sections": sections})
    return docs


#: 절 시작으로 인정하는 두 표기 — `### 헤딩` 과 줄머리 굵은 라벨 `**라벨**:`.
#  실측(909개 계획 문서)에서 짧은 세션은 `###` 를 안 쓰고
#  `**변경 파일 (5, ≤7)**:` 처럼 굵은 라벨 한 줄로 절을 연다. `###` 만 보면
#  그런 문서에서 아무것도 못 뽑는다.
#  주의: 헤딩 캡처는 **탐욕적**이어야 한다. `.+?` 로 두면 뒤의 `tail` 이
#  나머지를 다 흡수해 제목이 한 글자(`0`·`G`)로 잘린다(실측 회귀).
#  굵은 라벨의 콜론은 **선택**이다 — `**변경/도입 파일 목록**` 처럼 콜론 없이
#  제목만 굵게 쓴 표기가 실측에 흔하다.
#  공백 수량자는 반드시 `[ \t]*` 다. `\s*` 로 두면 줄바꿈을 넘어가 **바로
#  다음 줄의 `### 헤딩`까지 삼킨다** — 그러면 그 절이 통째로 사라진다(실측).
_SECTION_HEAD_RE = re.compile(
    r"^(?:###[ \t]+(?P<h>[^\n]+)"
    r"|\*\*(?P<b>[^*\n]{1,40}?)\*\*[ \t]*(?:[:：][ \t]*)?(?P<tail>[^\n]*))$",
    re.MULTILINE,
)


def _sections(block):
    """계획 블록을 `헤딩 → 본문` 목록으로 분해(헤딩 원문 유지).

    2단 전략이다. `###` 헤딩이 있으면 **그것만** 절 구분자로 쓴다 — 굵은
    라벨을 같이 인정하면 절 본문 안의 `**강조**:` 가 절을 쪼개 원래 잘 되던
    문서가 오히려 망가진다(실측: 파일 추출 54%→7%). `###` 가 하나도 없는
    문서에서만 굵은 라벨형으로 폴백한다.

    굵은 라벨형은 라벨 뒤에 이어지는 같은 줄 내용(`tail`)도 본문에 넣는다 —
    `**점검**: 적합성 ✅ …` 처럼 한 줄로 끝나는 절이 있기 때문.
    """
    found = _outside_fences(list(_SECTION_HEAD_RE.finditer(block)), block)
    heads = [m for m in found if m.group("h")]
    marks = heads or [m for m in found if m.group("b")]
    out = []
    for i, m in enumerate(marks):
        title = (m.group("h") or m.group("b") or "").strip()
        if not title:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
        tail = m.group("tail") if m.group("b") else ""
        body = (tail or "") + "\n" + block[m.end(): end]
        out.append((title, body.strip()))
    return out


def _find_section(sections, kind):
    """별칭 부분일치로 섹션 본문을 찾는다. 첫 매치 우선."""
    for title, body in sections:
        for alias in _SECTION_ALIASES[kind]:
            if alias in title:
                return title, body
    return "", ""


def _table_rows(body):
    """마크다운 표 → 행 리스트(구분선·헤더 제외). 표가 없으면 빈 리스트."""
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = split_table_cells(line)
        if not cells or all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue  # 구분선
        rows.append(cells)
    return rows[1:] if len(rows) > 1 else []  # 첫 행 = 헤더


def _table_header(body):
    """마크다운 표의 헤더 행(칸 목록). 표가 없으면 빈 리스트.

    `_table_rows` 는 헤더를 버린다. 열 이름을 모르면 렌더러가 제 이름을
    붙이게 되고, 그 이름이 계획의 열과 어긋난다(실측: `심각도` 열이
    「원인」 밑에 찍혔다).
    """
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("|"):
            return [_strip_md(c) for c in split_table_cells(line)]
    return []


def parse_gate_a_plan(content):
    """CURRENT_SESSION.md 의 Gate A 계획을 사람이 볼 구조로 추출.

    계획이 없거나 형식이 달라 못 읽으면 **빈 dict** 를 돌려준다 —
    렌더러는 그때 계획 섹션을 통째로 생략한다(무회귀).
    """
    empty = {
        "present": False, "files": [], "steps": [], "risks": [],
        "scope_checks": [], "refs": "", "verify": "", "evidence": {},
        "risk_header": [],
    }
    if not content:
        return empty

    block = _plan_block(content)
    if not block.strip():
        return empty

    secs = _sections(block)
    plan = dict(empty, present=True)

    # ── 변경 파일 ──
    # 실측 표기 3종을 모두 받는다(원본 909개 계획 문서 기준):
    #   `**1. \`path\` (수정)**` 굵은 항목 · `1. \`path\` (생성)` 평범한 번호목록 ·
    #   표 양식 · `- \`path\`` 불릿. 번호목록형이 가장 많아 굵기를 선택으로 둔다.
    _, files_body = _find_section(secs, "files")
    if files_body:
        for m in re.finditer(
            r"^(?:\*\*)?\d+\.\s*(.+?)(?:\*\*)?\s*$", files_body, re.MULTILINE
        ):
            plan["files"].append(_clean_file_entry(m.group(1)))
        if not plan["files"]:
            for row in _table_rows(files_body):
                # 모든 칸을 잇는다. 앞 2칸만 이으면 `| # | 저장소 | 경로 |`
                # 표에서 정작 경로가 떨어져 나간다(실측).
                plan["files"].append(
                    _clean_file_entry(" — ".join(c for c in row if c))
                )
        if not plan["files"]:
            for m in re.finditer(r"^[-*]\s+(.+?)\s*$", files_body, re.MULTILINE):
                plan["files"].append(_clean_file_entry(m.group(1)))

    # ── 구현 Step: `1. **제목**` 번호 목록 ──
    _, steps_body = _find_section(secs, "steps")
    if steps_body:
        for m in re.finditer(r"^(\d+)\.\s+(.+?)\s*$", steps_body, re.MULTILINE):
            plan["steps"].append((m.group(1), _strip_md(m.group(2))))
        if not plan["steps"]:
            for m in re.finditer(r"^[-*]\s+(.+?)\s*$", steps_body, re.MULTILINE):
                plan["steps"].append(("", _strip_md(m.group(1))))

    # ── 리스크: 표(`| 리스크 | 원인 | 대응 |`) 우선, 없으면 불릿 ──
    _, risk_body = _find_section(secs, "risks")
    if risk_body:
        for row in _table_rows(risk_body):
            plan["risks"].append([_strip_md(c) for c in row])
        if plan["risks"]:
            plan["risk_header"] = _table_header(risk_body)
        if not plan["risks"]:
            for m in re.finditer(r"^[-*]\s+(.+?)\s*$", risk_body, re.MULTILINE):
                plan["risks"].append([_strip_md(m.group(1))])

    # ── 범위 점검 체크박스(R-12): 계획 어디에 있든 전부 수집 ──
    for m in re.finditer(r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$", block, re.MULTILINE):
        line = m.group(2)
        # 한 줄에 `· [x] …` 로 여러 항목을 몰아 쓴 표기(실측 다수)를 분해
        parts = re.split(r"\s*·\s*\[[ xX]\]\s*", line)
        plan["scope_checks"].append((m.group(1).lower() == "x", _strip_md(parts[0])))
        for extra in parts[1:]:
            plan["scope_checks"].append((True, _strip_md(extra)))

    # 체크박스 없이 산문으로 쓴 범위 점검(실측 다수):
    #   `### Gate A 범위 점검 (R-12): 파일 7개·Step 4개·… → 통과.`
    # 헤딩 줄 자체에 결과가 실리는 형태라 위 체크박스 수집에 안 걸린다.
    if not plan["scope_checks"]:
        for title, body in secs:
            if "범위 점검" not in title:
                continue
            text = (title.split(":", 1)[1] if ":" in title else "") or body
            text = _strip_md(text)
            if text:
                passed = ("통과" in text or "✅" in text) and "미통과" not in text
                plan["scope_checks"].append((passed, text[:200]))
            break

    # ── 폴백: 전용 절 없이 `- 위험: …` 한 줄로 쓴 표기 ──
    # 실측상 전용 `### 리스크` 절이 압도적(56+26+8건)이지만, 짧은 세션은
    # `### 4~10. (요약)` 한 절에 몰아 쓴다. 전용 절을 못 찾았을 때만 인라인
    # 라벨을 줍는다 — 리스크가 조용히 사라지면 사람이 「위험 없음」으로
    # 오독하기 때문이다(빈 화면보다 나쁜 것은 틀린 안심이다).
    if not plan["risks"]:
        for m in re.finditer(
            r"^[-*]\s*(?:\*\*)?(?:위험|리스크)(?:\*\*)?\s*[:：]\s*(.+?)$",
            block, re.MULTILINE,
        ):
            # 한 줄에 `·` 로 여러 건을 이어 쓴 표기를 건별로 끊는다. 이어 붙은
            # 채로 두면 화면에 긴 한 덩어리로 나와 「리스크 1건」으로 오독된다.
            # 괄호 안의 `·` 는 자르지 않는다(설명 중간이라 문장이 깨진다).
            # 구분자는 **공백으로 둘러싼** ` · ` 만 인정한다. 한국어는
            # `nested JSON·배열` 처럼 명사를 붙이는 데도 가운뎃점을 쓰기
            # 때문에, 붙어 있는 `·` 까지 자르면 한 건이 둘로 쪼개진다.
            line = _strip_md(m.group(1))
            depth, cur, parts = 0, "", []
            i = 0
            while i < len(line):
                ch = line[i]
                if ch in "([{（":
                    depth += 1
                elif ch in ")]}）":
                    depth = max(0, depth - 1)
                if (
                    ch == "·"
                    and depth == 0
                    and i > 0
                    and line[i - 1] == " "
                    and i + 1 < len(line)
                    and line[i + 1] == " "
                ):
                    parts.append(cur)
                    cur = ""
                else:
                    cur += ch
                i += 1
            parts.append(cur)
            for part in parts:
                part = part.strip(" ·")
                if part:
                    plan["risks"].append([part])

    _, plan["refs"] = _find_section(secs, "refs")
    _, plan["verify"] = _find_section(secs, "verify")
    if not plan["verify"]:
        m = re.search(
            r"^[-*]\s*(?:\*\*)?(?:검증|Gate D)(?:\*\*)?[^:：]*[:：]\s*(.+?)$",
            block, re.MULTILINE,
        )
        if m:
            plan["verify"] = m.group(1)
    plan["refs"] = _strip_md(plan["refs"])[:400]
    plan["verify"] = _strip_md(plan["verify"])[:400]

    # ── 주장-근거 태그(ⓐ 실측 / ⓑ 파일인용 / ⓒ 추론) 개수 ──
    # ⓒ 가 남아 있으면 「아직 확인 안 한 주장」이 있다는 뜻이다 — 사람이
    # 가장 먼저 봐야 할 신호라 개수를 따로 센다.
    # 태그 범례 표의 행(`| ⓒ 추론 | … |`)은 주장이 아니다 — 빼고 센다.
    # 범례를 적은 계획에 「미검증 주장 1건」이 뜨던 것(엔진 이슈 #3 잔여).
    counted = "\n".join(
        ln for ln in block.splitlines()
        if not _EVIDENCE_LEGEND_RE.match(ln)
    )
    for tag in ("ⓐ", "ⓑ", "ⓒ"):
        # `ⓒ 0건` 처럼 **개수를 적은 표기**는 태그로 세지 않는다. 그것까지
        # 세면 「미검증 주장 0건」이라고 쓴 계획에 경고 타일이 뜬다(실측).
        n = len(re.findall(rf"{tag}(?!\s*\d+\s*건)", counted))
        # 대신 적힌 수는 따로 읽어 **둘 중 큰 값**을 쓴다. 적힌 수를 버리면
        # 「ⓒ 2건」이라고 쓴 계획이 0건으로 나온다(HARNESS-DASH-LEARN-1-a 후속).
        # 과대 표시는 검토자가 확인하게 만들 뿐이지만, 과소 표시는 놓치게 한다.
        # 한 줄 안의 「ⓒ 1건 → … 최종 ⓒ 0건」 은 한 주장의 전후다 — 그 줄의
        # **마지막** 수를 쓴다. 줄끼리는 그대로 큰 값(과소 표시 방지).
        written = []
        for ln in counted.splitlines():
            nums = re.findall(rf"{tag}\s*(\d+)\s*건", ln)
            if nums:
                written.append(int(nums[-1]))
        n = max([n] + written)
        if n:
            plan["evidence"][tag] = n

    return plan


_EVIDENCE_LEGEND_RE = re.compile(
    r"^\s*\|\s*(?:\*\*)?[ⓐⓑⓒ]\s*(?:실측|파일\s*인용|추론)(?:\*\*)?\s*\|"
)


# ─────────────────────────────────────────────────────────────────────
# 이해 브리핑 · Gate B 질문 (HARNESS-DASH-LEARN-1-b-2, 2026-10-14)
#
# gate-a 는 계획 맨 앞에 `### 이해 브리핑` 4항목을, gate-b 는 낸 질문을
# `### 질문 N` + 읽을 곳 + 평가로 적게 한다. 대시보드는 이 둘을 **맨 위**에
# 보여 준다 — 요약(흐름)과 전문(절차 기록 포함)만으로는 「왜·어떻게」를
# 찾기 어려웠다. 못 찾으면 빈 값이고, 렌더러가 안내 문구로 바꾼다.
# ─────────────────────────────────────────────────────────────────────

#: 브리핑 정식 라벨(순서 = 화면 순서).
BRIEFING_LABELS = ("왜 바꾸나", "어떻게 동작하나", "가장 깨지기 쉬운 곳", "되돌리는 법")

#: 규칙화 전 시범 계획(2026-10-11, 2건)이 쓴 라벨 → 정식 라벨.
_BRIEFING_ALIASES = {"왜 하는가": "왜 바꾸나", "핵심 동작": "어떻게 동작하나"}

#: 평가 자리표시 — gate-b 템플릿의 한·영 문구. 이것만 「평가 전」이다.
_EVAL_PLACEHOLDER_RE = re.compile(
    r"\(\s*(?:답변\s*후\s*기록|평가\s*전|filled after the answer)\s*\)", re.IGNORECASE
)

_BRIEF_ITEM_RE = re.compile(r"^[-*]\s+\*\*([^*\n]+?)\*\*\s*[:：]?\s*(.*)$")


def _labeled_items(body):
    """`- **라벨**: 본문` 목록 → [(라벨, 본문)]. **들여쓴** 이어진 줄만 본문에 붙인다.

    `**왜 바꾸나:**` 처럼 콜론을 굵은 글씨 안에 넣은 표기도 같은 라벨이다.
    들여쓰지 않은 다른 줄(뒤에 덧붙인 문단·일반 글머리)은 앞 항목에 붙이지
    않는다 — 붙이면 메모 문단이 「되돌리는 법」 카드에 섞였다(코드 리뷰 실측).
    """
    items, attach = [], False
    for line in body.splitlines():
        m = _BRIEF_ITEM_RE.match(line.strip()) if not line[:1].isspace() else None
        if m:
            label = m.group(1).strip().rstrip(":：").strip()
            items.append([label, m.group(2).strip()])
            attach = True
        elif not line.strip():
            continue
        elif items and attach and line[:1].isspace():
            items[-1][1] = (items[-1][1] + " " + line.strip()).strip()
        else:
            attach = False
    return [(k, v) for k, v in items]


def parse_comprehension(content):
    """이해 브리핑 4항목과 Gate B 질문을 읽는다.

    반환: `{"briefing": [(정식 라벨, 본문)…],  # 정식 라벨 순서, 찾은 것만
            "missing": [빠진 정식 라벨…],     # 브리핑 절이 없으면 빈 목록
            "questions": [{"title", "text", "where", "evaluated"}…]}`

    브리핑 **절 자체가 없으면** `briefing`·`missing` 모두 빈 목록이다 — 「절이
    없음」과 「일부 항목 빠짐」을 렌더러가 다르게 말해야 하기 때문이다.
    """
    out = {"briefing": [], "missing": [], "questions": []}
    if not content:
        return out
    try:
        return _parse_comprehension(content, out)
    except Exception:  # 자유 산문 — 못 읽으면 빈 값(대시보드는 계속 뜬다)
        return {"briefing": [], "missing": [], "questions": []}


def _parse_comprehension(content, out):
    """`parse_comprehension` 본체. 예외는 호출부가 가둔다."""

    _, a_block = _gate_block(content, "A")
    for title, body in _sections(a_block):
        if "이해 브리핑" not in title:
            continue
        found = {}
        for label, text in _labeled_items(body):
            label = _BRIEFING_ALIASES.get(label, label)
            if label in BRIEFING_LABELS and label not in found:
                found[label] = text
        out["briefing"] = [(lb, found[lb]) for lb in BRIEFING_LABELS if lb in found]
        out["missing"] = [lb for lb in BRIEFING_LABELS if lb not in found]
        break

    _, b_block = _gate_block(content, "B")
    for title, body in _sections(b_block):
        if not title.startswith("질문"):
            continue
        fields = dict(_labeled_items(body))
        # 질문 본문 = 라벨 줄이 나오기 전까지의 글
        text_lines = []
        for line in body.splitlines():
            if _BRIEF_ITEM_RE.match(line.strip()):
                break
            if line.strip():
                text_lines.append(line.strip())
        evaluation = ""
        for key, val in fields.items():
            if "평가" in key or "재질문" in key:
                evaluation += val
        # 자리표시(「(답변 후 기록)」)만 있으면 아직 평가 전이다. 괄호로 감싼
        # 실제 평가(「(통과 — 정확히 답함)」)까지 자리표시로 보면, 끝난 질문이
        # 「지금 답할 질문」으로 다시 뜬다(코드 리뷰 실측).
        evaluated = bool(evaluation.strip()) and not _EVAL_PLACEHOLDER_RE.fullmatch(
            evaluation.strip()
        )
        out["questions"].append({
            "title": title,
            "text": " ".join(text_lines),
            "where": fields.get("읽을 곳", ""),
            "evaluated": evaluated or "통과" in title,
        })
    return out


#: 레인 판정 블록의 라벨 (S6, 2026-10-22). gate-a/SKILL.md §0-Lane 의 예시와 같아야 한다
#: — 엔진 린트가 그 예시를 이 함수로 읽어 확인한다.
LANE_LABELS = ("레인", "걸린 트리거", "기준 커밋", "수락 명령")


def parse_lane_decision(content):
    """Gate A 계획의 `### 레인 판정` 블록을 읽는다 (S6, 2026-10-22).

    반환: `{"lane": "자율"|"검토", "reasons": [검토로 떨어진 이유…],
            "triggers": str, "base_commit": str, "acceptance": [명령…], "files": [경로…]}`

    대시보드 파서들과 극성이 **반대**다 — 칸 하나라도 비었거나 형식이 다르거나
    예외가 나면 「검토」다(fail-closed). 레인 범위 훅(S7)이 이 결과로 자율 레인을
    열지 정하므로, 못 읽은 계획이 자율로 새면 안 된다.
    """
    out = {"lane": "검토", "reasons": [], "triggers": "", "base_commit": "",
           "acceptance": [], "files": []}
    try:
        return _parse_lane_decision(content or "", out)
    except Exception:
        return dict(out, lane="검토", reasons=["레인 판정 블록을 읽지 못함"])


def _parse_lane_decision(content, out):
    """`parse_lane_decision` 본체. 예외는 호출부가 가둔다."""
    secs = _sections(_plan_block(content))
    _, body = next(((t, b) for t, b in secs if "레인 판정" in t), ("", ""))
    if not body:
        out["reasons"].append("레인 판정 블록 없음")
        return out
    items = dict(_labeled_items(body))
    lane = _strip_md(items.get("레인", ""))
    out["triggers"] = _strip_md(items.get("걸린 트리거", ""))
    base = _strip_md(items.get("기준 커밋", ""))
    out["acceptance"] = re.findall(r"`([^`\n]+)`", items.get("수락 명령", ""))

    _, files_body = _find_section(secs, "files")
    entries = re.findall(r"^(?:\*\*)?\d+\.\s*(.+?)(?:\*\*)?\s*$", files_body, re.MULTILINE)
    paths = [re.search(r"`([^`\n]+)`", e) for e in entries]
    out["files"] = [p.group(1) for p in paths if p]

    reasons = out["reasons"]
    if not re.fullmatch(r"자율(?:\s*[(（].*)?", lane):
        reasons.append(f"레인 값이 자율이 아님: {lane or '(비어 있음)'}")
    if not re.fullmatch(r"없음\.?", out["triggers"]):
        reasons.append(f"걸린 트리거: {out['triggers'] or '(비어 있음)'}")
    if re.fullmatch(r"[0-9a-f]{7,40}", base):
        out["base_commit"] = base
    else:
        reasons.append("기준 커밋이 커밋 해시가 아님")
    if not out["acceptance"]:
        reasons.append("수락 명령이 `백틱` 명령으로 적혀 있지 않음")
    if not entries or len(out["files"]) != len(entries):
        reasons.append("변경 파일 목록에 `경로` 가 없는 항목이 있음")
    if not reasons:
        out["lane"] = "자율"
    return out


def _clean_file_entry(text):
    """파일 항목에서 경로와 변경유형을 최대한 평이하게 남긴다."""
    return _strip_md(text)


def _strip_md(text):
    """마크다운 강조·백틱 제거 + 공백 정리(HTML 이스케이프는 렌더러 책임)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────
# 시각화 보조 (DASHBOARD-PLAN-VIZ-2, 2026-09-25)
#
# 1차(VIZ-1)는 총계 타일 말고는 전부 텍스트 목록이라 **「잘 꾸민 목록」**이었다.
# 사용자 판정: 「화면은 잘 보이는데 시각적인 자료가 없다」. 아래 두 함수는
# 이미 파싱해 둔 값에서 **그릴 수 있는 형태**를 뽑는다 — 새 파싱은 없다.
# ─────────────────────────────────────────────────────────────────────

#: 경중 판정 키워드. 실측 빈도(909개 계획 문서): 사소 70 · 경미 18 ·
#: 위험 낮음/낮은 위험 8 · 심각 6 · 위험 높음 1.
#: 압도적으로 **낮은 쪽 표현만** 쓰인다 — 그래서 기본값을 「보통」으로 두고,
#: 낮다고 **명시한 것만** 낮춘다. 안 적힌 위험을 낮음으로 칠하면 화면이
#: 「전부 안전하다」고 거짓말한다.
_RISK_LOW = ("사소", "경미", "위험 낮음", "낮은 위험", "무시 가능", "영향 없음")
_RISK_HIGH = ("심각", "치명", "위험 높음", "높은 위험", "데이터 손실", "유실")


def risk_severity(cells):
    """리스크 행 → "high" | "med" | "low".

    표 형식이면 셀 전체를, 불릿이면 그 문장을 본다. 판정 근거는 **본문 표현**
    뿐이다 — 점수를 지어내지 않는다(일반 confidence 점수는 승인 화면
    안티패턴으로 지목된 것이라 쓰지 않는다).
    """
    text = " ".join(str(c) for c in cells)
    if any(k in text for k in _RISK_HIGH):
        return "high"
    if any(k in text for k in _RISK_LOW):
        return "low"
    return "med"


def group_files(files):
    """변경 파일 목록 → [(디렉터리, [파일명, ...]), ...].

    **어디에 몰렸는지**를 보여주기 위한 묶음이다(blast radius 패턴에서
    「주요 그룹핑」에 해당). 경로가 아닌 항목(설명문 등)은 `""` 그룹으로
    모아 그대로 보여준다 — 버리면 계획에 있던 줄이 화면에서 사라진다.
    """
    groups = {}
    order = []
    for entry in files:
        # `path/to/x.py (수정)` 에서 경로 부분만 떼어 본다
        head = entry.split(" ")[0].strip("`")
        if "/" in head:
            directory, _, name = head.rpartition("/")
            directory += "/"
            rest = entry[len(head):].strip()
            label = f"{name} {rest}".strip()
        else:
            directory, label = "", entry
        if directory not in groups:
            groups[directory] = []
            order.append(directory)
        groups[directory].append(label)
    return [(d, groups[d]) for d in order]


def scope_gauges(checks):
    """범위 점검 체크박스 → [(라벨, 현재값, 한도), ...].

    `변경 파일 ≤ 7개 (2개)` 처럼 **한도와 실제치가 같은 줄에** 적히는 표기
    (실측 다수)에서 두 수를 뽑아 막대로 그릴 수 있게 한다. 둘 다 못 찾으면
    그 항목은 게이지에서 빠지고 체크 목록으로만 남는다.
    """
    out = []
    for _ok, text in checks:
        limit = re.search(r"≤\s*(\d+)", text)
        actual = re.search(r"\((?:실측\s*)?(\d+)\s*(?:개|건)?", text)
        if not (limit and actual):
            continue
        label = re.split(r"\s*≤", text)[0].strip()
        out.append((label, int(actual.group(1)), int(limit.group(1))))
    return out
