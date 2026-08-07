# Changelog

## [1.3.0] - 2026-08-07

### Added
- **`learning_path` 설정 필드 신설** (`skills/init/SKILL.md` 인터뷰 항목 + `harness-answers.yml` 템플릿) — 이해도 원장(`comprehension_ledger.md`)의 위치를 SSOT로 분리. 상대경로는 `CLAUDE_PROJECT_DIR` 기준 해석, 절대경로는 그대로 사용, **필드 부재 시 기존 기본값 `plans/learning`으로 간주**(하위 호환 — `plan_tier` 미기재를 `"2"`로 간주하는 것과 동일 패턴). 종전에는 원장 경로가 훅 코드와 스킬 문서에 하드코딩돼 있어, 워크스페이스 배치가 다른 프로젝트(예: `plans/`가 아닌 `plan/`)에서는 원장을 찾지 못했다.
- `install.sh` — 훅 배선 인터프리터 **OS 자동 분기**(`$OSTYPE` 감지 → Windows `py` / 그 외 `python3`, 11곳). Claude Code 훅은 로그인 셸을 거치지 않아 Git Bash의 `python3` shim을 신뢰할 수 없으므로 Windows에서 훅이 조용히 미동작할 수 있었다. 설치 스크립트 자신의 heredoc(`python3 - <<PYEOF`)은 설치 셸에서 실행되므로 그대로 유지.

### Fixed
- **훅 계층 Windows 이식 반영 (15파일)** — 배포본에 그동안의 Windows·인코딩 수리가 전혀 반영되지 않아, 설치 시 새 프로젝트가 이미 수정된 결함을 그대로 상속하는 상태였다. `"/tmp"` 하드코딩 **8파일 → 0건**(`tempfile.gettempdir()` 치환), `sys.stdout.reconfigure(encoding="utf-8")` **0 → 6파일**(Windows cp949 콘솔에서 `—`·`✅` 등 미지원 기호 출력 시 러너 크래시 — 하필 FAIL 분기 `print()`에만 있어 *테스트가 실패할 때만* 죽어 진짜 실패를 은폐하던 구조), `subprocess.run(..., encoding="utf-8")` 명시, `master-plan-stale-guard.py` 파서 2단 폴백.
- `hooks/comprehension-ledger-stale-guard.py` — 원장 경로 해석을 **3단 우선순위**(① `COMPREHENSION_LEDGER_PATH` env → ② `harness-answers.yml` `learning_path` → ③ 기본값)로 교체. 종전 `Path(_proj).parent / "plans" / ...`는 특정 워크스페이스의 형제 디렉터리 배치를 코드에 가정했고, env 부재 시 사설 절대경로로 폴백했다. **경로가 틀려도 fail-open 설계상 `exit 0`이라 조용히 오작동**했다(파일 부재와 만료 0건의 관측 결과가 동일).
- `hooks/skill-usage-auto.py`·`hooks/session_dashboard_renderer.py` — 사설 절대경로 폴백 제거(env 기반 교체). v1.2.1이 `session-dashboard-sync.py`에 적용한 것과 동종이나 누락됐던 2건.
- `sync-from-source.sh` — 훅 sanitize sed 규칙 보강. 기존 2줄이 **정확히 따옴표로 감싼 형태만** 매치해, 하위 경로 리터럴(`".../plans/process_evolution"`)과 `os.environ.get()`의 **기본 인자 자리**에 있는 경로가 규칙을 빠져나가 사설 경로가 릴리스에 실렸다. catch-all 규칙 추가 + **선행 처리 규칙**으로 치환 중첩 방지(규칙 간 순서 의존성을 주석에 명시). 치환 결과는 `os.path.join(...)` 형태로 **Python 구문 유효성을 유지**한다.
- `skills/gate-a/SKILL.md`·`skills/gate-b/SKILL.md` — 원장 경로 하드코딩 3곳을 `learning_path` SSOT 참조로 전환. 아울러 자동 감지 Stop 훅에 대한 서술에 **「배선돼 있을 때만 동작」 조건을 명시**(훅 축소 시 문서가 함께 갱신되지 않아 「동작한다」는 거짓 주장이 남았던 재발 경로 차단) + `gate-a`의 「planned」 스테일 서술을 구현 완료 사실로 정정.

