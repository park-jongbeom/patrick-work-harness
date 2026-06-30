#!/usr/bin/env python3
"""
세션 대시보드 HTML 자동 동기화 스크립트
Gate A~E 스킬 종료 시 CURRENT_SESSION.md/SESSION_INDEX.md를 읽어
session-dashboard.html을 자동 갱신한다.

HSA-2(2026-05-28): 819줄 → 진입점(read_markdown·main)만 보존하는
얇은 진입점으로 슬림화. 파싱·렌더링은 동일 디렉토리의
`session_dashboard_parsers.py`·`session_dashboard_renderer.py`로 분리.
파일명·경로는 Stop hook 호환을 위해 불변.
"""

import os
import sys
from pathlib import Path

# 동일 디렉토리 모듈 import 보장 (Stop hook 실행 시 cwd가 hook 디렉토리가 아닐 수 있음)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_dashboard_parsers import parse_current_session, parse_session_index  # noqa: E402
from session_dashboard_renderer import generate_html  # noqa: E402

# R-4-2-b: 3단 우선순위 (① custom env[테스트] → ② CLAUDE_PROJECT_DIR 파생 → ③ 절대경로 폴백)
#   error-topics-guard.py:38-43·gate-e-sync-guard.py:39-44와 동일 패턴 (정본 재사용)
PROJECT_ROOT = Path(
    os.environ.get("DASHBOARD_SYNC_BASE")
    or os.environ.get("CLAUDE_PROJECT_DIR")
    or "/media/ubuntu/data120g/ai-consulting-plans"
)
CURRENT_SESSION_FILE = PROJECT_ROOT / "CURRENT_SESSION.md"
SESSION_INDEX_FILE = PROJECT_ROOT / "SESSION_INDEX.md"
OUTPUT_HTML = PROJECT_ROOT / "session-dashboard.html"


def read_markdown(file_path):
    """마크다운 파일 읽기"""
    if not file_path.exists():
        return ""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    """메인 함수"""
    try:
        # 파일 읽기
        current_content = read_markdown(CURRENT_SESSION_FILE)
        index_content = read_markdown(SESSION_INDEX_FILE)

        if not current_content or not index_content:
            print(
                "⚠️  CURRENT_SESSION.md 또는 SESSION_INDEX.md를 찾을 수 없습니다.",
                file=sys.stderr,
            )
            return

        # 데이터 파싱
        current_session = parse_current_session(current_content)
        (
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
            project,
            gate_status,
            next_action,
        ) = parse_session_index(index_content)

        # HTML 생성
        html_content = generate_html(
            current_session,
            sessions,
            last_updated,
            current_title,
            priority_note,
            last_completed_title,
            project,
            gate_status,
            next_action,
        )

        # 파일 저장
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"✅ session-dashboard.html 동기화 완료 ({OUTPUT_HTML})")

    except Exception as e:
        print(
            f"❌ session-dashboard.html 동기화 실패: {e}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
