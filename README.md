# patrick-work-harness

[English](#english) | [한국어](#한국어)

---

## English

A process automation harness for Claude Code.  
Prevents the most common failure mode: **AI writing code before a plan is approved.**  
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
| Re-explaining the same concept every session | Gate B (comprehension gate) — expiring evidence ledger |

#### Process flow

```
/gate-a  →  user approval  →  /gate-b  →  /gate-c  →  /gate-d  →  /gate-e
  plan            ↑            comprehend  implement    verify      record
            no code change
```

Gate D is never skipped. Saying 「C~E 일괄」 (or 「D~E 일괄」) runs C → D → E without stopping in between, except for
high-risk sessions (security, migrations, public API, irreversible or cross-repo work) and whenever verification fails —
see `skills/gate-c/SKILL.md` §Batch runs.

**Two lanes (off by default).** Gate A also routes each plan. Anything that touches security, schema or stored data,
dependencies, tests or CI, a public contract or more than one module — or is simply ambiguous — takes the review lane above.
A small plan with an acceptance command and no trigger may take the **autonomous lane**: after 「자율 레인 승인」 it runs
C → D → E without stops, `lane-scope-guard.py` checks the real diff against the plan, and you judge one review card at the
end. Opt in per project — see Usage below and `skills/gate-a/SKILL.md` §0-Lane.

| Gate | Role | Description |
|------|------|-------------|
| A | **Plan** | Per-file change plan — scope, steps, risks. No code until approved. |
| B | **Comprehend** | Comprehension gate — free-form flow explanation, expiring evidence ledger. Pass-through for trivial work. |
| C | **Implement** | Code implementation — follow Gate A plan exactly. Closes on external signals only (test PASS/FAIL). |
| D | **Verify** | Test plan · execution · failure classification, and the code-review/security pass. Fills the `## Verification Checklist` marker Gate C leaves. |
| E | **Record** | WORKLOG + long-form archive. Flip all 3 docs to ✅E. |

#### Inspiration & Attribution

This harness incorporates the **minimalism ladder** decision framework from the open-source project [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT License, ~48k★).

The ladder philosophy: **"The best code is the code you never wrote."**

When planning features or changes (Gate A), the harness checks 7 rungs top-down before writing new code:
1. Does it need to exist? → skip (YAGNI)
2. Already in codebase? → reuse
3. Stdlib does it? → use stdlib
4. Native platform feature? → use native
5. Installed dependency? → use dependency
6. One line? → one line
7. Only then → write the minimum that works

The ladder is applied at every Gate A via the `0-Ladder` check step — each new file, method, or abstraction in the plan must justify which rung it stops at before implementation begins.

> **License notice**: The minimalism ladder concept is from `DietrichGebert/ponytail`, used under the MIT License. This harness is itself MIT-licensed (see [License](#license) below).

---

### Skills (slash commands)

| Command | Role |
|---------|------|
| `/gate-a` | Build a change plan — inspect files · steps · scope, then wait for approval |
| `/gate-b` | Comprehension gate — explain the flow in your own words; evidence ledger with expiry |
| `/gate-c` | Implement code — follow the Gate A plan exactly, then wait for confirmation |
| `/gate-d` | Verify — test plan · execution · failure classification (FIX-B / DEP) · code review |
| `/gate-e` | Session wrap-up — create WORKLOG · archive · flip 3 docs to ✅E |
| `/audit` | Direction check — 10-item review: priority · Gate process · doc sync |
| `/doc-cleanup` | Slim documents — migrate completed sessions to archive |
| `/harness-update` | Full upgrade — compare version → show CHANGELOG → 6-axis checklist → approve → batch update (HARNESS zone reconcile is Axis A) |
| `/init` | Initialize new project — create sentinel zones · stubs · wire hooks |

---

### Hooks

Hooks run automatically around each Claude Code response and tool call (Stop, PreToolUse, PostToolUse, UserPromptExpansion).

| File | Type | Role |
|------|------|------|
| `master-plan-stale-guard.py` | Stop | Detects mismatch between `00_MASTER_PLAN.md` L7 session ID and `CURRENT_SESSION.md` |
| `gate-a-sync-guard.py` | Stop | Detects missing required fields (e.g. `작업 의도`) while Gate A approval is pending |
| `gate-e-sync-guard.py` | Stop | Detects ✅E inconsistency between `SESSION_INDEX.md` and `CURRENT_SESSION.md` after Gate E |
| `error-topics-guard.py` | Stop | Detects missing error records after Gate E |
| `test-tampering-guard.py` | Stop | Detects reward-hacking patterns at the end of every response (4 types: `@Disabled` · reduced assertions · mock reduction · CI tampering) in uncommitted test files and — once per session, as a warning — in commits made during the session |
| `comprehension-ledger-stale-guard.py` | Stop | Detects expired comprehension-gate (Gate B) evidence ledger entries |
| `session-dashboard-sync.py` | PostToolUse | Auto-regenerates `session-dashboard.html` after each Edit/Write |
| `skill-usage-auto.py` | Stop | Auto-records skill usage history markers |
| `docker-command-guard.py` | PreToolUse | Blocks invalid Docker commands (`-it`, wrong container names, etc.) |
| `commit-msg-guard.py` | PreToolUse | Validates `git commit -m` messages against Korean Conventional Commits format |
| `test-write-guard.py` | PreToolUse | During Gate D, asks before any edit to a test file — no passing by weakening tests |
| `comprehension-pending-guard.py` | PreToolUse · UserPromptExpansion | Blocks `/gate-c`·`d`·`e` while a comprehension question still awaits an answer |
| `lane-scope-guard.py` | PreToolUse · UserPromptExpansion | Autonomous-lane sessions only: asks before writing a protected path; at Gate E compares the real diff with the plan and stops the session on any breach (fail-closed) |

> **Design note — the harness does not block edits before Gate A approval (2026-09-23).**
> A `claude-gate-guard.py` used to sit on PreToolUse and refuse edits while a session
> was still in Gate A. It was removed rather than repaired, because it exempted
> `.claude/`, `.github/`, `CURRENT_SESSION` and **every `.md` file**, and branched only
> on `tool_name == "Bash"` — so PowerShell calls passed unjudged. What it actually
> caught was close to nothing, while any real tightening would have blocked the
> harness from editing itself and raised the cost of a false positive (a guard with
> 22 false positives and 0 true positives was already removed on 2026-07-27).
>
> Gate order is therefore held by **procedure (the gate skills) and Stop-time checks**,
> not by pre-emptive blocking. `gate-a-sync-guard` still refuses to let a response end
> while Gate A is in progress and the session document is missing required fields.
> "No code before approval" is a rule the operator follows, not one the tooling enforces.

---

### Installation

#### Method 1 — Claude Code Marketplace (easiest)

Claude Code 커뮤니티 마켓플레이스에서 직접 설치:

```
/plugin marketplace add park-jongbeom/patrick-work-harness
/plugin install patrick-work-harness
```

Skills **and hooks** are both registered. Hooks come from the plugin's own
`hooks/hooks.json`, which resolves paths via `${CLAUDE_PLUGIN_ROOT}` — so this
method **does not touch your global `~/.claude/settings.json`**.

> Before v1.4.0 that file did not exist, so a marketplace install registered
> **zero hooks** while appearing to succeed.

#### Method 2 — install.sh (recommended)

```bash
# Install latest release into the current project
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash

# Pin a specific version
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --version v1.0.1

# Specify install path
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --target /path/to/your/project

# Install from a local checkout instead of downloading a release (offline, testing)
./install.sh --source /path/to/patrick-work-harness --target /path/to/your/project
```

`install.sh` rewrites the `${CLAUDE_PLUGIN_ROOT}/hooks/` paths inside the copied skills to the installed hooks folder
(`~/.claude/hooks/patrick-work-harness/`). Claude Code fills that variable in only for plugin skills; in a skill copied into
a project it is empty, and the Gate D facts block, Gate E review card and session ledger commands would fail.

Files created after installation:

```
your-project/
└── .claude/
    └── skills/          ← 9 slash commands
        ├── gate-a/
        ├── gate-b/
        ├── ...
        └── harness-update/
~/.claude/
└── hooks/
    └── patrick-work-harness/   ← 12 hook files (10 registered + 2 shared modules)
        ├── master-plan-stale-guard.py
        ├── gate-e-sync-guard.py
        └── ...
```

#### Method 2 — Initialize with /init (if already installed)

To add HARNESS zones to an existing project:

```
/init
```

Creates `CLAUDE.md` sentinel zones · `SESSION_INDEX.md` · `CURRENT_SESSION.md` stubs in one go. Hooks come from the plugin or `install.sh`; `/init` wires them into the project only for a hand-copied source install.

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

#### Gate B → C → D → E (comprehend · implement · verify · record)

```
/gate-b   ← comprehension check (pass-through for trivial work)
/gate-c   ← implement (exactly per Gate A plan)
/gate-d   ← verify (test plan · execution · failure classification)
/gate-e   ← record (WORKLOG + archive)
```

**All work runs A→B→C→D→E.** Gate D is where tests are planned, run and classified, and where the
`## Verification Checklist` marker that Gate C leaves behind gets filled — it is not an optional
refactor step. (Pre-2026-09-24 this README said simple work could take A→B→C→E; that path skipped
the only gate that runs tests.)

#### Autonomous lane (opt-in)

1. Set `enabled: true` under `autonomous_lane:` in `.claude/harness-answers.yml` and **commit** it — the lane reads the setting
   at the plan's base commit, so a session cannot switch itself on. `archive_path` must be set; the card ledger lives there.
2. Run `/gate-a` as usual. If the plan's `### 레인 판정` says 자율, reply 「자율 레인 승인」. 「Gate A 승인」 keeps the review lane.
3. Gate E shows a review card — acceptance commands re-run by script, diff counts, the scope check and flags. Reply 「카드 승인」
   or 「지적: 심각|경미 — …」. `python3 hooks/lane_card.py pending` lists cards still waiting for a verdict.

#### Measuring how the harness is used

`python3 hooks/harness_report.py` reads Claude Code's conversation transcripts (`~/.claude/projects`) and writes a
report: per session, which harness copy ran (plugin, `install.sh`, or a source copy), the models used, the Gate order,
and per guard how often it fired, asked, denied, blocked or warned — including whether you allowed or denied each
confirmation prompt — plus warnings repeated within one session. Run from this repository it also shows how far each
pending prediction in `DECISION_LOG.md` has come. It only reads; the output contains project names and conversation
snippets, so it is written outside any repository (`~/.claude/harness-reports/<date>/`). Transcripts are deleted after
30 days unless `cleanupPeriodDays` is raised (see `/init` Step 6-b).

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

Compares the current `_engine_version` with the latest, shows the CHANGELOG, and batch-updates all 6 axes (HARNESS zone, hooks, dashboard, stubs, Layer 2 docs, lesson store) after user approval.

```
/harness-update --check   ← checklist only, no file changes
```

---

### Changelog

Version history lives in [`CHANGELOG.md`](CHANGELOG.md) and [GitHub Releases](https://github.com/park-jongbeom/patrick-work-harness/releases) (both derived from commit history). It is intentionally **not duplicated here** to keep this README concise.

---

### License

MIT

**Third-party attributions**

| Component | Source | License |
|-----------|--------|---------|
| Minimalism Ladder (7-rung decision framework) | [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) | MIT |

---

## 한국어

Claude Code 기반 소프트웨어 개발 프로세스 자동화 하네스입니다.  
AI가 계획 승인 전에 코드를 작성하는 가장 흔한 실패 패턴을 차단합니다.  
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
| 같은 기술 이해도 재질문 반복 | Gate B(이해도 게이트) 만료형 증적 원장 |

#### 프로세스 흐름

```
/gate-a  →  사용자 승인  →  /gate-b  →  /gate-c  →  /gate-d  →  /gate-e
  계획           ↑             이해도      구현     검증+리팩터     기록
             변경 없음
```

Gate D 는 건너뛰지 않는다. 「C~E 일괄」(또는 「D~E 일괄」)이라고 하면 C → D → E 를 중간 정지 없이 이어 간다. 단 위험 세션
(보안·마이그레이션·공개 API·비가역·저장소 간 작업)과 검증이 실패한 경우는 예외다 — `skills/gate-c/SKILL.md` §Batch runs.

**두 레인 (기본은 꺼짐).** Gate A 는 계획마다 레인도 정한다. 보안, 스키마·저장 데이터, 의존성, 시험·CI, 공개 계약, 둘 이상의
모듈에 닿거나 애매한 작업은 위의 검토 레인으로 간다. 수락 명령이 있고 트리거가 하나도 없는 작은 계획만 **자율 레인**으로 갈 수
있다. 「자율 레인 승인」 뒤 C → D → E 를 멈추지 않고 진행하고, `lane-scope-guard.py` 가 실제 diff 를 계획과 대조하며, 사람은
마지막에 검토 카드 한 장을 판정한다. 프로젝트마다 켜야 한다 — 아래 사용법과 `skills/gate-a/SKILL.md` §0-Lane.

| Gate | 역할 | 설명 |
|------|------|------|
| A | **계획** | 파일별 변경 계획 — 범위·Step·위험 점검. 승인 전 코드 변경 없음(절차 규칙이며 사전 차단 훅은 없다 — 위 설계 원칙 참고). |
| B | **이해도 게이트** | 자유형 흐름 설명, 만료형 증적 원장. 단순 작업은 pass-through. |
| C | **구현** | 코드 구현 — Gate A 계획 그대로. 외부 실행 신호(테스트 PASS/FAIL)로만 종료. |
| D | **검증 + 리팩터** | 검증 루프, 이후 조건부 리팩터 (코드리뷰 3건 이상 또는 명시적 요청 시 실행). |
| E | **기록** | WORKLOG + 장문 archive 생성. 3문서 ✅E 전환. |

#### 영감의 원천 및 저작권 고지

이 하네스는 오픈소스 프로젝트 [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail)(MIT 라이선스, ~48k★)의 **미니멀리즘 래더(minimalism ladder)** 의사결정 프레임워크를 적용합니다.

래더 철학: **"가장 좋은 코드는 안 쓴 코드다."**

기능이나 변경을 계획할 때(Gate A) 새 코드를 작성하기 전에 7칸 래더를 위에서 아래로 확인하며 첫 충족 칸에서 멈춥니다:

1. 이 코드가 필요한가? → 필요 없으면 스킵 (YAGNI)
2. 이미 코드베이스에 있는가? → 재사용
3. 표준 라이브러리가 이미 할 수 있는가? → 표준 라이브러리 사용
4. 플랫폼 네이티브 기능이 있는가? → 네이티브 기능 사용
5. 이미 설치된 의존성이 할 수 있는가? → 의존성 사용
6. 한 줄로 충분한가? → 한 줄
7. 이 모두가 아니면 → 최소한으로 동작하는 코드만 작성

래더는 모든 Gate A의 `0-Ladder` 점검 단계에서 적용됩니다 — 계획에 포함된 새 파일·메서드·추상화마다 어느 칸에서 멈추는지 구현 전에 정당화해야 합니다.

> **라이선스 고지**: 미니멀리즘 래더 개념은 `DietrichGebert/ponytail`(MIT 라이선스)에서 가져왔습니다. 이 하네스 자체도 MIT 라이선스입니다(아래 [라이선스](#라이선스-1) 참고).

---

### 스킬 (슬래시 커맨드)

| 커맨드 | 역할 |
|--------|------|
| `/gate-a` | 변경 계획 수립 — 파일·Step·범위 점검·승인 대기 |
| `/gate-b` | 이해도 게이트 — 흐름을 자기 말로 설명·만료 있는 증적 원장 |
| `/gate-c` | 코드 구현 — Gate A 계획 그대로 구현 후 확인 대기 |
| `/gate-d` | 검증 — 시험 계획·실행·실패 분류(FIX-B/DEP)·코드리뷰 |
| `/gate-e` | 세션 정리 — WORKLOG·archive 생성·3문서 ✅E 갱신 |
| `/audit` | 방향성 점검 — 우선순위·Gate 프로세스·문서 동기화 10항목 |
| `/doc-cleanup` | 문서 슬림화 — 완료 세션 archive 이관·임계값 초과 정리 |
| `/harness-update` | 전체 업그레이드 — 버전 비교→CHANGELOG 표시→4 axis 체크리스트→승인→일괄 갱신 (HARNESS zone 갱신은 Axis A) |
| `/init` | 신규 프로젝트 초기화 — sentinel 2구역·stub 생성·hook 배선 |

---

### 훅 목록

훅은 Claude Code 응답과 도구 호출 전후에 자동 실행됩니다(Stop·PreToolUse·PostToolUse·UserPromptExpansion).

| 파일 | 종류 | 역할 |
|------|------|------|
| `master-plan-stale-guard.py` | Stop | `00_MASTER_PLAN.md` L7 세션 ID ↔ `CURRENT_SESSION.md` 불일치 감지 |
| `gate-a-sync-guard.py` | Stop | Gate A 승인 대기 시 필수 필드(`작업 의도` 등) 누락 감지 |
| `gate-e-sync-guard.py` | Stop | Gate E 후 `SESSION_INDEX.md` ↔ `CURRENT_SESSION.md` ✅E 불일치 감지 |
| `error-topics-guard.py` | Stop | Gate E 오류 기록 누락 감지 |
| `test-tampering-guard.py` | Stop | 응답이 끝날 때마다 reward-hacking 패턴 감지 (4종: `@Disabled`·단언 감소·mock 축소·CI 변조). 커밋 안 된 시험 파일 전체와, 이번 세션에서 한 커밋(세션당 한 번 경고) |
| `comprehension-ledger-stale-guard.py` | Stop | 이해도 게이트(Gate B) 증적 원장 만료 감지 |
| `session-dashboard-sync.py` | PostToolUse | Edit·Write 뒤 `session-dashboard.html` 자동 재생성 |
| `skill-usage-auto.py` | Stop | 스킬 사용 이력 자동 마커 기록 |
| `docker-command-guard.py` | PreToolUse | 잘못된 Docker 명령 실행 차단 (`-it`, 잘못된 컨테이너명 등) |
| `commit-msg-guard.py` | PreToolUse | `git commit -m` 메시지의 한국어 Conventional Commits 형식 검증 |
| `test-write-guard.py` | PreToolUse | Gate D 중 시험 파일 편집 전에 확인 — 시험을 약하게 고쳐 통과시키지 못하게 |
| `comprehension-pending-guard.py` | PreToolUse · UserPromptExpansion | 이해도 질문이 답을 기다리는 동안 `/gate-c`·`d`·`e` 진입 차단 |
| `lane-scope-guard.py` | PreToolUse · UserPromptExpansion | 자율 레인 세션에서만: 보호 경로 쓰기 전 확인, Gate E 진입 때 실제 diff 를 계획과 대조해 벗어나면 세션을 멈춤(확인할 수 없으면 막음) |

> **설계 원칙 — 이 하네스는 Gate A 승인 전 편집을 기계로 막지 않는다 (2026-09-23).**
> 예전에는 `claude-gate-guard.py` 가 PreToolUse 에서 Gate A 진행 중의 코드 편집을
> 거부했다. 고쳐 살리지 않고 **제거**한 이유는 그것이 실제로 막는 것이 거의 없었기
> 때문이다. `.claude/`·`.github/`·`CURRENT_SESSION`·**모든 `.md`** 가 면제였고,
> 코드가 `tool_name == "Bash"` 로만 분기해 PowerShell 호출은 판정 없이 지나갔다.
> 반대로 면제를 걷어내 제대로 조이면 **하네스가 자기 자신을 고치는 것까지 막히고**
> 오탐 비용이 커진다 — 2026-07-27 에 오탐 22·정탐 0 인 가드를 이미 같은 이유로 뺐다.
>
> 그래서 Gate 순서는 **절차(게이트 스킬)와 Stop 시점 검사**가 지킨다. 사전 차단은 하지
> 않는다. `gate-a-sync-guard` 는 Gate A 진행 중에 세션 문서 필수 필드가 비어 있으면
> 응답 종료를 막는다. **「승인 전 코드 금지」는 작업자가 지키는 규칙이지 도구가 강제하는
> 규칙이 아니다** — 문서가 이를 강제라고 말하면 안 된다.

---

### 설치

#### 방법 1 — Claude Code 마켓플레이스 (가장 간단)

```
/plugin marketplace add park-jongbeom/patrick-work-harness
/plugin install patrick-work-harness
```

스킬과 **훅이 함께** 등록된다. 훅은 플러그인 자신의 `hooks/hooks.json` 에서 오고 경로를
`${CLAUDE_PLUGIN_ROOT}` 로 풀기 때문에, **전역 `~/.claude/settings.json` 을 건드리지 않는다.**

> v1.4.0 이전에는 그 파일이 없어서, 마켓플레이스로 설치하면 **훅이 0개**로 들어가면서도
> 설치는 성공한 것처럼 보였다.

#### 방법 2 — install.sh

전역 `settings.json` 에 훅을 직접 등록하는 방식이다. 마켓플레이스를 쓰지 않을 때 선택한다.
**수정 전에 타임스탬프 백업을 남기고, 배포본에 없는 스킬을 지우지 않는다**(v1.4.0).

```bash
# 최신 릴리즈를 현재 프로젝트에 설치
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash

# 특정 버전 지정
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --version v1.0.1

# 설치 경로 지정
curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --target /path/to/your/project

# 릴리스를 내려받지 않고 로컬 체크아웃에서 설치(오프라인·시험용)
./install.sh --source /path/to/patrick-work-harness --target /path/to/your/project
```

`install.sh` 는 복사한 스킬 안의 `${CLAUDE_PLUGIN_ROOT}/hooks/` 경로를 훅 설치 폴더(`~/.claude/hooks/patrick-work-harness/`)로 바꿔 쓴다.
Claude Code 는 이 변수를 플러그인 스킬에서만 채우고, 프로젝트에 복사한 스킬에서는 빈 문자열이라 Gate D 사실 블록·Gate E 검토 카드·
세션 원장 명령이 실패한다.

설치 후 생성되는 파일:

```
your-project/
└── .claude/
    └── skills/          ← 슬래시 커맨드 9종
        ├── gate-a/
        ├── gate-b/
        ├── ...
        └── harness-update/
~/.claude/
└── hooks/
    └── patrick-work-harness/   ← 훅 파일 12개 (등록 10 + 공용 모듈 2)
        ├── master-plan-stale-guard.py
        ├── gate-e-sync-guard.py
        └── ...
```

#### 방법 2 — /init 스킬로 초기화 (이미 설치된 경우)

기존 프로젝트에 HARNESS zone을 추가할 때:

```
/init
```

`CLAUDE.md` sentinel 2구역·`SESSION_INDEX.md`·`CURRENT_SESSION.md` stub 을 일괄 생성합니다. 훅은 플러그인이나 `install.sh` 가 걸고, `/init` 은 손으로 복사한 원본 설치에서만 프로젝트에 훅을 겁니다.

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

#### Gate B → C → D → E (이해도·구현·검증·기록)

```
/gate-b   ← 이해도 점검 (단순 작업은 pass-through)
/gate-c   ← 구현 (Gate A 계획 그대로)
/gate-d   ← 검증 (시험 계획·실행·실패 분류)
/gate-e   ← 기록 (WORKLOG + archive)
```

**모든 작업은 A→B→C→D→E 를 따릅니다.** Gate D 는 시험을 계획·실행하고 실패를 분류하는 단계이며,
Gate C 가 남긴 `## Verification Checklist` 표식을 채우는 곳입니다 — 선택적인 리팩터 단계가 아닙니다.
(2026-09-24 이전 이 문서는 단순 작업에 A→B→C→E 를 안내했는데, 그 경로는 **시험을 돌리는 유일한
게이트를 건너뜁니다.**)

#### 자율 레인 (선택)

1. `.claude/harness-answers.yml` 의 `autonomous_lane:` 아래 `enabled: true` 로 바꾸고 **커밋**한다 — 레인은 계획의 기준 커밋에
   있는 설정을 읽으므로 세션이 스스로 켤 수 없다. 카드 원장이 `archive_path` 에 쌓이므로 그 값이 있어야 한다.
2. 평소처럼 `/gate-a`. 계획의 `### 레인 판정` 이 자율이면 「자율 레인 승인」으로 답한다. 「Gate A 승인」은 검토 레인이다.
3. Gate E 에서 검토 카드가 나온다 — 스크립트가 다시 돌린 수락 명령 결과, diff 수치, 범위 판정, 깃발. 「카드 승인」 또는
   「지적: 심각|경미 — …」로 답한다. `python3 hooks/lane_card.py pending` 이 판정 없는 카드를 보여 준다.

#### 하네스 사용 측정

`python3 hooks/harness_report.py` 는 Claude Code 대화 기록(`~/.claude/projects`)을 읽어 보고서를 만든다. 세션마다 어느
하네스 사본이 돌았는지(플러그인·`install.sh`·원본 사본), 쓰인 모델, Gate 순서, 가드별 발동·묻기·거부·차단·알림 수와
확인 창에 사용자가 허용했는지 거부했는지, 한 세션 안에서 반복된 경고를 센다. 이 저장소에서 돌리면 `DECISION_LOG.md` 의
대기 예측이 확인 시점까지 얼마나 왔는지도 보여 준다. 읽기만 하고, 결과에 프로젝트 이름과 대화 조각이 들어가므로 저장소
밖(`~/.claude/harness-reports/<날짜>/`)에 쓴다. 대화 기록은 `cleanupPeriodDays` 를 늘리지 않으면 30일 뒤 지워진다
(`/init` 6-b 단계).

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

버전 이력은 [`CHANGELOG.md`](CHANGELOG.md)와 [GitHub Releases](https://github.com/park-jongbeom/patrick-work-harness/releases)에 있습니다(둘 다 커밋 이력 기반). README 비대화 방지를 위해 **여기에 중복 기재하지 않습니다**.

---

### 라이선스

MIT

**서드파티 저작권 고지**

| 구성 요소 | 출처 | 라이선스 |
|-----------|------|---------|
| 미니멀리즘 래더 (7칸 의사결정 프레임워크) | [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) | MIT |