### Note
- 스킬의 tier-aware 일반화 콘텐츠(플레이스홀더 91곳·`plan document(s)` 문구 36곳)는 **전량 보존** — 소스 저장소의 스킬은 프로젝트 고유형이고 배포본은 sed 변환을 거친 일반화 상위형이므로, 훅과 달리 **통짜 재동기화 시 역행**한다. 이번에도 원장 경로 3곳만 선택 이식했으며, 검증에서 91→91곳·36→36곳 보존을 확인했다. 스킬은 자동 역전파 불가 — **선택 이식이 정본 절차**.

## [1.2.1] - 2026-07-20

### Fixed
- **공개 스킬 파일 내부 참조 잔존 정리** — 1.2.0에서 `sync-from-source.sh`에 추가된 정화 규칙(SSOT 문서명 플레이스홀더 치환·내부 리서치 문서 인용 각주화)이 저장소 **기존** 스킬 콘텐츠에는 소급 적용된 적이 없어, 스킬 7종에 내부 리서치 문서 경로(`REPORTS/HARNESS_*.md`)·SSOT 원문 파일명·로컬 절대경로·구 브랜드명이 노출된 채 남아 있던 것을 일괄 정리(11파일 ±88줄 순수 치환 + 수동 잔존 3건: harness-update 로컬경로 1·init 구 브랜드명 2). 1.2.0의 tier-aware 일반화 콘텐츠는 전량 보존 — 소스 전체 재동기화(sync)는 tier-aware 콘텐츠를 역행시키므로 수행하지 않음(역방향 절차 설계는 소스 저장소 HARNESS-SYNC-RECONCILE-2 트랙).
- `hooks/session-dashboard-sync.py` — `PROJECT_ROOT` fallback의 사설 절대경로를 `CLAUDE_PROJECT_DIR` env 기반으로 교체(공개 저장소 이식성·경로 노출 제거). 훅 회귀 89 PASS / 0 FAIL.

### Note
- 소스 저장소 메타파일(`CHANGELOG.md`·`plugin.json`)을 본 릴리스 기준으로 역정합(backfill) — sync 실행 시 배포 저장소 릴리스 이력([1.2.0] 항목)이 삭제되던 재발 경로 차단.

## [1.2.0] - 2026-07-06

### Added
- **1-tier/2-tier plan-document structure support** (`plan_tier`) — `harness-answers.yml`에 `plan_tier`(`"1"`/`"2"`)·`master_plan_file`·`detail_plan_file`·`single_plan_file`·`single_plan_threshold` 5개 필드 신설. `/init` Step 1-c가 기존 2단 구조(서브플랫폼 상세계획 파일·§7 세션테이블) 존재 여부를 자동감지해 제안하고, Step 2 인터뷰에서 사용자가 확인/오버라이드. 단일 계획문서(`WORK_PLAN.md` 등)만 쓰는 프로젝트에 설치할 때마다 반복되던 수동 로컬라이즈 작업을 해소.
- **Gate D 검증 단계 code-review 에스컬레이션** (`gate-d/SKILL.md` §3-B, R-14) — Gate A의 R축 총점 ≥6 또는 변경파일 >7개일 때, 기존 인라인 7항목 자체점검 대신 `/code-review` Skill(다각도 finder + 독립 검증 에이전트)을 Gate C diff에 위임하도록 확장. `/code-review`는 하네스가 보증하지 않는 클라이언트 개별 capability이므로 가용성 체크 후 미가용 시 인라인 체크리스트로 자동 폴백(gate-e의 `/error-log` 미가용 대응 원칙과 동일).
- `skills/SKILL_DETAIL.md` `§Plan-Doc Update Pattern` 신설 — gate-a~e·audit·doc-cleanup 전역의 "계획 문서 갱신" tier-aware 공통 문구를 한 곳에 정의. `harness-answers.yml`에 `plan_tier` 필드가 없는 기존 저장소는 자동으로 `"2"`(기존 2단 동작)로 간주 — 하위 호환 보장.
- `install.sh` `NEW_HOOKS`에 누락됐던 6개 Stop 훅(`gate-a-sync-guard`·`gate-e-sync-guard`·`error-topics-guard`·`comprehension-ledger-stale-guard`·`test-tampering-guard`·`skill-usage-auto`) + PreToolUse `commit-msg-guard` 자동등록 추가 — README에는 문서화되어 있었으나 실제 설치 스크립트에는 등록되지 않던 버그 수정.
- `sync-from-source.sh`에 SSOT 문서명(`00_MASTER_PLAN.md`·`SESSION_INDEX.md`·`CURRENT_SESSION.md`) 플레이스홀더 자동치환 + 내부 리서치 문서(`REPORTS/HARNESS_*.md`) 인용 자동 각주화 sed 규칙 추가. 2단 구조·튜닝된 임계값·예시 저장소명 등 사람 판단이 필요한 잔존 패턴은 sync 후 경고로 표면화.

