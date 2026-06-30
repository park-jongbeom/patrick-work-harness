---
name: audit
description: "Periodic work-direction review. Verifies priority consistency, Phase regression, Gate-process adherence, prohibited patterns, document sync, and missing handoffs. Use on '/audit', '방향 점검', '감사', '정합성 체크', etc."
effort: medium
---

# /audit Procedure (follow order strictly)

> **Purpose**: Lightweight check that current work is consistent with project priority, process, and guardrails.
> A separate axis from Gate A~E — Gate is "individual session progress", audit is "overall direction verification".

> **Invocation timing** (mirrors CLAUDE.md §/audit Periodic Review):
> - At Gate E completion when accumulated ✅E sessions since the previous audit ≥ 3 (the Gate E SKILL auto-recommends)
> - At a chain transition or priority change (e.g. MEETING-ALIGN chain ends → next chain begins)
> - Manual invocation when the user suspects drift (`/audit`)

---

## Step 0. R/V/D 3-axis classification + model verification (mandatory, PROC-MODEL-RUBRIC-2 revision)

> **PROC enforcement**: This Step must be performed before entering Step 1. Proceeding past Step 1 while ignoring this Step's STOP verdict is a **PROC violation**.
>
> **Revision (PROC-MODEL-RUBRIC-2, 2026-05-06)**: Single-score summation → tier mapping abolished. Model is decided by **3-axis independent measurement** (R/V/D) (same pattern as gate-a SKILL Step 0-A-a/b, adapted to the audit task character).

### Step 0-a. audit-specific R/V/D 3-axis classification

> **Single-canonical declaration**: This Step 0-a "audit-specific R/V/D scoring" + "tier verdict" (0-b) + "current-model detection" (0-c) + "STOP verdict" (0-d) is the **shared PROC canonical for audit·doc-cleanup·gate-e**. doc-cleanup `Step 0-A-c/0-A-d` cites this 0-c/0-d directly (model detection·STOP format). Conversely, doc-cleanup `Step 0-A-a/0-A-b` is a doc-cleanup-specific R/V/D scoring table that measures **different metadata (threshold docs·§5 items)** than this audit 0-a — the two scoring tables are run as **separate canonicals** per each SKILL's task character.
>
> **Shared vs separate**:
> - Shared canonical (model detection·STOP): audit 0-c/0-d (single source)
> - Separate canonical (R/V/D scoring): audit 0-a (direction-check metadata) ↔ doc-cleanup 0-A-a (document-bloat metadata)
> - Philosophy, sources, estimation guide, and R-13 guard → `SKILL_DETAIL.md §Model Rubric Common` (not auto-loaded — load via `Read` when needed).

**Measurement targets (5 metadata)** — measure directly with the commands below, then substitute into the R/V/D items:

```bash
# (1) SESSION_INDEX.md YAML header — extract sessions_since_audit + last_audit_date
grep -E "^(sessions_since_audit|last_audit_date):" \
  ${CLAUDE_PROJECT_DIR}/SESSION_INDEX.md

# (2) §5 「즉시 처리 대상」 item count
awk '/^### 즉시 처리 대상/,/^### 의존 대기/' \
  ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md | grep -c "^- \["

# (3) Permanent DEP Ledger mandatory-re-verification not-done item count
#     Search CLAUDE_DETAIL.md §Permanent DEP Ledger for active items lacking RESOLVED/완료 markers
grep -nE "^- \[(DEP-[0-9]+|R[0-9]+)\]" \
  ${CLAUDE_PROJECT_DIR}/CLAUDE_DETAIL.md 2>/dev/null \
  | grep -v "RESOLVED\|✅ E\|완료" | wc -l

# (4) Active chain transition point — whether the most recent ✅E session is the last row of its chain
#     In the SESSION_INDEX.md table, look at the most recent ✅E row; if all same-chain follow-up sessions are complete/absent, it is a transition point
#     Not grep-able automatically → operator judgment (confirmable during Step 1 status collection)

# (5) §5 dependency-waiting + conditional total count (for V-A2 measurement)
awk '/^### 의존 대기/,/^---/' \
  ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md | grep -c "^- \["
```

