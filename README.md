# patrick-work-harness

[English](#english) | [한국어](#한국어)

---

## English

A process automation harness for Claude Code.  
Provides the **Gate A~E 5-step process** and **Stop hook quality guards** as slash commands.

### What is this?

Solves the most common problems that arise when using AI coding tools (Claude Code).

| Problem | Harness solution |
|---------|-----------------|
| Code changes without a plan | Gate A — pre-approve files · steps · scope before any edit |
| Verification closed by AI self-judgment | Gate C — closes only on external execution signals (test PASS/FAIL) |
| Tests disabled to fake a pass | `test-tampering-guard` Stop hook detects reward-hacking in real time |
| Completion records scattered and untraceable | Gate E — auto-generates WORKLOG + archive |
| Documents go stale every session | 5 guard hooks including `master-plan-stale-guard` |
| Re-explaining the same concept every session | `comprehend-gate` — expiring evidence ledger |

#### Process flow

```
/gate-a  →  user approval  →  /gate-b  →  /gate-c  →  (/gate-d)  →  /gate-e
  plan            ↑             implement    verify      refactor      record
            no code change
```

---

### Skills (slash commands)

| Command | Role |
|---------|------|
| `/gate-a` | Build a change plan — inspect files · steps · scope, then wait for approval |
| `/gate-b` | Implement code — follow the Gate A plan exactly, then wait for confirmation |
| `/gate-c` | Verify — external-signal-based loop · classify FIX-B / DEP |
| `/gate-d` | Refactor — code quality improvement (conditional, after Gate C) |
| `/gate-e` | Session wrap-up — create WORKLOG · archive · flip 3 docs to ✅E |
| `/audit` | Direction check — 10-item review: priority · Gate process · doc sync |
| `/doc-cleanup` | Slim documents — migrate completed sessions to archive |
| `/doc-update` | Update HARNESS zone — `_engine_version` + HARNESS section refresh |
| `/harness-update` | Full upgrade — compare version → show CHANGELOG → 4-axis checklist → approve → batch update |
| `/init` | Initialize new project — create sentinel zones · stubs · wire hooks |
| `/comprehend-gate` | Comprehension gate — risk-based self-explanation check · expiring ledger |
| `/error-log` | Record errors — accumulate recurrence-prevention rules into topic files |
| `/export-roles` | Sync config — rsync `ai_claude` source of truth to other repositories |

---

### Hooks

Stop hooks and PreToolUse hooks run automatically before/after each Claude Code response.

| File | Type | Role |
|------|------|------|
| `master-plan-stale-guard.py` | Stop | Detects mismatch between `00_MASTER_PLAN.md` L7 session ID and `CURRENT_SESSION.md` |
| `gate-a-sync-guard.py` | Stop | Detects missing required fields (e.g. `작업 의도`) while Gate A approval is pending |
| `gate-e-sync-guard.py` | Stop | Detects ✅E inconsistency between `SESSION_INDEX.md` and `CURRENT_SESSION.md` after Gate E |
| `error-topics-guard.py` | Stop | Detects missing error records after Gate E |
| `test-tampering-guard.py` | Stop | Detects reward-hacking patterns during Gate B→C transition (4 types: `@Disabled` · reduced assertions · mock reduction · CI tampering) |
| `comprehension-ledger-stale-guard.py` | Stop | Detects expired comprehend-gate evidence ledger entries |
| `session-dashboard-sync.py` | Stop | Auto-regenerates `session-dashboard.html` |
| `skill-usage-auto.py` | Stop | Auto-records skill usage history markers |
| `docker-command-guard.py` | PreToolUse | Blocks invalid Docker commands (`-it`, wrong container names, etc.) |
| `claude-gate-guard.py` | PreToolUse | Blocks code change attempts before Gate A approval |

---

### Installation

#### Method 1 — install.sh (recommended)

```bash
# Install latest release into the current project
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash

# Pin a specific version
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --version v1.0.1

# Specify install path
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --target /path/to/your/project
```

Files created after installation:

```
your-project/
└── .claude/
    └── skills/          ← 13 slash commands
        ├── gate-a/
        ├── gate-b/
        ├── ...
        └── harness-update/
~/.claude/
└── hooks/
    └── patrick-work-harness/   ← 10 hook files
        ├── master-plan-stale-guard.py
        ├── gate-e-sync-guard.py
        └── ...
```

#### Method 2 — Initialize with /init (if already installed)

To add HARNESS zones to an existing project:

```
/init
```

Creates `CLAUDE.md` sentinel zones · `SESSION_INDEX.md` · `CURRENT_SESSION.md` stubs · wires 3 Stop hooks in one go.

#### Method 3 — Manual install

```bash
git clone https://github.com/park-jongbeom/patrick-work-harness.git
cd patrick-work-harness

# Copy skills
cp -r skills/ /your-project/.claude/skills/

# Copy hooks
mkdir -p ~/.claude/hooks/patrick-work-harness
cp hooks/*.py ~/.claude/hooks/patrick-work-harness/
```

Then register hooks manually in Claude Code `settings.json` or run the `/init` skill.

---

### Usage

#### Starting a session — Gate A (plan)

When starting new work:

```
/gate-a
```

Claude Code automatically reads `00_MASTER_PLAN.md` · `SESSION_INDEX.md` · `CURRENT_SESSION.md` and builds a change plan.  
**No code changes happen until the user approves.**

How to approve:
```
Gate A 승인
```
or
```
계획대로 구현
```

#### Gate B → C → E (implement · verify · record)

```
/gate-b   ← implement (exactly per Gate A plan)
/gate-c   ← verify (external execution signal loop)
/gate-e   ← session wrap-up (WORKLOG + archive)
```

Simple work: A→B→C→E. Complex work: A→B→C→D→E.

#### Direction check — /audit

Every 3 sessions or at a chain transition:

```
/audit
```

Reviews 10 items including priority alignment · Gate process · document sync, and reports WARN/FAIL.

#### Upgrade the harness — /harness-update

```
/harness-update
```

Compares the current `_engine_version` with the latest, shows the CHANGELOG, and batch-updates all 4 axes after user approval.

```
/harness-update --check   ← checklist only, no file changes
```

---

### Changelog

#### [1.0.1] — 2026-06-26

**Added**
- `/harness-update` skill: standard upgrade path (version compare → CHANGELOG → 4-axis checklist → approve → batch update → `_engine_version` bump)
- `/harness-update --check` mode: read-only checklist output

**Changed**
- `/doc-update` scoped to HARNESS zone only; full upgrades use `/harness-update`

---

#### [1.0.0] — 2026-06-24

**Added**
- 8 Gate A~E process skills (`/gate-a` ~ `/gate-e`, `/doc-cleanup`, `/audit`, `/comprehend-gate`)
- `/harness-update`, `/init`, `/doc-update`, `/error-log`, `/export-roles` skills
- Hook system: `master-plan-stale-guard`, `docker-command-guard`, `gate-e-sync-guard`, `test-tampering-guard`, `comprehension-ledger-stale-guard` + 5 more
- `plugin.json` v1.0.0 metadata
- `install.sh` automated installer
- `.github/workflows/deploy-plugin.yml` CI/CD pipeline

**Fixed**
- 13 skill failure cases verified (HARNESS-REVIEW-4-R-4-6, 2026-06-21)
- Plugin E2E verification passed (PLUGIN-TEST-1, C1~C5 PASS, 2026-06-23)

---

#### [0.1.0] — 2026-06-15

**Initial**
- Initial `plugin.json` metadata definition
- 7 core skills (`/gate-a` ~ `/gate-e`, `/doc-cleanup`, `/audit`)
- `CLAUDE.md`-based harness specification

---

### License

MIT

---

## 한국어

Claude Code 기반 소프트웨어 개발 프로세스 자동화 하네스입니다.  
**Gate A~E 5단계 프로세스**와 **Stop hook 품질 가드**를 슬래시 커맨드로 제공합니다.

### 이 도구는?

AI 코딩 도구(Claude Code)를 사용할 때 발생하는 공통 문제를 구조적으로 해결합니다.

| 문제 | 하네스의 해결 |
|------|--------------|
| 계획 없이 바로 코드 변경 | Gate A — 변경 파일·Step·범위 사전 승인 |
| 검증을 AI 자기 판단으로 종료 | Gate C — 외부 실행 신호(테스트 PASS/FAIL)로만 닫힘 |
| 테스트를 무력화해 통과 위장 | `test-tampering-guard` Stop hook 실시간 감지 |
| 완료 기록이 흩어져 추적 불가 | Gate E — WORKLOG + archive 자동 생성 |
| 문서가 세션마다 스테일 | `master-plan-stale-guard` 등 5종 가드 훅 |
| 같은 기술 이해도 재질문 반복 | `comprehend-gate` 만료형 증적 원장 |

#### 프로세스 흐름

```
/gate-a  →  사용자 승인  →  /gate-b  →  /gate-c  →  (/gate-d)  →  /gate-e
  계획           ↑              구현         검증         리팩터        기록
             변경 없음
```

---

### 스킬 (슬래시 커맨드)

| 커맨드 | 역할 |
|--------|------|
| `/gate-a` | 변경 계획 수립 — 파일·Step·범위 점검·승인 대기 |
| `/gate-b` | 코드 구현 — Gate A 계획 그대로 구현 후 확인 대기 |
| `/gate-c` | 검증 — 외부 실행 신호 기반 반복 루프·FIX-B/DEP 분류 |
| `/gate-d` | 리팩터 — 코드 품질 개선 (조건부, Gate C 후) |
| `/gate-e` | 세션 정리 — WORKLOG·archive 생성·3문서 ✅E 갱신 |
| `/audit` | 방향성 점검 — 우선순위·Gate 프로세스·문서 동기화 10항목 |
| `/doc-cleanup` | 문서 슬림화 — 완료 세션 archive 이관·임계값 초과 정리 |
| `/doc-update` | HARNESS zone 갱신 — `_engine_version` + HARNESS 구역 최신화 |
| `/harness-update` | 전체 업그레이드 — 버전 비교→CHANGELOG 표시→4 axis 체크리스트→승인→일괄 갱신 |
| `/init` | 신규 프로젝트 초기화 — sentinel 2구역·stub 생성·hook 배선 |
| `/comprehend-gate` | 이해도 게이트 — 위험 기반 자기설명 검증·만료형 ledger |
| `/error-log` | 오류 기록 — 재발 방지 규칙을 topic 파일에 누적 |
| `/export-roles` | 설정 동기화 — `ai_claude` 정본을 타 저장소에 rsync |

---

### 훅 목록

Stop hook과 PreToolUse hook이 Claude Code 응답 전후에 자동 실행됩니다.

| 파일 | 종류 | 역할 |
|------|------|------|
| `master-plan-stale-guard.py` | Stop | `00_MASTER_PLAN.md` L7 세션 ID ↔ `CURRENT_SESSION.md` 불일치 감지 |
| `gate-a-sync-guard.py` | Stop | Gate A 승인 대기 시 필수 필드(`작업 의도` 등) 누락 감지 |
| `gate-e-sync-guard.py` | Stop | Gate E 후 `SESSION_INDEX.md` ↔ `CURRENT_SESSION.md` ✅E 불일치 감지 |
| `error-topics-guard.py` | Stop | Gate E 오류 기록 누락 감지 |
| `test-tampering-guard.py` | Stop | Gate B→C 전환 시 reward-hacking 패턴 감지 (4종: `@Disabled`·단언 감소·mock 축소·CI 변조) |
| `comprehension-ledger-stale-guard.py` | Stop | comprehend-gate 증적 원장 만료 감지 |
| `session-dashboard-sync.py` | Stop | `session-dashboard.html` 자동 재생성 |
| `skill-usage-auto.py` | Stop | 스킬 사용 이력 자동 마커 기록 |
| `docker-command-guard.py` | PreToolUse | 잘못된 Docker 명령 실행 차단 (`-it`, 잘못된 컨테이너명 등) |
| `claude-gate-guard.py` | PreToolUse | Gate A 승인 없이 코드 변경 시도 차단 |

---

### 설치

#### 방법 1 — install.sh (권장)

```bash
# 최신 릴리즈를 현재 프로젝트에 설치
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash

# 특정 버전 지정
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --version v1.0.1

# 설치 경로 지정
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --target /path/to/your/project
```

설치 후 생성되는 파일:

```
your-project/
└── .claude/
    └── skills/          ← 슬래시 커맨드 13종
        ├── gate-a/
        ├── gate-b/
        ├── ...
        └── harness-update/
~/.claude/
└── hooks/
    └── patrick-work-harness/   ← 훅 파일 10종
        ├── master-plan-stale-guard.py
        ├── gate-e-sync-guard.py
        └── ...
```

#### 방법 2 — /init 스킬로 초기화 (이미 설치된 경우)

기존 프로젝트에 HARNESS zone을 추가할 때:

```
/init
```

`CLAUDE.md` sentinel 2구역·`SESSION_INDEX.md`·`CURRENT_SESSION.md` stub·Stop hook 3종 배선을 일괄 생성합니다.

#### 방법 3 — 수동 설치

```bash
git clone https://github.com/park-jongbeom/patrick-work-harness.git
cd patrick-work-harness

# 스킬 복사
cp -r skills/ /your-project/.claude/skills/

# 훅 복사
mkdir -p ~/.claude/hooks/patrick-work-harness
cp hooks/*.py ~/.claude/hooks/patrick-work-harness/
```

이후 Claude Code `settings.json`에 훅을 수동 등록하거나 `/init` 스킬을 실행합니다.

---

### 사용법

#### 세션 시작 — Gate A (계획)

새 작업을 시작할 때:

```
/gate-a
```

Claude Code가 자동으로 `00_MASTER_PLAN.md`·`SESSION_INDEX.md`·`CURRENT_SESSION.md`를 읽고 변경 계획을 수립합니다.  
**코드 변경은 사용자 승인 전까지 일어나지 않습니다.**

승인 방법:
```
Gate A 승인
```
또는
```
계획대로 구현
```

#### Gate B → C → E (구현·검증·기록)

```
/gate-b   ← 구현 (Gate A 계획 그대로)
/gate-c   ← 검증 (외부 실행 신호 기반 루프)
/gate-e   ← 세션 정리 (WORKLOG + archive)
```

단순 작업은 A→B→C→E, 복잡한 작업은 A→B→C→D→E 경로를 따릅니다.

#### 방향성 점검 — /audit

3세션마다 또는 체인 전환 시:

```
/audit
```

우선순위 정합·Gate 프로세스·문서 동기화 등 10항목을 점검하고 WARN/FAIL을 리포트합니다.

#### 하네스 업그레이드 — /harness-update

```
/harness-update
```

현재 `_engine_version`과 최신 버전을 비교해 CHANGELOG를 보여주고, 사용자 승인 후 4 axis를 일괄 갱신합니다.

```
/harness-update --check   ← 파일 변경 없이 체크리스트만 확인
```

---

### 업데이트 이력

#### [1.0.1] — 2026-06-26

**추가**
- `/harness-update` 스킬 신설: 전체 업그레이드 표준 경로 (버전 비교 → CHANGELOG → 4 axis 체크리스트 → 승인 → 일괄 갱신 → `_engine_version` 갱신)
- `/harness-update --check` 모드: 읽기 전용 체크리스트 출력

**변경**
- `/doc-update`는 HARNESS zone 전용으로 역할 분리; 전체 업그레이드는 `/harness-update` 사용

---

#### [1.0.0] — 2026-06-24

**추가**
- Gate A~E 프로세스 스킬 8종 (`/gate-a` ~ `/gate-e`, `/doc-cleanup`, `/audit`, `/comprehend-gate`)
- `/harness-update`, `/init`, `/doc-update`, `/error-log`, `/export-roles` 스킬 추가
- 훅 시스템: `master-plan-stale-guard`, `docker-command-guard`, `gate-e-sync-guard`, `test-tampering-guard`, `comprehension-ledger-stale-guard` 외 5종
- `plugin.json` v1.0.0 메타 완성
- `install.sh` 자동 설치 스크립트
- `.github/workflows/deploy-plugin.yml` CI/CD 파이프라인

**수정**
- 스킬 실패케이스 13건 검증 완료 (HARNESS-REVIEW-4-R-4-6, 2026-06-21)
- 플러그인화 E2E 검증 통과 (PLUGIN-TEST-1, C1~C5 PASS, 2026-06-23)

---

#### [0.1.0] — 2026-06-15

**초기 릴리즈**
- 초기 `plugin.json` 메타 정의
- 핵심 스킬 7종 (`/gate-a` ~ `/gate-e`, `/doc-cleanup`, `/audit`)
- `CLAUDE.md` 기반 하네스 명세 완성

---

### 라이선스

MIT