### Fixed
- `doc-cleanup/SKILL.md` Step 0-B/Step 3/V-D3 공식을 tier별로 파라미터화 (4문서 임계값 표 → 2단/1단 행 집합 분기), Step 5를 확장해 1단 프로젝트의 완료 Phase 본문 슬림화까지 흡수 (Step 3의 preserve/delete 판단표 재사용).
- gate-a Step 0-A·gate-a/b/c/d 최종출력 지침·gate-e 다수 지점에 남아있던 "3-document"/"3문서"/"§7" 고정 서술을 tier-aware 문구로 전환 (SKILL_DETAIL.md가 신설한 "고정 문서 개수 서술 금지" 규칙 위반 잔존분 포함).
- audit·doc-cleanup의 bash 측정 명령에 남아있던 미해결 결합 플레이스홀더(`<master_plan_file_or_single_plan_file>`)를 tier별 분리 실행 블록으로 교체 — 실행 시 "No such file" 오류가 나던 결함 수정.
- README 훅 목록에 `commit-msg-guard.py` 누락 보정 (영/한 양쪽), 훅 개수 10→11 갱신.

## [1.1.1] - 2026-07-06

### Fixed
- 배포 메타파일 버전 드리프트 수정 (HARNESS-VERSION-SYNC-1) — `.claude-plugin/plugin.json`(1.0.7 고정, 생성 커밋 이후 1.0.8/1.0.9/1.1.0 세 번 누락)·`.claude-plugin/marketplace.json`(1.0.8 고정, 1.0.9/1.1.0 두 번 누락)이 정본(루트 `plugin.json`·CHANGELOG 기준 1.1.0)보다 뒤처져 있던 것을 3파일 모두 1.1.1로 동기화. `deploy-plugin.yml`이 루트 `plugin.json`만 검증·릴리스 대상으로 삼고 `.claude-plugin/plugin.json`은 전혀 검사하지 않던 것이 반복 드리프트의 구조적 원인.

### Added
- `deploy-plugin.yml` `validate` job에 `.claude-plugin/plugin.json` 존재·JSON 유효성 검사 + 3파일(root `plugin.json`·`.claude-plugin/plugin.json`·`.claude-plugin/marketplace.json`) `version` 필드 상호일치 검증 스텝 추가 — 향후 릴리스에서 동일 드리프트 재발 시 CI가 즉시 fail.

## [1.1.0] - 2026-06-30

### Added
- `skills/init/SKILL.md` Step 1-b 컨텍스트 문서 디스커버리 — 코드 스캔(Step 1-a)과 분리하여 기획·PRD·사업계획 등 제품 의도 문서를 `/init` 시점에 수집 (`context_summary` 생성). 검색 위치: repo root + `docs/` + `docs/planning/` 등, 영문·한국어 파일명 패턴 지원. 토큰 폭발 방지 바운드(최대 ~5파일) 및 할루시네이션 가드(`<!-- verify -->` 마킹) 내장 (DOCBASE-CONTEXT-1).
- `skills/init/SKILL.md` Step 8-b 리네임 — 기존 "PRD discovery(재탐색)" → "Context incorporation(Step 1-b 재사용)". `context_summary`를 ARCHITECTURE.md `## Purpose / System Boundaries` 섹션 및 DATA_FLOW.md 도메인 엔티티/플로우에 주입. 재탐색 제거로 중복 파일 I/O 없음.
- `skills/init/SKILL.md` ARCHITECTURE.md 템플릿 `## Purpose / System Boundaries` 섹션 추가 — Step 8-b 주입 결과를 받는 플레이스홀더 포함.
- `session_dashboard_parsers.py` `gate_status`·`next_action` 파싱 — SESSION_INDEX.md YAML `gate:`·`next_action:` 필드를 읽어 8-tuple로 반환 (HARNESS-DASHBOARD-GATE-1).
- `session_dashboard_renderer.py` 헤더 메타 2칸 추가 — "Gate 상태"·"다음 행동" 조건부 표시(값 없는 구세션 무회귀).
- `session-dashboard-sync.py`·`test_session_dashboard_sync.py` 6→8-tuple 갱신 및 fixture·golden 재생성 — 전체 테스트 4/4·90/90 PASS.

