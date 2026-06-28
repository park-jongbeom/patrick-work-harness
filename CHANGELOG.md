# Changelog

## [1.0.6] - 2026-06-28

### Removed
- Cursor 전용 규칙·훅 제거 (HARNESS-CURSOR-REMOVE-1) — Claude Code 단독 사용으로 전환. `gate-guard.py`(Cursor Agent Hook)·`test_gate_guard.py` 삭제, `CLAUDE.md`의 Cursor 안내 참조 제거, `claude-gate-guard.py`의 Cursor 코스메틱(주석·`.cursor/` exempt) 정리. claude-gate-guard 차단 로직 불변(회귀 95 PASS).

### Changed
- README 변경로그 섹션 제거 — 버전 이력은 `CHANGELOG.md`·GitHub Releases(커밋 이력 기반)가 정본. README 비대화 방지를 위해 중복 기재 중단.

### Fixed
- `claude-gate-guard.py` false-positive 핫픽스 — `is_gate_a_blocked` 폴백 정규식(`Gate\s*A.*승인\s*대기`)이 ✅E 완료 세션 본문에 남은 "Gate A 계획(승인 대기)" 블록 텍스트에 오탐해 비면제 편집을 잘못 차단하던 것을, 폴백을 "파서가 게이트 판정 실패(gate=None)일 때만" 적용하도록 수정. v1.0.5(실파일 읽기 활성화) 후 첫 비면제 편집에서 노출. 회귀 테스트 추가(✅E+Gate A 본문→비차단).

## [1.0.5] - 2026-06-28

### Fixed
- `claude-gate-guard.py` (+ Cursor `gate-guard.py` 쌍둥이) Gate 강제 백스톱의 **실파일 fail-open 복구** (HARNESS-GATEGUARD-FIX-1 · 하네스 검증 HARNESS_VERIFICATION_V1 P1)
  - ① `find_session_file`이 stale `plans/current_work/` 대신 **리포 루트 `{repo}/CURRENT_SESSION.md` 우선** 탐색 (그동안 엉뚱한 stale 파일을 읽던 것 교정)
  - ② `parse_gate_status`가 실 표 포맷(`| 현재 Gate | **A (승인 대기)** |`, `| Gate 진행 | A✅ → C⏸ … |` 글자선행) 인식 — 구 헤더 포맷 하위호환 유지
  - 효과: Gate A 미승인 코드편집·Gate<D 테스트명령이 차단 안 되던 것(EXIT 0)을 차단(EXIT 2)으로 복구. 전용 단위테스트 `test_claude_gate_guard.py` 신설 + `test_gate_guard.py` 실 포맷 갱신 (회귀 107 PASS).

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
