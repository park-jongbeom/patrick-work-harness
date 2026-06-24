---
name: error-log
description: "Records errors from session Gate B~D into the per-repository error-topic ledger. Auto-invoked inside Gate E, or used standalone on '오류 기록', '에러 원장 업데이트' requests."
effort: low
---

# error-log Procedure (follow order strictly)

## Step 0 — Error-occurrence verdict

Check the items below in the Gate B~D blocks of `CURRENT_SESSION.md`:

| Check item | If applicable |
|----------|--------|
| Gate B: build·type·runtime failure (FIX-B occurred) | record target |
| Gate C: FIX-B classification item exists | record target |
| Gate D: re-verification failure | record target |
| Docker·environment·permission retry occurred | record target |

**Verdict criteria** (all must hold to record):
- At least one of the above items applies
- Has "value for the next session to reuse" (exclude simple typos·one-off mistakes)

→ **If no target, output "오류 기록 대상 없음 — 생략"** then **proceed to Step 0-B (HARNESS_EVOLUTION branch)** (no immediate termination).

---

## Step 0-B — HARNESS_EVOLUTION_LOG auto-registration branch (R-11, introduced 2026-05-04 1-b-1)

> **Introduction background**: HARNESS_EVOLUTION_LOG went silent after 4-14. Tracking of "why it became so" for PROC·harness changes was severed, making it hard for audit·new sessions to grasp PROC intent. This Step auto-triggers PROC-evolution registration by analyzing Gate B/C/D change targets.

### Step 0-B-a: trigger condition check

Check whether this session's Gate B/C/D changed-file list (`CURRENT_SESSION.md` Gate block is canonical — `ai-consulting-plans`·`plans` containing SKILL/CLAUDE.md are non-git so `git status` is unavailable. Only git-tracked repos [react-web-ga·ga-api-platform·college-crawler] may use `git status` as an aux) matches at least one of the 4 groups below:

| Group | glob pattern |
|------|----------|
| Skill definition | `.claude/skills/*/SKILL.md` (all SKILL files) |
| Top-level PROC doc | `ai-consulting-plans/CLAUDE.md` |
| Detail PROC doc | `ai-consulting-plans/CLAUDE_DETAIL.md` |
| Index §6 (document-structure guide) | `ai-consulting-plans/00_MASTER_PLAN.md` §6 area change (`awk '/^## 6\./,/^## 7\./'`) |

> If no trigger target applies (e.g. only code·test·SQL changes) → output "HARNESS_EVOLUTION 등재 대상 없음" then end Step 0-B. Whether to proceed to Step 1 follows Step 0's error verdict result.

> **Skip when LOG canonical absent**: if `${HARNESS_PLANS_DIR}/process_evolution/HARNESS_EVOLUTION_LOG.md` is absent or empty, skip all of Step 0-B. The SKILL proceeds safely even in project branches where the R-11 feature is disabled.

### Step 0-B-b: write the registration entry

If applicable, append an entry at the bottom of the canonical `${HARNESS_PLANS_DIR}/process_evolution/HARNESS_EVOLUTION_LOG.md`:

```markdown
## [YYYY-MM-DD] {세션ID} — 한줄 요약

**태그**: {SCOPE | STRUCTURE | GATE | TOKEN | PROC | OTHER 중 1개 이상}

**맥락**: 어떤 문제·관찰이 변경을 촉발했는가 (1~3줄)

**확립된 원칙**: 본 변경으로 명문화된 규칙·정책 (불릿 또는 표)

**변경 내역**: 영향 파일 + 변경 요점 (불릿)

**재발 방지**: 본 원칙이 어떤 PROC 위반/혼선을 막는가 (1~2줄)

**영향 받은 파일**:
- {파일 경로 1}
- {파일 경로 2}
- ...
```

> Keep the format identical to the canonical LOG's existing entries (e.g. the `## 2026-04-14` item). If a new tag is needed in the header's 「태그 분류」 table (SCOPE/STRUCTURE/GATE etc.), add 1 row to that table too at the time of writing this entry.

### Step 0-B-c: output the registration result

In the Step 3 result output, note 「HARNESS_EVOLUTION 등재: Y/N」 in 1 line. If Y, quote the registration entry header in 1 line.

### Step 0-B-d: whether to proceed to Step 1 after registration

- Step 0 「오류 기록 대상 없음」 + Step 0-B registration Y → skip Step 1, go straight to Step 3 (output with only HARNESS_EVOLUTION registered)
- Step 0 record target occurred + Step 0-B registration Y → proceed to Step 1 (output both error + HARNESS_EVOLUTION)

> **Separation principle**: HARNESS_EVOLUTION registration triggers unconditionally on PROC change (regardless of error occurrence). Independent of error recording (when Step 0 passes).

---

## Step 1 — Determine the repository and topic file

**Canonical locations** (independent per repository):

| Repository | error_topics path |
|--------|-----------------|
| `react-web-ga` | `react-web-ga/docs/rules/error_topics/` |
| `ga-api-platform` | `ga-api-platform/docs/rules/error_topics/` |
| `college-crawler` | `college-crawler/docs/rules/error_topics/` |
| `ai-consulting-plans` · `plans` | none of their own → use the code repository of that session |

> Each folder's `README.md` is the topic index (canonical). Do not write to `../error_analysis.md`.

**Topic-file mapping** (common to the three repositories):

| File | Tag | Target error |
|------|------|----------|
| `gate_process.md` | `PROC` | Gate approval·procedure·「구현」 interpretation·after-the-fact retroaction |
| `runtime_env.md` | `ENV` | Docker·container·npm·gradle·pytest·lockfile·permission·path |
| `git_commit.md` | `PROC` | commit message·git operation |
| `testing.md` | `TYPE` `VERIFY` `LOGIC` | type·build·test failure·CI verification |
| `security_schema.md` | `SEC` `API` | XSS·token·axios·API contract·DB schema |

If the topic does not fit the 5 above:
1. Create a new topic file
2. Add 1 row to that repository's `error_topics/README.md` table

---

## Step 2 — Write the error item and append

Add a date section at the bottom of the relevant topic file:

```
## [YYYY-MM-DD] 세션ID — 한줄 요약
- **발생 Gate**: B / C / D
- **증상**: (로그·메시지 핵심 1~3줄)
- **근본 원인**: 무엇이 왜 틀렸는가
- **해결**: 파일·라인 포함 변경점
- **재발 방지 규칙**: 다음 세션이 지켜야 할 1줄 규칙
```

> No creating a new document per session — always append to an existing topic file.

---

## Step 3 — Result output

After recording, output in the format below:

```
## error-log 결과
기록 건수: N건
기록 위치:
  - [저장소]/docs/rules/error_topics/[주제파일].md — [세션ID] [태그]
  (없으면 "대상 없음")
HARNESS_EVOLUTION 등재 (R-11): Y / N
  - Y인 경우 등재 entry 헤더 1줄: "## YYYY-MM-DD {세션ID} — 한줄 요약"
  - N인 경우 사유: "trigger 조건 미해당 (Skill·CLAUDE.md·CLAUDE_DETAIL.md·인덱스 §6 변경 없음)"
```