> The 5 measured values above are produced by Bash execution **within this response**, and those numbers are substituted into the R/V/D items below. (4) is an operator-judgment item — apply the Step 1 status-collection result back into this Step to finalize the score, then reflect it in the STOP verdict (if the score is unconfirmed, treat conservatively as STOP).

#### R (Reasoning Depth) — Opus promotion gate

| Item | Definition | Score |
|------|------------|-------|
| R-A1 | (2) §5 「즉시 처리 대상」 ≥ 5 items (multi-item classification·priority-reasoning needed) | +3 |
| R-A2 | (3) Permanent DEP Ledger mandatory re-verification not done ≥ 1 (re-verification judgment·resolution-classification reasoning) | +3 |
| R-A3 | (4) Active chain transition point (chain end → next chain entry reasoning) | +3 |
| R-A4 | §3/§4 index–canonical inconsistency suspected (canonical-priority decision reasoning) | +3 |

> **R total ≥ 6 (= 2+ items)** → Opus 4.8 candidate. 0 items = standard check (most audit calls land here).

#### V (Volume) — Sonnet ↔ Haiku branch signal

| Item | Measurement basis | Score |
|------|-------------------|-------|
| V-A1 | (1) `sessions_since_audit` 1~3 +0 / 4~6 +1 / 7+ +2 | +0~2 |
| V-A2 | §5 total item count ((2)+(5)) 1~5 +0 / 6~10 +1 / 11+ +2 | +0~2 |

> Volume has **no effect on Opus promotion**. Used only for the Sonnet ↔ Haiku branch.

#### D (Determinism / Format Strictness) — Sonnet forcing gate

| Item | Definition | Score |
|------|------------|-------|
| D-A1 | 9-item verdict table has a fixed output format (Step 3 result output) | +1 |
| D-A2 | Only 2 SESSION_INDEX YAML fields updated (smallest diff enforced) | +1 |
| D-A3 | This canonical·plan body·code unchanged (many regression guards) | +1 |

> **D total ≥ 2** → Sonnet forced (Opus promotion blocked). audit is inherently D=3 (all 3 items satisfied) — fixed output·smallest diff·no code change are the SKILL definition itself. Hence a standard call with R = 0 is **always Sonnet default**, and Opus promotion is considered only when an R-A* item fires.

### Step 0-b. audit per-Gate model decision rule

audit is a single-SKILL one-shot run, so there is no Gate branching. Decision rule:

| Decision priority | Condition | Recommended model |
|-------------------|-----------|-------------------|
| (1) | R ≥ 6 (2+ R-A items) | **Opus 4.8** |
| (2) | R = 0 + V ≤ 1 + D ≥ 2 (most standard checks) | **Haiku 4.5** (D forces Sonnet as default, but if R=0+V≤1 the simple verdict allows Haiku downgrade) |
| (3) | otherwise (R = 0~3 + V ≥ 2) | **Sonnet 4.6 (default)** |

> **Revision meaning**: The old "total ≤4 = Haiku, 5~9 = Sonnet, 10+ = Opus" single mapping is abolished. R/V/D 3-axis independent measurement separates "direction-check multi-item reasoning (R)" from "repeated-call accumulation (V)" — Opus only when R fires (avoiding systematic Opus bias).

### Step 0-b'. R-13 cost-justification guard

> R-13 guard (Opus output format·auto-downgrade conditions·STOP format) → `SKILL_DETAIL.md §3` (not auto-loaded — load via `Read` when needed). Note: use `{R-A 항목}` prefix in the Opus output format line when citing audit-specific R items.

### Step 0-c. Current-model detection

From the calling Claude's system context (`You are powered by the model named {model}` form), extract a **single model-family keyword** (Opus / Sonnet / Haiku). Ignore the version number.

If keyword extraction fails, treat as "detection failure" and STOP conservatively.

### Step 0-d. STOP verdict (PROC violation enforcement)

Model tier integers: `Haiku=1` / `Sonnet=2` / `Opus=3`.

- **Current tier ≥ recommended tier** → proceed normally (to Step 1). Output 1 line at the start of this response: 「✅ 모델 검증: 현재 {모델} ≥ 권장 {권장} (R={항목 1줄 또는 0} / V={점수 분해} / D={항목 1줄})」.
- **Current tier < recommended tier** → **STOP**. Output the format below verbatim and await the user's response:

