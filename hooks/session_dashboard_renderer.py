"""세션 대시보드 HTML 렌더링 모듈

`parse_current_session`·`parse_session_index` 결과를 받아 단일 HTML
문서를 생성한다. HSA-2(2026-05-28)에서 `session-dashboard-sync.py`로부터
분리: 진입점은 파일명 불변 강제, 렌더링 책임만 본 모듈로 이동.

HSA-2-b(2026-05-28): CSS 393줄을 `dashboard.css` 외부 파일로 추출하고
`_load_css()`로 빌드 시 인라인 삽입 — HTML 출력은 self-contained 유지
(byte 동등성 보존) + 본 모듈 줄 수는 KPI ≤ 250 충족.
"""

import os
from datetime import datetime
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_CSS_PATH = _HOOKS_DIR / "dashboard.css"

# 정본 저장소(아카이브) 경로 — env 폴백(skill-usage-auto.py 동일 변수 규약 재사용).
# 미설정 시 본가 절대경로 폴백 → 정본 footer byte-equivalent + plugin sync 시 정의 동반(NameError 해소).
HARNESS_PLANS_DIR = os.environ.get("HARNESS_PLANS_DIR", "/media/ubuntu/data120g/plans")


def _load_css():
    """`dashboard.css` 읽기 — Stop hook 실행 cwd와 무관한 절대 경로."""
    return _CSS_PATH.read_text(encoding="utf-8")


def generate_html(
    current_session,
    sessions,
    last_updated,
    current_title,
    priority_note,
    last_completed_title,
):
    """HTML 생성"""
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

    # HTML 템플릿
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>세션 대시보드 — Go Almond AI 유학 상담</title>
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
            <h1>🎓 Go Almond AI 유학 상담 — 세션 대시보드</h1>

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
            </div>
        </header>

        <div class="sessions">
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
