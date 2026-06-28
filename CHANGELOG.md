# Changelog

## [1.0.2] - 2026-06-26

### Removed
- `/error-log` 스킬 폐기 — HARNESS-SELF-AUDIT-1(2026-05-28) 누적 사용 0회. Gate E 인라인 오류 기록으로 흡수됨
- `/export-roles` 스킬 폐기 — HARNESS-SELF-AUDIT-1 누적 사용 0회. 해당 기능 미사용 확인

---

## [1.0.1] - 2026-06-26

### Added
- `README.md` 신규 작성 — 영/한 이중 언어 (앵커 링크 전환), 459줄
  - 소개·스킬 13종·훅 10종·설치 3방법·사용법·업데이트 이력
- `/harness-update` 스킬 신설: 전체 업그레이드 표준 경로 (버전 비교 → CHANGELOG → 4 axis 체크리스트 → 승인 → 일괄 갱신 → `_engine_version` 갱신)
- `/harness-update --check` 모드: 읽기 전용 체크리스트 출력

### Changed
- `/doc-update`는 HARNESS zone 전용으로 역할 분리; 전체 업그레이드는 `/harness-update` 사용

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
