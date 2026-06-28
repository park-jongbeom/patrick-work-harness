# Changelog

## [1.0.4] - 2026-06-28

### Fixed
- `test-tampering-guard.py` reward-hacking 검출기 복구 (HARNESS-TAMPER-FIX-1, 하네스 검증 HARNESS_VERIFICATION_V1 G1) — ① `git diff` 인자순서 버그(`tests/ --unified=0` → `--unified=0 -- tests/`; git 2.43이 rc=128로 거부해 Pattern A/B/C가 빈 diff로 사문화되던 것) 수정 ② git returncode 가드 추가(조용한 fail-open 제거) ③ staged(`--cached`) 변경도 검사(Gate C가 편집을 stage) ④ Pattern D(CI config) → `exit 2`(block) 분기 복원(docstring 0/1/2 계약). 전용 단위테스트 `test_test_tampering_guard.py` 신설(8 케이스, 회귀 95 PASS).

## [1.0.3] - 2026-06-28

### Removed
- `/doc-update` 스킬 폐기 — `/harness-update`로 통합. doc-update(좁음·HARNESS zone 전용) 기능은 harness-update Axis A(HARNESS zone reconcile) + `_engine_version` 갱신이 이미 포섭. harness-update/init/README의 doc-update 참조 정리

### Fixed
- 세션 대시보드 렌더러 footer 경로 `HARNESS_PLANS_DIR` 미정의 `NameError` 해소 — env 폴백 변수 정의(HARNESS-DASH-RENDER-FIX-1). `/init` 후 플러그인/배포본에서 대시보드가 silent 미생성되던 버그 수정

### Changed
- `/init` Step 6/7 플러그인 반영 — Stop hook 배선 + session-dashboard.html 1회 생성(INIT-COMPLETE-1, 소스 기반 전파)

---

## [1.0.2] - 2026-06-26

### Removed
- `/error-log` 스킬 폐기 — HARNESS-SELF-AUDIT-1(2026-05-28) 누적 사용 0회. Gate E 인라인 오류 기록으로 흡수됨
- `/export-roles` 스킬 폐기 — HARNESS-SELF-AUDIT-1 누적 사용 0회. 해당 기능 미사용 확인

---

## [1.0.1] - 2026-06-26

### Added
- `/harness-update` 스킬: 하네스 전체 업그레이드 (버전 확인 → CHANGELOG 표시 → 체크리스트 → 사용자 승인 → 일괄 갱신)
  - Axis A: CLAUDE.md HARNESS zone 갱신 (`/doc-update` 로직 재사용)
  - Axis B: Stop hook 3종 배선 자동 적용 (session-dashboard-sync → gate-e-sync-guard → error-topics-guard, prepend 방식으로 기존 항목 보존)
  - Axis C: session-dashboard.html 생성 (미존재 시)
  - Axis D: SESSION_INDEX.md / CURRENT_SESSION.md stub 생성 (session_docs: true 레포, 미존재 시)
- `/harness-update --check` 모드: 파일 쓰기 없이 체크리스트만 출력

### Changed
- `/doc-update`는 HARNESS zone 전용으로 유지; `/harness-update`가 전체 업그레이드 표준 경로로 지정

---

## [1.0.0] - 2026-06-24

### Added
- Gate A~E 프로세스 스킬 8종: `/gate-a`, `/gate-b`, `/gate-c`, `/gate-d`, `/gate-e`, `/doc-cleanup`, `/audit`, `/comprehend-gate`
- 훅 시스템: `master-plan-stale-guard`, `docker-command-guard`, `session-dashboard-sync`
- HARNESS-REVIEW-4 체인 (R-4-1~6) 완료: 유효성·무결성 검증 6종
- plugin.json v1.0.0 메타 완성 (keywords, homepage, repository, author)
- `.claude-plugin/marketplace.json` 완성 (category, tags, compatibility, skills 목록)
- `.github/workflows/deploy-plugin.yml` CI/CD 파이프라인 (tag push → validate → release)

### Fixed
- [HARNESS-REVIEW-4-6] 스킬 실패케이스 13건 검증 완료 (2026-06-21)
- [PLUGIN-TEST-1] harness-test-dummy E2E 검증 통과 (C1~C5 PASS, 2026-06-23)

### Changed
- 버전 v0.1.0 → v1.0.0 (마켓플레이스 첫 배포)

---

## [0.1.0] - 2026-06-15

### Initial
- 초기 plugin.json 메타 정의
- 7종 핵심 스킬 (gate-a~gate-e, doc-cleanup, audit)
- CLAUDE.md 기반 하네스 명세 완성