## [1.0.9] - 2026-06-30

### Fixed
- `session_dashboard_parsers.py` 섹션명 정합 — `## 활성·예정 세션` → `## 현재 세션`, `## 최근 완료` → `## 최근 완료 세션` 패턴 수정 (HARNESS-RENDERER-PROJECT-FIX-1). SESSION_INDEX.md 실제 섹션명과 정규식 불일치로 활성세션이 빈 상태로 렌더링되던 버그 수정.
- `session_dashboard_parsers.py` 권장 모델 패턴 확장 — `Gate별 권장 모델` 외 `권장 모델` 필드명도 허용하여 구세션 호환성 확보.
- `session-dashboard-sync.py` 기본 경로 하드코딩 수정 — `CLAUDE_PROJECT_DIR` 폴백 중복(`or … or …` 동일값)을 `/media/ubuntu/data120g/ai-consulting-plans` 절대경로로 교체.

### Added
- 세션 대시보드 `project` 동적 반영 — `SESSION_INDEX.md` YAML `project:` 필드를 파싱하여 HTML `<title>`·`<h1>`에 프로젝트명을 삽입 (`session_dashboard_parsers.py` + `session_dashboard_renderer.py`). 필드 부재 시 하위호환 유지(빈 문자열 폴백).

### Removed
- `session_dashboard_renderer.py` footer `DOC_INDEX.md` 링크 제거 — 모든 저장소에 `DOC_INDEX.md`가 있지 않아 노이즈가 되던 항목 삭제.

## [1.0.8] - 2026-06-30

### Added
- Gate A~E 스킬에 Layer 2 문서 갱신 지시 추가 (DOCBASE-3+) — `/init --docs=full`로 생성된 Layer 2 문서 골격(FEATURE_SPEC·API_SPEC·TEST_PLAN·ERROR_HANDLING·DECISION_LOG)을 각 Gate가 실제로 채우도록 `gate-a~e/SKILL.md`에 `### Layer 2 document update` 절 삽입. `if file exists / else skip silently` 조건부로 brownfield·`--docs=minimal/none` 저장소에 무영향. 각 Gate의 책임 분리: Gate A→FEATURE_SPEC Overview/AC, Gate B→API_SPEC Endpoints(변경 시), Gate C→TEST_PLAN 테스트케이스, Gate D→TEST_PLAN 체크리스트+ERROR_HANDLING+DECISION_LOG ADR, Gate E→DOC_INDEX 최종 상태 확정.
- `harness-update/SKILL.md` Axis E 체크리스트 행 추가 — 배포본 동기화 시 Layer 2 문서 누락을 탐지할 수 있도록 Step 3 체크리스트에 `E | Layer 2 docs status` 행 추가(기존 A~D 보존). `DOC_INDEX.md` 존재·모든 행 `Skeleton` 이상 = PASS, 부재·`Pending` 잔존 = FAIL.

## [1.0.7] - 2026-06-29

### Removed
- `/comprehend-gate` 스킬 폐기 — 이해도 게이트가 Gate B(`/gate-b`)로 통합되어 단독 호출 use case 소멸 (HARNESS-COMPREHEND-REMOVE-1). comprehend-gate와 gate-b는 동일 Step 0~4 절차이고 gate-b가 더 완전(3문서 갱신·STOP 포함)·자립·통합 정본. `skills/comprehend-gate/` 삭제, `gate-a/SKILL.md`의 트리거 정본·선행 안내를 `gate-b/SKILL.md §Step 0`로 재지정, `comprehension-ledger-stale-guard.py`의 소문자 `comprehend-gate` 참조 4건 → `gate-b`(대문자 세션ID는 이력 보존). 훅 로직 불변(회귀 9/9·무회귀).

### Changed
- 플러그인 배포 문서 comprehend-gate 참조 정리 — `README.md`·`.claude-plugin/marketplace.json`·`install.sh`의 `/comprehend-gate` 안내 제거 + 이해도 게이트 = Gate B 일원화 표기 (`RELEASE_POLICY.md`의 v1.0.0 baseline 기록은 이력이므로 보존). `comprehension-ledger-stale-guard` 훅 설명은 gate-b 기준으로 갱신(훅 자체는 유지).

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
