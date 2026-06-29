# DATA_FLOW — patrick-work-harness

## Session Dashboard Pipeline

```
CURRENT_SESSION.md / SESSION_INDEX.md   (target repo)
  → session-dashboard-sync.py           (Stop hook — 항상 첫 번째)
      → session_dashboard_parsers.py    (parse_current_session, parse_session_index)
      → session_dashboard_renderer.py   (generate_html)
  → session-dashboard.html              (target repo root)
```

## Gate Guard Pipeline (PreToolUse)

```
Tool 호출 시도
  → claude-gate-guard.py  (PreToolUse)
      → CURRENT_SESSION.md 읽기 (Gate 상태 파싱)
      → Gate A 미승인 + 코드 편집 → exit 2 (차단)
      → Gate < D + 테스트 명령    → exit 2 (차단)
      → 허용 조건 → exit 0 (통과)
```

## HARNESS Zone Update Path

```
CLAUDE.md (HARNESS zone, target repo)
  → /harness-update skill
      → harness-answers.yml 읽기 (_engine_version 확인)
      → HARNESS:START…HARNESS:END 영역 덮어쓰기 (Axis A)
      → harness-answers.yml _engine_version bump
```

## Install Path

```
install.sh (--version / --target / --dry-run / SHA256 체크섬)
  → GitHub Releases tarball 다운로드
  → skills/ · hooks/ 압축 해제 → target repo
  → .claude/settings.json Stop hook 배선
```

## Layer 2 Document Fill Path (--docs=full)

```
/init --docs=full
  → Step 8: PROJECT_MAP.md · ARCHITECTURE.md · DATA_FLOW.md · DOC_INDEX.md 생성
  → Step 9: FEATURE_SPEC.md · API_SPEC.md · TEST_PLAN.md · ERROR_HANDLING.md · DECISION_LOG.md 골격 생성
             DOC_INDEX.md Layer 2 행 Pending → Skeleton

Gate A 실행
  → FEATURE_SPEC.md ## Overview / ## Acceptance Criteria 마커 채움
  → DOC_INDEX.md FEATURE_SPEC 행 Skeleton → Partial

Gate B 실행 (엔드포인트 변경 세션만)
  → API_SPEC.md ## Endpoints Changed 마커 채움

Gate C 실행
  → TEST_PLAN.md ## Test Cases 마커 채움

Gate D 실행
  → TEST_PLAN.md ## Verification Checklist 마커 채움
  → ERROR_HANDLING.md ## Failure Paths / ## Recovery Strategies (실패 시)
  → DECISION_LOG.md ADR 항목 추가 (비자명 결정 시)

Gate E 실행
  → DOC_INDEX.md 최종 상태 확정 (Partial → Complete)
```

<!-- PRD not found — fill in manually -->
