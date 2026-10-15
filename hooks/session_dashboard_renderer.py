"""세션 대시보드 HTML 렌더링 모듈

`parse_current_session`·`parse_session_index` 결과를 받아 단일 HTML
문서를 생성한다. HSA-2(2026-05-28)에서 `session-dashboard-sync.py`로부터
분리: 진입점은 파일명 불변 강제, 렌더링 책임만 본 모듈로 이동.

HSA-2-b(2026-05-28): CSS 393줄을 `dashboard.css` 외부 파일로 추출하고
`_load_css()`로 빌드 시 인라인 삽입 — HTML 출력은 self-contained 유지
(byte 동등성 보존) + 본 모듈 줄 수는 KPI ≤ 250 충족.
"""

import html as _html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 시각화 보조(경중 판정·파일 묶음·게이지)는 파서 모듈에 있다. Stop 훅은 실행
# cwd 가 이 디렉터리가 아닐 수 있어 경로를 먼저 넣는다(sync 진입점과 동일 규약).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_dashboard_parsers import (  # noqa: E402
    BRIEFING_LABELS,
    group_files,
    risk_severity,
    scope_gauges,
    split_table_cells,
)

_HOOKS_DIR = Path(__file__).resolve().parent
_CSS_PATH = _HOOKS_DIR / "dashboard.css"

# 정본 저장소(아카이브) 경로 — env 폴백(skill-usage-auto.py 동일 변수 규약 재사용).
# 미설정 시 본가 절대경로 폴백 → 정본 footer byte-equivalent + plugin sync 시 정의 동반(NameError 해소).
HARNESS_PLANS_DIR = os.environ.get("HARNESS_PLANS_DIR", ".")


def _load_css():
    """`dashboard.css` 읽기 — Stop hook 실행 cwd와 무관한 절대 경로."""
    return _CSS_PATH.read_text(encoding="utf-8")


def _esc(text):
    """HTML 이스케이프.

    계획 본문은 사람이 자유롭게 쓴 산문이라 `<T>`·`&`·`"` 가 그대로 들어온다.
    이스케이프 없이 끼워 넣으면 화면이 깨지거나 태그가 먹힌다. 배너·표 등
    기존 필드는 오래 쓰인 경로라 건드리지 않고, **이번에 새로 넣는 계획
    영역에만** 적용한다(무회귀).
    """
    return _html.escape(str(text if text is not None else ""), quote=True)


#: 경중 표시의 뜻. 색만 칠하면 「빨강이 뭔데?」가 되고, 특히 **색각 이상**에서는
#: 빨강·노랑 구분이 어렵다 — 그래서 범례에 말로 적고 개수를 함께 보여준다.
_SEV_LABEL = {
    "high": "심각·유실 언급",
    "med": "경중 미표기 (기본)",
    "low": "사소·낮음 명시",
}


def _risk_legend(risks):
    """리스크 경중 범례 — 실제로 나온 등급만 보여준다.

    🔴 **기본값이 「보통」인 것을 숨기지 않는다.** 계획에 경중이 안 적히면
    med 가 되는데, 그걸 말 없이 노란 점으로만 두면 **AI 가 위험도를 판정한
    것처럼** 보인다. 범례에 「경중 미표기 (기본)」이라고 적어 **누가 정한
    값인지**를 드러낸다(원본의 유보를 함께 옮긴다 — 지침 §3-3).
    """
    counts = {}
    for r in risks:
        sev = risk_severity(r)
        counts[sev] = counts.get(sev, 0) + 1
    if not counts:
        return ""
    parts = ""
    for sev in ("high", "med", "low"):
        if sev not in counts:
            continue
        parts += (
            '                    <span class="plan-legend-item">'
            f'<span class="plan-dot plan-dot-{sev}"></span>'
            f'{_esc(_SEV_LABEL[sev])} {counts[sev]}</span>\n'
        )
    return f'                <div class="plan-legend">\n{parts}                </div>\n'


# ─────────────────────────────────────────────────────────────────────
# 계획 전문 패널 (DASHBOARD-FULL-PLAN, 2026-10-11)
#
# 요약 패널(`render_gate_a_plan`)은 계획에서 다섯 가지만 골라 싣는다. 그래서
# 계획에 적힌 배경·근거가 화면에 없었고, 사람이 화면만 보고는 이해도 질문에
# 답할 수 없었다. 아래는 Gate 블록을 **고르지 않고 전부** 싣는다.
#
# 마크다운 라이브러리는 쓰지 않는다 — 훅은 추가 설치 없이 돌아야 한다. 계획
# 문서가 실제로 쓰는 부분집합(문단·중첩 목록·표·인용·체크박스·굵게·코드)만
# 표준 라이브러리로 바꾼다.
# ─────────────────────────────────────────────────────────────────────

_LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_TABLE_SEP_RE = re.compile(r":?-{2,}:?")


def _md_inline(text):
    """한 줄 안의 서식. **이스케이프가 먼저다** — 본문의 `<T>`·`&` 가 태그로
    먹히지 않게 한 뒤, 우리가 만든 태그만 입힌다."""
    s = _esc(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def _md_list(items, i, indent):
    """들여쓰기 깊이로 중첩 목록을 만든다.

    `items` = [들여쓰기, 번호목록?, 글, 시작 번호, 항목 아래 블록 HTML].
    같은 깊이에서 목록 종류(`-` ↔ `1.`)가 바뀌면 거기서 끊는다 — 호출부가 새
    목록으로 이어 그린다. 번호 목록은 첫 번호를 `start` 로 살린다.
    """
    ordered = items[i][1]
    tag = "ol" if ordered else "ul"
    start = items[i][3] if ordered and items[i][3] not in (None, 1) else None
    parts = []
    while i < len(items) and items[i][0] >= indent:
        if items[i][0] > indent:
            sub, i = _md_list(items, i, items[i][0])
            if parts:
                parts[-1] += sub  # 하위 목록은 바로 위 항목 안에 넣는다
            else:
                parts.append(sub)
            continue
        if items[i][1] != ordered and parts:
            break
        text = items[i][2]
        box = re.match(r"\[([ xX])\]\s*(.*)$", text)
        if box:
            mark = "☐" if box.group(1) == " " else "✅"
            text = f"{mark} {box.group(2)}"
        parts.append(_md_inline(text) + items[i][4])
        i += 1
    body = "".join(f"<li>{p}</li>" for p in parts)
    open_tag = f'<ol start="{start}">' if start else f"<{tag}>"
    return f"{open_tag}{body}</{tag}>", i


def _md_table(lines):
    rows = [split_table_cells(line) for line in lines]
    has_head = len(rows) > 1 and all(
        _TABLE_SEP_RE.fullmatch(c or "-") for c in rows[1]
    )
    out = '<table class="doc-table">'
    if has_head:
        out += "<thead><tr>" + "".join(
            f"<th>{_md_inline(c)}</th>" for c in rows[0]
        ) + "</tr></thead>"
        rows = rows[2:]
    out += "<tbody>"
    for cells in rows:
        out += "<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in cells) + "</tr>"
    return out + "</tbody></table>"


def _md_block_to_html(md):
    """계획 문서용 마크다운 부분집합 → HTML. 모르는 줄은 문단으로 둔다."""
    lines = md.splitlines()
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + "<br>".join(_md_inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append("<pre>" + _esc("\n".join(lines[i + 1: j])) + "</pre>")
            i = j + 1
        elif not stripped:
            flush()
            i += 1
        elif stripped.startswith("|"):
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_md_table(lines[i:j]))
            i = j
        elif _LIST_RE.match(line):
            flush()
            items = []
            while i < len(lines):
                cur = lines[i]
                cur_s = cur.strip()
                m = _LIST_RE.match(cur)
                if m:
                    marker = m.group(2)
                    num = int(marker[:-1]) if marker[0].isdigit() else None
                    items.append([len(m.group(1)), num is not None, m.group(3), num, ""])
                    i += 1
                elif not cur_s:
                    # 빈 줄 하나로 목록을 끊지 않는다 — 다음 내용이 항목이거나 들여쓴
                    # 줄이면 같은 목록이다(끊으면 「1. 2. 3.」 이 「1. 1. 1.」 로 보였다).
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and (_LIST_RE.match(lines[j]) or lines[j][:1] in " \t"):
                        i = j
                        continue
                    break
                elif cur[:1] in " \t" and items:
                    # 항목 아래 들여쓴 블록 — 코드·표는 블록 그대로, 나머지는 이어진 글
                    if cur_s.startswith("```"):
                        pad = len(cur) - len(cur.lstrip())
                        j = i + 1
                        while j < len(lines) and not lines[j].strip().startswith("```"):
                            j += 1
                        code = "\n".join(
                            ln[pad:] if not ln[:pad].strip() else ln.strip()
                            for ln in lines[i + 1: j]
                        )
                        items[-1][4] += "<pre>" + _esc(code) + "</pre>"
                        i = j + 1
                    elif cur_s.startswith("|"):
                        j = i
                        while j < len(lines) and lines[j].strip().startswith("|"):
                            j += 1
                        items[-1][4] += _md_table(lines[i:j])
                        i = j
                    else:
                        items[-1][2] += " " + cur_s
                        i += 1
                else:
                    break
            # 들여쓰기가 첫 항목보다 얕은 항목이 있어도 하나도 버리지 않는다
            pos = 0
            while pos < len(items):
                html_part, pos = _md_list(items, pos, items[pos][0])
                out.append(html_part)
        elif stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(_md_inline(lines[i].strip()[1:].strip()))
                i += 1
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
        elif stripped.startswith("####"):
            flush()
            out.append("<h4>" + _md_inline(stripped.lstrip("#").strip()) + "</h4>")
            i += 1
        else:
            para.append(stripped)
            i += 1
    flush()
    return "\n".join(out)


#: 전문 패널에서 기본으로 접는 절차 기록 절(제목 부분일치).
_PROCESS_SECTIONS = ("권장 모델", "범위 점검", "점검 결과", "대조 검증", "범위 밖")


def render_comprehension(comp, plan_present=False):
    """맨 위 이해 패널 — 지금 답할 질문 + 「이 계획 이해하기」 카드.

    요약(흐름)과 전문(절차 기록 포함)만으로는 이해도 질문의 답을 찾기
    어려웠다(HARNESS-DASH-LEARN-1-b-2). 그래서 계획의 이해 브리핑 4항목을
    가장 먼저, 크게 보여 준다.
    - 질문 상자에는 **평가가 없는 마지막 질문**의 본문과 읽을 곳만 싣는다.
      평가는 답을 담고 있어 지난 질문 목록(접힘)에서만 보인다.
    - 읽을 곳에 브리핑 라벨이 그대로 들어 있을 때만 카드로 가는 링크를 단다.
    - 브리핑 절이 없으면 빈칸이 아니라 **없다고 말한다** — 빈 화면은
      「설명할 게 없는 계획」으로 읽힌다. 계획 자체가 없으면 아무것도 안 그린다.
    """
    comp = comp or {}
    briefing = comp.get("briefing") or []
    missing = comp.get("missing") or []
    questions = comp.get("questions") or []
    if not (briefing or missing or questions or plan_present):
        return ""

    def link_where(where):
        for n, label in enumerate(BRIEFING_LABELS):
            if label in where and any(lb == label for lb, _ in briefing):
                return (f'{_md_inline(where)} '
                        f'<a class="comp-jump" href="#brief-{n}">→ 「{_esc(label)}」 카드로</a>')
        return _md_inline(where)

    html = '        <div class="comp-panel">\n'
    pending = [q for q in questions if not q.get("evaluated")]
    if pending:
        q = pending[-1]
        where = (f'<div class="comp-q-where">📍 읽을 곳: {link_where(q.get("where", ""))}</div>'
                 if q.get("where") else "")
        html += (
            '            <div class="comp-question">\n'
            f'                <div class="comp-q-label">❓ 지금 답할 질문 — {_esc(q.get("title", ""))}</div>\n'
            f'                <div class="comp-q-text">{_md_inline(q.get("text", ""))}</div>\n'
            f'                {where}\n'
            '            </div>\n'
        )

    html += '            <h2>🧠 이 계획 이해하기</h2>\n'
    if briefing or missing:
        found = dict(briefing)
        html += '            <div class="comp-grid">\n'
        for n, label in enumerate(BRIEFING_LABELS):
            text = found.get(label)
            body = (_md_inline(text) if text else
                    '<span class="comp-missing">계획에 이 항목이 없다.</span>')
            html += (
                f'                <div class="comp-item" id="brief-{n}">\n'
                f'                    <div class="comp-item-label">{_esc(label)}</div>\n'
                f'                    <div class="comp-item-body">{body}</div>\n'
                '                </div>\n'
            )
        html += '            </div>\n'
    else:
        html += ('            <p class="comp-none">이 계획에는 이해 브리핑이 없다 — '
                 '아래 「규모와 순서」와 전문에서 찾아야 한다.</p>\n')

    done = [q for q in questions if q.get("evaluated")]
    if done:
        items = "".join(
            f'<li><strong>{_esc(q.get("title", ""))}</strong> {_md_inline(q.get("text", ""))}</li>'
            for q in done
        )
        html += (
            '            <details class="comp-done">\n'
            f'                <summary>지난 질문 {len(done)}개 (평가는 아래 Gate B 전문)</summary>\n'
            f'                <ol>{items}</ol>\n'
            '            </details>\n'
        )
    return html + '        </div>\n\n'


def render_gate_documents(docs):
    """Gate 블록 전문 패널. 블록이 없으면 빈 문자열(섹션 생략).

    - 문서 순서(A→D)대로 그린다. 예전에는 나중 Gate 를 위에 뒀는데, C·D 가
      진행되면 계획(A)이 맨 아래로 밀렸다. 지금 답할 질문은 맨 위 이해
      패널이 따로 보여 준다(HARNESS-DASH-LEARN-1-b-2).
    - 절차 기록 절(권장 모델·범위 점검 등)은 **접힌 채로** 둔다. 모두 펼치면
      「왜·어떻게」가 절차 기록 사이에 묻힌다. 목차에는 그대로 있다.
    - 절 하나의 변환이 실패하면 **그 절만 원문 그대로** 보여주고 나머지는
      계속 그린다. 절을 빼면 읽는 사람이 「렌더 문제로 빠진 것」을 「계획에
      없는 것」으로 오해한다 — 빈 자리보다 다듬지 않은 원문이 낫다.
    - 버튼·폼은 여기에도 없다(요약 패널과 같은 계약). 접기는 `<details>` 다.
    """
    if not docs:
        return ""
    panels = ""
    for doc in docs:
        gate = doc.get("gate", "")
        toc, body = "", ""
        for n, (title, md) in enumerate(doc.get("sections") or []):
            anchor = f"gate-{_esc(gate).lower()}-s{n}"
            label = title or "개요"
            try:
                inner = _md_block_to_html(md)
            except Exception:  # 자유 산문이라 무엇이 올지 모른다 — 절 단위로 가둔다
                inner = (
                    '<p class="doc-fallback">이 절은 서식 변환에 실패해 원문 '
                    "그대로 보여준다.</p>"
                    f'<pre class="doc-raw">{_esc(md)}</pre>'
                )
            toc += f'<a class="doc-toc-item" href="#{anchor}">{_md_inline(label)}</a>\n'
            is_open = "" if any(k in label for k in _PROCESS_SECTIONS) else " open"
            body += (
                f'<details class="doc-section" id="{anchor}"{is_open}>\n'
                f"<summary>{_md_inline(label)}</summary>\n"
                f'<div class="doc-body">\n{inner}\n</div>\n'
                "</details>\n"
            )
        panels += (
            '        <div class="gate-doc">\n'
            f"            <h2>📖 {_esc(doc.get('heading') or 'Gate ' + gate)}"
            " — 전문</h2>\n"
            '            <p class="plan-hint">문서에 적힌 그대로다. 고르거나 '
            "줄이지 않았다.</p>\n"
            f'            <div class="doc-toc">\n{toc}            </div>\n'
            f"{body}"
            "        </div>\n\n"
        )
    return panels


def render_gate_a_plan(plan):
    """Gate A 계획을 '사람이 승인 판단하는' 패널로 렌더한다.

    설계 근거(2026-09-25 조사):
      - 승인 버튼을 늘리지 않는다. Anthropic 계측상 사용자는 권한 프롬프트의
        약 93%를 승인하고, "승인을 많이 볼수록 각각에 주의를 덜 기울인다".
        → 이 패널은 **읽고 판단하는 화면**이지 결재 버튼이 아니다.
        (https://www.anthropic.com/engineering/how-we-contain-claude)
      - 계획을 .md 에서 빼앗지 않는다. 편집은 .md 가 제자리라는 실사용 선호가
        있다(HN 45686364). HTML 은 요약·판정 레이어로만 얹는다.
      - 보여줄 것의 우선순위는 blast radius 패턴을 따른다 — **총계 먼저**,
        그 다음 목록. (https://aiuxplayground.com/pattern/blast-radius-visualization/)
      - 간트·타임라인은 넣지 않는다. 코딩 에이전트 계획 검토에 쓴다는 실증
        사례를 찾지 못했다.

    계획이 없으면 빈 문자열 → 호출부가 섹션을 통째로 생략한다.
    """
    if not plan or not plan.get("present"):
        return ""

    files = plan.get("files") or []
    steps = plan.get("steps") or []
    risks = plan.get("risks") or []
    checks = plan.get("scope_checks") or []
    evidence = plan.get("evidence") or {}

    # ── 1행 요약(총계) — 목록보다 먼저 온다 ──
    unproven = evidence.get("ⓒ", 0)
    tiles = [
        ("변경 파일", f"{len(files)}개" if files else "—"),
        ("구현 Step", f"{len(steps)}개" if steps else "—"),
        ("리스크", f"{len(risks)}건" if risks else "0건"),
        ("미검증 주장 ⓒ", f"{unproven}건" if unproven else "0건"),
    ]
    tile_html = ""
    for label, value in tiles:
        # ⓒ(추론·미승격 주장)가 남아 있으면 그 타일만 경고색 — 사람이 가장
        # 먼저 의심해야 할 지점이기 때문이다.
        warn = " plan-tile-warn" if label.startswith("미검증") and unproven else ""
        tile_html += (
            f'                <div class="plan-tile{warn}">\n'
            f'                    <div class="plan-tile-label">{_esc(label)}</div>\n'
            f'                    <div class="plan-tile-value">{_esc(value)}</div>\n'
            f'                </div>\n'
        )

    # ── 범위 가드(R-12) — 하나라도 미체크면 눈에 띄게 ──
    checks_html = ""
    if checks:
        # 한도와 실제치를 함께 적은 항목은 **막대**로 — 「2/7」 은 숫자로 읽어야
        # 알지만 막대는 한도 근접을 눈으로 보게 한다(R-12 는 쪼갤지 판단하는 자리).
        gauges = scope_gauges(checks)
        gauged_labels = {label for label, _a, _l in gauges}
        bars = ""
        for label, actual, limit in gauges:
            pct = min(100, round(100 * actual / limit)) if limit else 0
            # 한도의 80% 를 넘으면 색을 바꾼다 — 「아직 통과」와 「곧 걸린다」는 다르다
            tone = " plan-bar-near" if pct >= 80 else ""
            near = " · 한도 근접" if pct >= 80 else ""
            bars += (
                '                    <div class="plan-bar-row">\n'
                f'                        <div class="plan-bar-label">{_esc(label)}</div>\n'
                '                        <div class="plan-bar-track">\n'
                f'                            <div class="plan-bar-fill{tone}"'
                f' style="width:{pct}%"></div>\n'
                '                        </div>\n'
                f'                        <div class="plan-bar-num">{actual} / {limit}'
                f'{near}</div>\n'
                '                    </div>\n'
            )

        # 막대로 못 그린 항목(수치가 없는 서술형)만 체크 목록으로 남긴다
        items = ""
        for ok, text in checks:
            if any(text.startswith(lbl) for lbl in gauged_labels):
                continue
            mark = "✅" if ok else "⚠️"
            cls = "plan-check" if ok else "plan-check plan-check-fail"
            items += (
                f'                    <li class="{cls}">{mark} {_esc(text)}</li>\n'
            )
        list_html = (
            f'                <ul class="plan-list">\n{items}                </ul>\n'
            if items else ""
        )
        checks_html = (
            '            <div class="plan-block">\n'
            '                <div class="plan-block-title">범위 가드 (R-12)</div>\n'
            f'{bars}{list_html}'
            '            </div>\n'
        )

    # ── 변경 파일 ──
    files_html = ""
    if files:
        # 디렉터리로 묶어 **변경이 어디에 몰렸는지**를 보이게 한다
        # (blast radius 패턴의 「주요 그룹핑」).
        items = ""
        for directory, names in group_files(files):
            if directory:
                items += (
                    '                    <li class="plan-dir">'
                    f'<span class="plan-dir-name">{_esc(directory)}</span>'
                    f'<span class="plan-dir-count">{len(names)}</span></li>\n'
                )
            for name in names:
                cls = "plan-file plan-file-nested" if directory else "plan-file"
                items += (
                    f'                    <li class="{cls}">{_esc(name)}</li>\n'
                )
        files_html = (
            '            <div class="plan-block">\n'
            '                <div class="plan-block-title">변경 파일 '
            f'({len(files)})</div>\n'
            f'                <ul class="plan-list">\n{items}'
            '                </ul>\n'
            '            </div>\n'
        )

    # ── 구현 Step(실행 순서) ──
    steps_html = ""
    if steps:
        # ① 가로 파이프라인 — 「몇 단계이고 어떤 순서인가」를 먼저 보게 한다.
        #    각 칸에 Step 의 첫 어절을 넣어, 번호만 보고 본문을 뒤지지 않게 한다.
        flow = ""
        for i, (num, text) in enumerate(steps):
            if i:
                flow += '                        <span class="plan-arrow">→</span>\n'
            badge = _esc(num) if num else "•"
            # 제목 = 콜론 앞 또는 첫 두 어절(길면 잘린다 — 상세는 아래 목록에 있다)
            head = text.split(":")[0] if ":" in text[:24] else " ".join(
                text.split()[:2]
            )
            flow += (
                '                        <div class="plan-node">\n'
                f'                            <div class="plan-node-num">{badge}</div>\n'
                f'                            <div class="plan-node-cap">{_esc(head)}</div>\n'
                '                        </div>\n'
            )

        # ② 상세 목록 — 파이프라인이 요약이라면 이쪽이 원문이다
        items = ""
        for num, text in steps:
            badge = _esc(num) if num else "•"
            items += (
                '                    <li class="plan-step">'
                f'<span class="plan-step-num">{badge}</span>'
                f'<span>{_esc(text)}</span></li>\n'
            )
        steps_html = (
            '            <div class="plan-block">\n'
            '                <div class="plan-block-title">실행 순서 '
            f'({len(steps)} Step)</div>\n'
            f'                <div class="plan-flow">\n{flow}'
            '                </div>\n'
            f'                <ol class="plan-list plan-steps">\n{items}'
            '                </ol>\n'
            '            </div>\n'
        )

    # ── 리스크 — 표(리스크/원인/대응)면 표로, 아니면 목록으로 ──
    risks_html = ""
    if risks:
        if any(len(r) >= 2 for r in risks):
            # 계획이 쓴 열 이름과 열 수를 그대로 따른다. 고정 3열·고정 이름이면
            # 4열 표의 「대응」이 잘리고, `심각도` 가 「원인」 밑에 찍힌다(실측).
            # 헤더를 못 받은 경우(손으로 만든 dict·옛 호출부)만 예전 3열이다.
            heads = list(plan.get("risk_header") or [])
            if heads:
                ncol = max(len(heads), max(len(r) for r in risks))
                heads += [""] * (ncol - len(heads))
            else:
                ncol, heads = 3, ["리스크", "원인", "대응"]
            head_html = "".join(f"<th>{_esc(h)}</th>" for h in heads)
            rows = ""
            for r in risks:
                sev = risk_severity(r)
                cells = f'<td><span class="plan-dot plan-dot-{sev}"></span></td>'
                cells += "".join(f"<td>{_esc(c)}</td>" for c in r[:ncol])
                # 열 수가 모자란 행도 표가 깨지지 않게 채운다
                cells += "<td></td>" * max(0, ncol - len(r[:ncol]))
                rows += f"                        <tr>{cells}</tr>\n"
            risks_html = (
                '            <div class="plan-block">\n'
                '                <div class="plan-block-title">리스크 '
                f'({len(risks)})</div>\n'
                '                <table class="plan-risk-table">\n'
                f'                    <thead><tr><th></th>{head_html}'
                '</tr></thead>\n'
                f'                    <tbody>\n{rows}'
                '                    </tbody>\n'
                '                </table>\n'
                f'{_risk_legend(risks)}'
                '            </div>\n'
            )
        else:
            items = ""
            for r in risks:
                sev = risk_severity(r)
                items += (
                    '                    <li class="plan-risk">'
                    f'<span class="plan-dot plan-dot-{sev}"></span>'
                    f'{_esc(r[0])}</li>\n'
                )
            risks_html = (
                '            <div class="plan-block">\n'
                '                <div class="plan-block-title">리스크 '
                f'({len(risks)})</div>\n'
                f'                <ul class="plan-list">\n{items}'
                '                </ul>\n'
                f'{_risk_legend(risks)}'
                '            </div>\n'
            )

    # ── 검증 계획 / 기존 참조 ──
    extra_html = ""
    for label, value in (("검증 계획 (Gate D)", plan.get("verify")),
                         ("기존 구현 참조", plan.get("refs"))):
        if value:
            extra_html += (
                '            <div class="plan-block">\n'
                f'                <div class="plan-block-title">{_esc(label)}</div>\n'
                f'                <p class="plan-prose">{_esc(value)}</p>\n'
                '            </div>\n'
            )

    return (
        '        <div class="plan-review">\n'
        '            <h2>📐 규모와 순서</h2>\n'
        '            <p class="plan-hint">정본은 <code>CURRENT_SESSION.md</code>다. '
        '이 화면은 읽고 판단하기 위한 요약이며, 고칠 것은 .md 에서 고친다.</p>\n'
        f'            <div class="plan-tiles">\n{tile_html}            </div>\n'
        f"{checks_html}{files_html}{steps_html}{risks_html}{extra_html}"
        '        </div>\n\n'
    )


def generate_html(
    current_session,
    sessions,
    last_updated,
    current_title,
    priority_note,
    last_completed_title,
    project="",
    gate_status="",
    next_action="",
    gate_a_plan=None,
    gate_docs=None,
    comprehension=None,
):
    """HTML 생성

    `gate_a_plan` 은 **선택 인자**다(DASHBOARD-PLAN-VIZ-1). 기존 호출부는
    9개 인자로 그대로 호출하며, 그 경우 계획 패널만 빠지고 나머지 화면은
    바이트 동일하다 — 시험이 고정한 호출 계약을 깨지 않기 위함.
    `gate_docs`(계획 전문, DASHBOARD-FULL-PLAN)·`comprehension`(이해 브리핑·
    질문, HARNESS-DASH-LEARN-1-b-2)도 같은 규약의 선택 인자다.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    css = _load_css()

    # 배너 제목 우선순위 (DASHBOARD-INTENT-1):
    # CURRENT_SESSION 평이 「세션 주제」 → YAML title → 「세션 ID (작업 주제)」 괄호
    # → 직전 완료 세션 제목. Gate 상태(status)는 제외 — 배너는 "주제·의도"의 자리
    purpose_text = (
        current_session.get("intent_title", "")
        or current_title
        or current_session.get("work_topic", "")
        or last_completed_title
        or "(작업 주제 미기재)"
    )
    # 배너 본문: 평이 「작업 의도」 우선 → priority_note 폴백(강등, 과거 세션 무회귀)
    purpose_note = current_session.get("intent_note", "") or priority_note
    purpose_note_html = ""
    if purpose_note:
        purpose_note_html = (
            f'\n                <div class="purpose-note">{purpose_note}</div>'
        )

    # 현재 상태 배지 색상 결정
    status_color = "status-complete"
    if "진행 중" in current_session["status"]:
        status_color = "status-in-progress"
    elif "보류" in current_session["status"]:
        status_color = "status-pending"

    # 활성 세션 카드 생성
    active_cards = ""
    for session in sessions["active"]:
        gate_badge_class = "gate-badge"
        if "보류" in session["status"] or "대기" in session["status"]:
            gate_badge_class += " pending"

        repo_badges = ""
        for repo in session["repo"].split(","):
            repo_badges += f'<span class="repo-badge">{repo.strip()}</span>\n                            '

        active_cards += f"""            <div class="session-card">
                <div class="session-header">
                    <div>
                        <div class="session-title">{session['title']}</div>
                    </div>
                    <span class="session-id">{session['id']}</span>
                </div>
                <div class="session-details">
                    <div class="session-detail">
                        <div class="session-detail-label">상태</div>
                        <div class="session-detail-value">
                            <span class="{gate_badge_class}">{session['status']}</span>
                        </div>
                    </div>
                    <div class="session-detail">
                        <div class="session-detail-label">저장소</div>
                        <div class="session-detail-value">
                            {repo_badges}
                        </div>
                    </div>
                </div>
            </div>

"""
    if not active_cards:
        active_cards = '            <p style="color: #999; padding: 20px; text-align: center;">활성 세션 없음</p>\n'

    # 완료 세션 카드 생성
    completed_cards = ""
    for session in sessions["completed"][:4]:  # 최근 4개만
        repo_badges = ""
        for repo in session["repo"].split(","):
            repo_badges += f'<span class="repo-badge">{repo.strip()}</span>'

        completed_cards += f"""            <div class="session-card">
                <div class="session-header">
                    <div>
                        <div class="session-title">{session['title']}</div>
                    </div>
                    <span class="session-id">{session['id']}</span>
                </div>
                <div class="session-details">
                    <div class="session-detail">
                        <div class="session-detail-label">상태</div>
                        <div class="session-detail-value">
                            <span class="gate-badge">{session['status']}</span>
                        </div>
                    </div>
                    <div class="session-detail">
                        <div class="session-detail-label">저장소</div>
                        <div class="session-detail-value">
                            {repo_badges}
                        </div>
                    </div>
                </div>
            </div>

"""

    # Gate A 계획 패널 — 계획이 없거나 못 읽으면 빈 문자열(섹션 생략)
    # 이해 패널이 맨 위다 — 「무엇을 왜 어떻게」가 「규모와 순서」보다 먼저다.
    # 인자를 안 받으면(옛 호출부) 빈 문자열이라 기존 화면과 같다.
    # 이 패널이 예외를 내도 대시보드 나머지는 그린다(패널만 빠진다).
    plan_html = ""
    if comprehension is not None:
        try:
            plan_html += render_comprehension(
                comprehension, bool(gate_a_plan and gate_a_plan.get("present"))
            )
        except Exception:
            plan_html = ""
    plan_html += render_gate_a_plan(gate_a_plan)
    # 계획 전문 — 요약 바로 아래. 요약이 「한눈에」라면 이쪽이 「읽고 이해」다
    plan_html += render_gate_documents(gate_docs)

    # HTML 템플릿
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>세션 대시보드{(' — ' + project) if project else ''}</title>
    <style>
{css}    </style>
</head>
<body>
    <div class="container">
        <div class="last-updated">
            📅 마지막 업데이트: {now} KST
        </div>

        <div class="purpose-banner">
            <div class="purpose-label">🎯 지금 하는 작업</div>
            <div class="purpose-title">{purpose_text}</div>{purpose_note_html}
        </div>

        <header>
            <h1>🎓 {(project + ' — ') if project else ''}세션 대시보드</h1>

            <div class="meta-info">
                <div class="meta-item">
                    <div class="meta-label">현재 세션</div>
                    <div class="meta-value">{current_session['session_id']}</div>
                    <span class="status-badge {status_color}">{current_session['status']}</span>
                </div>

                <div class="meta-item">
                    <div class="meta-label">Gate 진행</div>
                    <div class="meta-value">{current_session['gate_progress']}</div>
                </div>

                <div class="meta-item">
                    <div class="meta-label">작업 기간</div>
                    <div class="meta-value">{current_session['start_date']}</div>
                    <span class="status-badge {status_color}">진행 중</span>
                </div>

                <div class="meta-item">
                    <div class="meta-label">마지막 동기화</div>
                    <div class="meta-value">{last_updated}</div>
                </div>
{f'''                <div class="meta-item">
                    <div class="meta-label">Gate 상태</div>
                    <div class="meta-value">{gate_status}</div>
                </div>
''' if gate_status else ''}{f'''                <div class="meta-item">
                    <div class="meta-label">다음 행동</div>
                    <div class="meta-value">{next_action}</div>
                </div>
''' if next_action else ''}            </div>
        </header>

{plan_html}        <div class="sessions">
            <h2>📝 활성 세션</h2>
{active_cards}        </div>

        <div class="dashboard">
            <h2>📊 현재 세션 상세</h2>

            <table class="dashboard-table">
                <thead>
                    <tr>
                        <th>항목</th>
                        <th>값</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>변경 파일</strong></td>
                        <td>{current_session['files_changed']}</td>
                    </tr>
                    <tr>
                        <td><strong>작업 저장소</strong></td>
                        <td>{''.join([f'<span class="repo-badge">{repo}</span>' for repo in current_session['repos']])}</td>
                    </tr>
                    <tr>
                        <td><strong>착수일</strong></td>
                        <td>{current_session['start_date']}</td>
                    </tr>
                    <tr>
                        <td><strong>완료일</strong></td>
                        <td>{current_session['end_date']}</td>
                    </tr>
                    <tr>
                        <td><strong>검증 결과</strong></td>
                        <td>{current_session['test_result']}</td>
                    </tr>
                    <tr>
                        <td><strong>권장 모델</strong></td>
                        <td>{current_session['model_rec']}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="sessions">
            <h2>🏆 최근 완료 세션</h2>
{completed_cards}        </div>

        <div class="footer">
            <p>📂 정본 저장소: <code>{HARNESS_PLANS_DIR}/current_work/archive/session_history/</code></p>
            <p>🔗 현재 세션: <code>CURRENT_SESSION.md</code> · 세션 인덱스: <code>SESSION_INDEX.md</code> · 마스터 플랜: <code>00_MASTER_PLAN.md</code></p>
            <p style="margin-top: 10px; opacity: 0.6;">⚙️ Gate 스킬 종료 시 자동 동기화</p>
        </div>
    </div>
</body>
</html>"""

    return html