```
⚠️ 모델 미달 — 본 호출은 권장 모델 {권장} 이상이 필요합니다.
   현재 모델: {현재}
   R/V/D 분해: R={R-A 항목 1줄 또는 0} / V={V-A1+V-A2 점수 분해} / D={D-A1+D-A2+D-A3 항목}
   결정 근거: {결정 우선순위 (1)/(2)/(3) 중 하나}

다음 중 하나로 응답하세요:
  (a) 「현재 모델로 진행 승인」 — 사용자 책임으로 계속
  (b) `/model {권장}` 후 본 SKILL 재호출

승인 없이 본 SKILL을 진행하는 것은 PROC 위반입니다.
```

Response handling:
- **(a)**: proceed to Step 1. In the **final output** of this response (after Step 4), force-append this 1 line — `⚠️ 모델 미달 우회 (사용자 승인): 현재 {모델} < 권장 {권장} (R={N} / V={N} / D={N})`. Make the bypass visible.
- **(b)**: end this call. The user re-invokes after `/model` switch.

> **Scope of (a) approval**: **valid for this single call only.** On the next audit / doc-cleanup call, if the model is again below the recommended tier, STOP is emitted again. Session-wide cumulative bypass (e.g. "approve all calls from now on") is not recognized; even if such a user response is given, the SKILL performs this Step independently on every call — proceeding without STOP while ignoring this is a **PROC violation**.

> **On system-detection failure**: write "감지 불가" in the "현재 모델" slot of the format above and STOP. The user must state the model explicitly.

> **Decomposition output obligation**: Output the **R/V/D 3-axis decomposition** in the first line of this response. Showing only the total·omitting the decomposition is a **PROC violation**. When producing Opus, the R-13 cost-justification 1 line is also mandatory (Step 0-b' format).

> **R-12 self-contradiction avoidance (memo)**: The audit SKILL itself presupposes "this canonical·plan body·code unchanged" (Step 4), so it is not a direct target of the R-12 guard (changed files ≤ 7 / Step ≤ 5). However, the "1-line recommended action" principle for §5 entries (Step 4-b) is kept (no multi-line entries — inheriting the gate-a R-12 spirit).

---

## Step 1. Status collection (tool calls)

Read these 3 documents:

1. `00_MASTER_PLAN.md` — §2 priority, §3 active tracks, §4 next action, §5 handoff notes
2. `SESSION_INDEX.md` — YAML header + session table
3. `CURRENT_SESSION.md` — dashboard + active Gate block

Additionally if needed:
- `05_PLATFORM_MODERNIZATION/00_MODERNIZATION_MASTER_PLAN.md` §7 (session table)
- Each repository's `CLAUDE.md` guardrail section

---

## Step 2. 10-item check

Check each item in the table below in order and record the verdict (✅ PASS / ⚠️ WARN / ❌ FAIL).

| # | Check item | Check content | Verdict criterion |
|---|------------|---------------|-------------------|
| 1 | **Priority consistency** | Does the current active session match the P0 work in `00_MASTER_PLAN.md` §2 | Work outside P0 scope in progress = FAIL |
| 2 | **Declared-order forcing violation** | Was the declared order (MVP Phase 1~4 / a chain like P0-NEW-1~5 / sub-sessions `-a→-b→-c`) not regressed | Order violation = FAIL |
| 3 | **Gate process adherence** | Any code change without Gate A approval, Gate skipping, or retroactive after-the-fact recording | PROC violation found = FAIL |
| 4 | **Prohibited-pattern violation** | Was no code violating per-repo CLAUDE.md prohibitions written in the current session | Violation found = WARN (fixable immediately) / FAIL (already committed) |
| 5 | **Document sync** | Do the 3 locations §7 session status + SESSION_INDEX.md + CURRENT_SESSION.md agree | Mismatch = WARN |
| 6 | **Missing handoffs** | Is there an unprocessed FIX-B/DEP in §5 that is being ignored by the current session | Omission = WARN |
| 7 | **Permanent DEP Ledger mandatory re-verification** | Among `CLAUDE_DETAIL.md §Permanent DEP Ledger` items, was one re-verified at the first Gate C after its dependent session reached ✅E | Mandatory re-verification not done = FAIL |
| 8 | **Graduation-candidate identification** | List rules·items with 0 firings over the past 6 months and propose them as graduation candidates (do not delete directly — user decides) | ≥1 graduation candidate → WARN (deletion recommended), none → ✅ |
| 9 | **Consolidation-candidate identification** | (a) Stale/duplicate completed items in the `00_MASTER_PLAN.md` index that are retire·merge candidates (b) duplicate·merge candidates in the per-repo error_topics 5-topic ledger (c) HARNESS_EVOLUTION_LOG items that have only decisions but lack outcome (after-effect) feedback — identify·list the 3 kinds (do not clean up directly — user / separate doc-cleanup·PLAN-SYNC session decides) | ≥1 candidate → WARN (cleanup recommended), none → ✅ |
| 10 | **Maintainability delta** | Did the files **changed** by ✅E sessions since the previous audit (a) duplicate·copy-paste logic (b) code churn (rewrite of code written within ~2 weeks) (c) *increase* coupling·cognitive complexity — qualitatively judge the **delta direction**, not a single-score gate. Do not pass/fail by absolute values (MI·cyclomatic complexity) (van Deursen/Shepperd). If a tool is **installed**, use Docker auxiliary measurement (see "tool-conditional commands" below); if not installed, qualitative judgment only. | Duplicate/churn/complexity *increase* found → WARN (refactor·consolidation recommended), no increase/decrease → ✅. Do not refactor directly — a follow-up Gate D·separate session decides |

> **Scope of check item #2**: Includes the MVP demo guardrail Phase 1~4 (CLAUDE.md §MVP) + active-chain order (items marked "order forced" in `00_MASTER_PLAN.md §2`, e.g. P0-NEW-1 → ... → P0-NEW-5 no-parallel) + sub-session (`-a`,`-b`,…) order.

> **Check item #10 rationale·scope (MAINT-AUDIT-1, 2026-06-21)**: AI code generation tends to create new code rather than reuse existing → duplicate·copy-paste increase is the #1 signal (GitClear 211M lines: 2024 duplicate code blocks ↑8×·refactor (move) 24.1%→9.5%·copy-paste overtook refactor for the first time ever). This extends what audit *already prohibits* ("no logic duplication"·"no `String.contains()` substring matching") to **quantitative enforcement·delta tracking** (not a new axis). Focus priority ① duplicate·copy-paste → ② churn (rewrite within 2 weeks — MS Research: relative churn predicts defect density at 89%) → ③ coupling·cognitive-complexity delta. Canonical research → `05_PLATFORM_MODERNIZATION/REPORTS/HARNESS_RIGOR_RESEARCH_V1.md §3`.

### Tool-conditional commands (check item #10 auxiliary measurement)

> **Conditional**: Run via Docker only when the tool below is **installed in the repository** to back up the qualitative judgment. If not installed, skip the command and do qualitative judgment on the changed files only. Avoid dual toolchains: use only tools that coexist with each repo's existing single linter. Refer to `CLAUDE.md §Build·Test` for per-repo canonical Docker commands and container names.

```bash
# Example: Kotlin repo with detekt — adapt container name / compose file from CLAUDE.md §Build·Test
# docker compose -f <path>/docker-compose-test.yml run --rm <test-service> ./gradlew detekt --no-daemon 2>/dev/null || echo "detekt 미설치/실행불가 → 정성 판정만"

# Example: TypeScript repo with jscpd — no permanent dev container → one-shot node container
# docker run --rm -v <repo-path>:/app -w /app node:20-alpine sh -c 'npm install --legacy-peer-deps >/dev/null 2>&1 && npx jscpd src' 2>/dev/null || echo "jscpd 미설치/실행불가 → 정성 판정만"

# Example: Python repo with radon
# docker exec <crawler-container> radon cc src -a 2>/dev/null || echo "radon 미설치 → 정성 판정만"
```

> **Note**: Replace placeholder container names / paths with the project's actual values from `CLAUDE.md §Build·Test` and `.claude/harness-answers.yml → docker_blocked_containers`. Do not hardcode project-specific names in this skill.
> **Excluded tools**: `eslint-plugin-sonarjs` (needs ESLint runtime — conflicts with Biome single-linter)·`pylint R0801` (needs pylint — conflicts with Ruff single-linter). Both would introduce a new dual toolchain, so a maintainability check would itself increase maintenance burden — a self-contradiction. The delta is judged qualitatively on changed files **without storing a metric snapshot** (the audit "record metadata only" principle·Step 4 maintained).

---

## Step 3. Verdict-result output

Output in the following format:

```
── /audit 점검 결과 ──────────────────────────
  날짜       : YYYY-MM-DD
  활성 세션   : {세션 ID}
  현재 Gate   : {Gate 상태}
  직전 audit  : {날짜 또는 "최초"}
──────────────────────────────────────────────
  1. 우선순위 정합성        : ✅ / ⚠️ / ❌  — {1줄 근거}
  2. 선언된 순서 강제 위반   : ✅ / ⚠️ / ❌  — {1줄 근거}
  3. Gate 프로세스 준수     : ✅ / ⚠️ / ❌  — {1줄 근거}
  4. 금지 패턴 위반         : ✅ / ⚠️ / ❌  — {1줄 근거}
  5. 문서 동기화            : ✅ / ⚠️ / ❌  — {1줄 근거}
  6. 인수인계 누락          : ✅ / ⚠️ / ❌  — {1줄 근거}
  7. DEP 원장 의무 재검증    : ✅ / ⚠️ / ❌  — {1줄 근거}
  8. 졸업 후보 식별           : ✅ / ⚠️ / ❌  — {1줄 근거}
  9. consolidation 후보 식별 : ✅ / ⚠️ / ❌  — {1줄 근거}
 10. 유지보수성 delta        : ✅ / ⚠️ / ❌  — {1줄 근거 (중복/churn/복잡도 증감 + 도구 실행 여부)}
──────────────────────────────────────────────
  종합: {ALL PASS / N건 WARN / N건 FAIL}
  권장 조치: {없음 / 구체적 조치 1~3줄}
──────────────────────────────────────────────
```

---

## Step 4. audit history record (SESSION_INDEX YAML single source)

Update the 2 fields in the `SESSION_INDEX.md` YAML header:

```yaml
last_audit_date: "YYYY-MM-DD"   # ← update to today's date
sessions_since_audit: 0          # ← reset to 0 (Gate E does += 1 each session)
```

Add if absent, overwrite if present. WARN/FAIL details are not accumulated into the SESSION_INDEX `priority_note` 1 line — keep them in the separate output only (this response's Step 3 output suffices).

> **Single-source principle**: The `CURRENT_SESSION.md` 「마지막 /audit」 1 line used in earlier operation is no longer used (risk of being dropped during `doc-cleanup` slimming). Unified into the YAML single canonical.

> **Stale-counter recommendation correction (AUDIT-COUNTER-STALE-FIX-1)**: On reset (`sessions_since_audit: 0`), if a **stale recommendation phrase** like `sessions_since_audit=N → /audit 권장` remains in the current head prose (`priority_note`/`next_action`/`CURRENT_SESSION.md` 「다음 행동」), **remove it too** (the canonical just became 0 → the recommendation is unnecessary). Preserve the past `(이전)` chain (fact at that time). This is a legitimate sync of this Step, **not** a violation of the "do not change the body" rule below. Fundamentally, if Gate E does not copy the counter number into prose (gate-e §Step 4 "do not write the counter value in prose"), the target of this correction never arises.

### Step 4-b. On WARN/FAIL, add a §5 recommended action (optional)

If a WARN·FAIL occurred and the next session needs action, add 1 line to `00_MASTER_PLAN.md §5 즉시 처리 대상` (format: `[YYYY-MM-DD / audit N회차] PROC: 조치 1줄`). Register the recommended action only; do not change the canonical·plan body.

---

## Notes on verdicts

- **If even one FAIL exists**: stop current work and propose a corrective direction to the user.
- **If only WARN**: work may continue, but advise the recommended action.
- **ALL PASS**: work direction confirmed normal. No additional action needed.
- What audit records is **check metadata only** — allowed scope:
  - Update SESSION_INDEX YAML 2 fields (`last_audit_date`·`sessions_since_audit`)
  - On WARN/FAIL, add 1 recommended-action line to §5 즉시 처리 대상 (Step 4-b)
- Beyond these 2 kinds, **do not change the canonical·plan body·code**.
