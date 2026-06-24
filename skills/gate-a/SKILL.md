---
name: gate-a
description: "Establishes the Gate A implementation plan. Use when starting a new session or on '작업 계획 작성', 'Gate A 시작', '계획해라', etc."
effort: high
---

# Gate A Procedure (follow order strictly)

## Session Initialization Checklist (mandatory before starting Gate A)

Before session start (before any code change):

0-A. **Load the work-plan index** — `ai-consulting-plans/00_MASTER_PLAN.md`
   - Check §2 priority · §3 active tracks · §4 next action
   - Check **§5 handoff notes**: if 「즉시 처리 대상」·「의존 대기」·「조건부」 has items, review whether they can be reflected when forming this Gate A plan
   - If such an item is incorporated into this session's scope, delete it from §5 at Gate E

0-B. **Index–canonical cross-verification** (mandatory, stale detection)
   - Since the index is not a per-session refresh target (§6 L273), re-verify the actual Gate progress of §3/§4 ⏸/⏳/🟡 items against the canonical (`SESSION_INDEX.md` table + latest archive)
   - On finding `final_status: ✅ E (완료)` in an archive or `✅E` in `SESSION_INDEX.md` → index stale confirmed
   - On finding stale: include an "index correction" Step in this Gate A plan (3rd precedent "stale correction"); if out of scope, register in §5 handoff
   - **Cross-verification scope**: only the session/track this Gate A directly touches — no exhaustive lookup (avoid overhead)
   - **Comprehension-gate ledger expiry check** (COMPREHEND-GATE-1): if this Gate A's target scope has evidence in `plans/learning/comprehension_ledger.md`, check whether `exp` has elapsed·whether the scope files materially changed — on expiry, reflect 「재검증」 in this session's trigger verdict (the auto-expiry-detection Stop hook is planned in COMPREHEND-GATE-1-b)

1. Confirm `ai-consulting-plans/SESSION_INDEX.md` (root) exists
   - YES → load (YAML header only)
   - NO → create new (refer to template)

2. Confirm `ai-consulting-plans/CURRENT_SESSION.md` (root) exists
   - YES → load (only the current-session section's dashboard + active Gate block)
   - NO → create new (record this session's info)
   - ※ The same-named file under `plans/current_work/` is a redirect-guidance file — do not edit

3. Confirm the master plan (detail)
   - New feature → can it be added to `05_PLATFORM_MODERNIZATION/00_MODERNIZATION_MASTER_PLAN.md` §7?
   - Independent work → no creating a separate new master plan
   - Partial work → integrate into the relevant master plan
   - **The index (`00_MASTER_PLAN.md`) is not a per-session refresh target** — update only on priority change·§5 handoff incorporation/migration

## Gate A Procedure

### Step 0-A. Gate A self model verification (mandatory, audit/doc-cleanup pattern)

> **PROC enforcement**: This Step must be performed before entering Step 0 (Pre-Plan investigation). Proceeding past Step 0 while ignoring this Step's STOP verdict is a **PROC violation**.
>
> **Single-canonical declaration**: This Step 0-A "Gate A scoring table" (0-A-a) + "tier verdict" (0-A-b) is the **Gate A-specific canonical**. Gate A uses this table for two things: verifying its own progress model and producing the recommended models for follow-up Gates B/C/D/E (see Step 1's "per-Gate recommended model·effort table").
>
> **Model detection·STOP format**: cite `audit/SKILL.md §Step 0-c/0-d` directly (single canonical). (The audit skill body is not auto-loaded — if that procedure is needed, load it directly via the `Skill` tool.)

### Step 0-A-a. Gate A 3-axis classification (R / V / D)

> Philosophy, sources, estimation guide, R-13 guard, and Effort/Thinking rule → `SKILL_DETAIL.md §Model Rubric Common` (not auto-loaded — load via `Read` when needed).

#### R (Reasoning Depth) — Opus promotion gate

| Item | Definition | Score |
|------|------------|-------|
| R1 | New architecture/domain-model decision (e.g. precise decisions like D-LSE-INTEG-1~5) | +3 |
| R2 | New design of concurrency·transaction-boundary·consistency model | +3 |
| R3 | New algorithm·scoring·matching-weight introduction | +3 |
| R4 | Science·math·statistics reasoning needed | +3 |
| R5 | New security·auth policy (CORS·token·RBAC) | +3 |

> **R total ≥ 6 (= 2+ items)** → Opus 4.8 candidate. **0 items = standard implementation** (most sessions land here).

#### V (Volume) — Sonnet ↔ Haiku branch signal

| Item | Measurement basis | Score |
|------|-------------------|-------|
| V1 | Changed file count 1~3 +1 / 4~7 +2 | +1~2 |
| V2 | Implementation Step count 1~2 +0 / 3~5 +1 | +0~1 |
| V3 | Multiple repos 1 +0 / 2 +1 / 3+ +2 | +0~2 |

> Volume has **no effect on Opus promotion**. Used only for the Sonnet ↔ Haiku branch. For many files, Anthropic's official recommended "Sonnet orchestrator + Haiku worker parallel" pattern is more cost-efficient than a single Opus.

#### D (Determinism / Format Strictness) — Sonnet forcing gate

| Item | Definition | Score |
|------|------------|-------|
| D1 | smallest diff enforced (existing-pattern preservation stated, CLAUDE.md R-4) | +1 |
| D2 | Fixed format·schema output (DTO·SQL·i18n keys, etc., deterministic output) | +1 |
| D3 | Many regression guards (e.g. obligation to keep 285+ tests PASS) | +1 |

> **D total ≥ 2** → Sonnet forced (Opus promotion blocked). Sonnet's instruction-following advantage·overengineering avoidance fits deterministic work. Opus tends to be "warmer/longer/over-elaborate" and conflicts with smallest diff.
> **D-axis direction caution (technique-5 review result, 2026-05-25)**: This D-axis uses determinism as an 'Opus blocking gate' (Sonnet's instruction-following advantage fits deterministic formats). The direction differing from the industry routing convention 'determinism = easy work → weak model (Haiku downgrade)' is intentional design — D is not a Haiku-downgrade signal but an Opus-promotion-blocking signal.

### Step 0-A-b. Per-Gate model decision rule

| Gate | Decision rule (in priority order) |
|------|-----------------------------------|
| **A** (plan) | (1) R ≥ 6 → Opus 4.8 (2) R = 0 + V ≤ 1 + D = 0 → Haiku 4.5 (3) otherwise → **Sonnet 4.6 (default)** |
| **B** (implement) | (1) **default Sonnet 4.6** — Anthropic official coding positioning·instruction-following advantage·overengineering avoidance fit the smallest-diff guard (2) Opus promotion = only when a Gate A unresolved R decision is delegated to B (1-line reason mandatory) (3) Haiku downgrade = R=0 + V≤1 + D≥1 (repeated-pattern application·CRUD mass production — SWE-bench Haiku 91%·RouteLLM basis) |
| **C** (verify) | (1) API/DB/SEC coupling or self-debug branch → Sonnet 4.6 (2) Simple regression re-confirm (already PASS) → Haiku 4.5 |
| **D** (refactor) | (1) **default Sonnet 4.6** (overengineering-avoidance advantage) (2) R ≥ 6 (architecture-redesign class) → Opus 4.8 |
| **E** (cleanup) | always Haiku 4.5 |

> **Per-Gate independent application**: Even if Gate A is Opus, Gate B is default Sonnet (Anthropic official pattern). The old "Gate B = same model as A" auto-inheritance rule is abolished (PROC-MODEL-RUBRIC-1).

> **Meaning of self-verification**: Gate A is "deciding the whole session's direction", so Opus promotion only when an R item (architecture decision·new algorithm, etc.) explicitly arises. Even with many changed files·repos, if R = 0, Sonnet suffices — for multi-file handling, Anthropic's official recommended "Sonnet orchestrator + Haiku worker parallel" pattern is more cost-efficient than a single Opus.

### Step 0-A-b'. R-13 cost-justification guard + Step 0-A-b''. Effort·Thinking decision rule

> R-13 guard (Opus output format·auto-downgrade conditions·STOP format) and Effort/Thinking rule (per-Gate table) → `SKILL_DETAIL.md §3` and `§4` (not auto-loaded — load via `Read` when needed).

### Step 0-A-c. Current-model detection + Step 0-A-d. STOP verdict

Apply the **same procedure** as `audit/SKILL.md` Step 0-c / Step 0-d (single canonical). Format·bypass handling·detection-failure handling are all identical.

Summary:
- Current tier ≥ recommended → proceed normally (to Step 0 Pre-Plan investigation). Output 1 line at the start of this response: 「✅ 모델 검증: 현재 {모델} ≥ 권장 {권장} (R/V/D 분해, {등급})」.
- Current tier < recommended → STOP. Use the audit STOP format, stating the score breakdown.

> **Decomposition output obligation**: Output the **R/V/D 3-axis decomposition** in the first line of this response (e.g. `현재 Sonnet ≥ 권장 Sonnet (R=0 / V=2: 변경파일 4 +1 + Step 3 +1 + 단일저장소 +0 / D=1: smallest diff +1 → Sonnet 디폴트)`). Omitting the decomposition·showing only the total is a **PROC violation**. When producing Opus, the R-13 cost-justification 1 line is also mandatory (Step 0-A-b' format).

> **This 3-axis classification is the single canonical for producing the follow-up Gate B/C/D/E recommended models**: Step 1's "per-Gate recommended model table" is produced by applying the Step 0-A-b per-Gate decision rule **independently to each Gate** (no natural-language prose, no Gate B auto-inheritance).

---

### 0. Pre-Plan investigation (ECC search-first)

**Immediately before** reading related files, perform the 1~2 items below and record the result links in the Gate A required output item
"기존 구현 참조 경로". If there is no investigation result, state "없음".

- `Grep` / `Glob` — search for similar features·same naming·already-existing helpers
- If needed, `gh search code` or external-library documentation check

Purpose: avoid writing a duplicate implementation, and pass existing patterns to Gate B as reuse candidates.

> **💡 Multi-repo exploration subagent delegation (HARNESS-DELEGATE-1)**: When investigating 2+ repositories and raw output is expected to accumulate heavily in main ("intermediate output ≫ conclusion"), delegate the exploration to the `Explore` subagent and **retrieve only the conclusion** — college-crawler↔ga-api-platform schema comparison, front↔back API contract checks, etc. **For single-file·small exploration, inline is better due to spawn overhead** (no delegation when the verdict gate is unmet). Detail → `CLAUDE_DETAIL.md §Subagent Delegation Guidelines`.

#### 0-Fitness. System fitness check (HARNESS-PLAN-AUGMENT-1, 2026-06-09)

> The duplicate-avoidance investigation above sees only **internal reuse**. This check self-checks **within Gate A** whether the plan is consistent with the system direction (the current `/audit` is a post-check — this check pulls part of it forward to the Gate A point).

After reading all related files, self-check the 3 axes below in 1 line each and record the result in the required output item "시스템 적합성 점검":

- **Architecture consistency**: does the change not conflict with the existing stack·layer·canonical pattern (when introducing a new pattern, cite 1 existing canonical)
- **Phase guardrail**: is it not a Phase regression of `CLAUDE.md §MVP 데모 로드맵 가드레일` (not bringing a lower Phase to Gate A before a higher one)
- **Prohibited patterns**: no violation of per-repo core prohibitions (during MVP)·common prohibitions (smallest diff·YAGNI·key hardcoding)

Verdict: if all 3 axes are consistent, 「적합성 ✅ (아키텍처/Phase/금지 정합)」 1 line. If there is a violating·suspect axis, state that axis + response (scope adjustment or user query `AskUserQuestion`).

#### 0-OSS. OSS catalog reference check (HARNESS-PLAN-AUGMENT-2, 2026-06-10)

> Where "0-Fitness" above sees **internal consistency**, this check self-judges at the Gate A point whether the plan has **room to be complemented by adopting external OSS** and asks the user (user request 2026-06-09: "depending on task complexity, self-judge whether to complement the plan by referencing open source, then ask"). The reference-catalog canonical = `05_PLATFORM_MODERNIZATION/REPORTS/HARNESS_OSS_SCAN_V1.md` §4 (OSS-SCAN-1 output).

After reading all related files, check the trigger table below. **If any applies**, propose a §4 candidate as a 1-line complement and ask whether to adopt via `AskUserQuestion` (not forced adoption — user decides):

| Trigger (this plan's task character) | OSS candidate (§4) | Complement effect |
|--------------------------------------|--------------------|-------------------|
| External-library version change·DEP-BUMP·new-library introduction·framework migration | **Context7 MCP** (P0) | Inject per-version latest docs → prevent stale-API inference |
| react-web-ga UI/flow change + E2E verification needed | **Playwright MCP** (P1) | Fill the E2E gap of unit-tests-only |
| Long Gate C verification·large test logs·multi-repo simultaneous verification | **Context Engineering / 5 coordination patterns** (P1/P2) | tool-result-clearing·delegation for token saving |

`AskUserQuestion` options: ① register as a separate `OSS-ADOPT-*` track / ② incorporate into this session's scope / ③ no adoption (reference only).

Verdict: if no trigger applies, 「OSS 참조 N/A (트리거 미해당)」 1 line (natural skip for simple doc·cleanup work). If applicable, record the proposed candidate + the user-decision result in the required output item "OSS 카탈로그 참조 점검".

#### 0-Ladder. Minimalism ladder check (R-4-6, 2026-06-23 · ponytail OSS)

> Where "0-Fitness" sees internal consistency and "0-OSS" sees external complement, this check forces the plan to write **the least code that works**. Source: `DietrichGebert/ponytail` (OSS, MIT) decision ladder — "the best code is the code you never wrote". Canonical rule = `CLAUDE.md §Prohibited` minimalism ladder.

For **each new file·method·abstraction** the plan introduces, apply the 7-rung ladder top-down and **stop at the first rung that satisfies the task**, then record that rung number:

1. Does this need to exist? → **skip it** if not (YAGNI)
2. Already in this codebase? → **reuse** (no rewrite)
3. Stdlib does it? → **use stdlib**
4. Native platform feature? → **use native**
5. Installed dependency? → **use existing package**
6. One line? → **one line**
7. Only then → **the minimum that works**

If a planned new-code item can stop at rung 1~5, **remove it from the plan** (or replace it with reuse/stdlib/native/dependency). The ladder runs **after** understanding the problem (read the code the change touches·trace the real flow), not instead of it.

**Safety guardrail (non-negotiable)**: trust-boundary validation·data-loss handling·security·accessibility are **never** trimmed at any rung, regardless of which rung applies.

Verdict: record the per-new-item rung number in the required output item "미니멀리즘 래더 점검". If 0 new items (reuse/edit-only), 「N/A (신규 추상화 없음)」 1 line.

1. **After reading all related files**, output the Gate A content as text
   - Changed-file list (number·path·change type)
   - Per-file detailed change content: current code structure → post-change structure, key decisions
   - **기존 구현 참조 경로** (Pre-Plan investigation result; "없음" if none)
   - External-dependency mapping (design tokens·API·library versions, etc.)
   - Execution order (based on dependencies)
   - Risks and responses (concrete cause + response method)
   - **시스템 적합성 점검** (architecture·Phase·prohibited-pattern 3 axes, 1 line; the "0-Fitness" result above — HARNESS-PLAN-AUGMENT-1)
   - **이해도 게이트 발동 판정** (COMPREHEND-GATE-1) — produce 1 line by risk heuristic (AI auto + user override): 「발동(폭발반경 大→사용자 설명 / 일반 위험→AI 자기설명)」 or 「미발동(사소 CRUD·문서·정형 변경)」. On firing, after Gate A approval `/comprehend-gate` precedes gate-b. Criteria → `comprehend-gate/SKILL.md §Step 0` (the comprehend-gate skill body is not auto-loaded — if the firing-criteria detail is needed, load it directly via the `Skill` tool.)
   - **OSS 카탈로그 참조 점검** (on trigger, propose §4 candidate + user decision / if not applicable, 「N/A」 1 line — HARNESS-PLAN-AUGMENT-2)
   - **미니멀리즘 래더 점검** (R-4-6) — per new file·method·abstraction, the rung number at which it stops (e.g. `MatchScoreCalculator 신규 — 래더 7칸(rung 2·3·4·5 불가 확인)`); the "0-Ladder" result above. If 0 new items, 「N/A (신규 추상화 없음)」 1 line
   - **Gate D (refactor) expectation and basis** (needed/not needed + 1-line reason)
   - **Per-Gate recommended model table** — produced by applying the Step 0-A-b per-Gate decision rule **independently to each Gate** (Gate B auto-inheritance abolished):

     **Mapping rule (single canonical, PROC-MODEL-RUBRIC-1 revision)** — re-score the Step 0-A-a R/V/D classification per each Gate's task character:

     | Gate | Mapping procedure | Output model |
     |------|-------------------|--------------|
     | **B** (implement) | **default Sonnet 4.6**. Opus promotion = only when a Gate A unresolved R decision is delegated to B (1-line reason mandatory). Haiku downgrade = R=0 + V≤1 + D≥1 (repeated-pattern application·CRUD mass production — SWE-bench Haiku 91%·RouteLLM basis). No auto-inheritance even if Gate A is Opus | decision-rule result |
     | **C** (verify) | API/DB/SEC coupling or self-debug branch → Sonnet 4.6. Simple regression re-confirm (already PASS) → Haiku 4.5 | decision-rule result |
     | **D** (refactor) | produced only when "Gate D 예상 = 필요". default Sonnet 4.6 (overengineering-avoidance advantage). Architecture-redesign class R≥6 → Opus 4.8 | decision-rule result or — |
     | **E** (cleanup) | always Haiku 4.5 | Haiku 4.5 |

     **Output format**:

     | Gate | 권장 모델 | Effort / Thinking | 분해 (R / V / D) | 비용 정당화 (Opus 한정, R-13) |
     |------|----------|--------------------|-----------------|----------------------|
     | B | {Opus 4.8 / Sonnet 4.6 / Haiku 4.5} | {high·medium·low} / {auto·off} | R={항목 1줄 또는 0} / V={점수 분해} / D={항목 1줄 또는 0} | (Opus면) "R{N}건 — {항목 나열}" / (그 외) — |
     | C | {…} | {medium·low} / off | R={C 한정 — API/DB/SEC 결합 여부} / V=— / D={회귀 가드 多 여부} | … |
     | D | {모델 또는 —} | {medium} / off | R={리팩터 깊이 — R≥6 여부} / V=— / D={overengineering 회피 명시 여부} | … |
     | E | Haiku 4.5 | low / off | — | — |

     > **No natural-language prose**: instead of natural-language reasons like 「표준 구현 — Opus 불필요」, cite the **Step 0-A-a R/V/D decomposition** directly. That way, follow-up Gates can verify consistency using the same metadata during model verification.
     > **R-13 guard**: an Opus-produced row must have the R items in 1 line in the cost-justification column. If unmet, auto-downgrade to Sonnet (Step 0-A-b' format).
   - **Scope-check forced STOP guard** (R-12, introduced 2026-05-04 HARNESS-OPTIMIZE-1-b-1):

     This guard is a **pre-emptive STOP** — checked right after computing the changed-file·Step count, **before outputting the plan text and updating the 3 documents**. On violation, refuse both the Gate A text output and the document update, and output the STOP format below.

     **Guard items**:
     ```
     ## Gate A 범위 점검
     - [ ] 변경 파일 ≤ 7개
     - [ ] 구현 Step ≤ 5개
     - [ ] 변경의 논리적 이유가 1가지
     - [ ] 서브세션 없이도 각 Step 후 컴파일 가능
     ```

     **STOP format** (when changed files > 7 or Step > 5, reusing the `audit/SKILL.md` Step 0-d format):
     ```
     ⛔ Gate A 범위 가드 STOP (R-12)
     - 변경 파일 N개 (가드: ≤ 7) / 구현 Step M개 (가드: ≤ 5)
     - 사유: [전체 범위가 단일 세션 한계 초과]
     - 분할 후보:
       - {-a-1}: [그룹 A 파일·Step 요약] (≤ 7 / ≤ 5)
       - {-a-2}: [그룹 B 파일·Step 요약] (≤ 7 / ≤ 5)
     - 사용자 결정 필요: ① -a-1만 본 세션 진행 / ② -a-2만 본 세션 진행 / ③ 「가드 우회 진행」 명시
     ```

     **Bypass handling** (restricted):
     - Proceed only when the user **explicitly states in a sentence** 「가드 우회 진행」 in their response
     - When proceeding, record 1 line at the end of the Gate A response: `> ⚠️ R-12 가드 우회: 사용자 명시 승인 (변경 파일 N개 / Step M개)`
     - Ambiguous responses like 「진행」「ok」「계속」 are not recognized as a bypass (same as the Gate A approval interpretation rule)

     **Self-contradiction avoidance**: This guard applies **from the next Gate A call** after R-12 introduction. The R-12 introduction itself (HARNESS-OPTIMIZE-1-b-1) proceeds under the pre-change SKILL, but pre-satisfies the post-change guard via the user decision to split 1-b whole (8+ files) → 1-b-1/1-b-2.

2. Update the 3 documents (status: `A (승인 대기)`, write the Gate A block) — **run the file-editing tool**
   - `00_MODERNIZATION_MASTER_PLAN.md` §7
   - `SESSION_INDEX.md` YAML
   - `CURRENT_SESSION.md` dashboard + the full Gate A block content (no writing a summary table only)
     - **Intent-field obligation (DASHBOARD-INTENT-1)**: in the header, write 2 lines in plain Korean — `> **세션 주제**: <평이 한 줄>` (banner title)·`> **작업 의도**: <무엇을 왜, 1~2문장>` (banner body). No jargon·filename dumps — the banner 「🎯 지금 하는 작업」 displays these 2 lines as-is (falls back to work_topic·priority_note if absent).
   > **session-dashboard.html update**: `session-dashboard-sync.py` always runs as the first entry of the `Stop` hook array, auto-regenerating the HTML (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

3. STOP — await user document review·approval

## Gate A Approval Interpretation

- 「진행」「다음 작업」 alone are not interpreted as Gate A approval
- Explicit phrases recognized as approval: 「Gate A 승인」「계획대로 구현」「위 Gate A대로 구현해」 etc.

## Dashboard Required Fields (PROC-MODEL-RUBRIC-2 revision)

At every Gate transition, the items below must be updated:
- Current Gate, Gate progress (✅⏸☐), next action
- **R/V/D decomposition** — Step 0-A-a 3-axis scoring result (e.g. `R=0 / V=2: 변경파일 4 +1 + Step 3 +1 + 단일저장소 +0 / D=1: smallest diff +1`)
- **Per-Gate recommended model** (B/C/D/E each, the result of applying the Step 0-A-b + 0-A-b'' decision rule — e.g. `B: Sonnet 4.6 (medium/off) / C: Haiku 4.5 (low/off) / D: 미예상 / E: Haiku 4.5 (low/off)`)
  - Format: `{모델} ({effort}/{thinking})` — writing the 3 items together is mandatory (model only is a PROC violation)

> **Revision reason (PROC-MODEL-RUBRIC-2)**: The old "task complexity (L·M·H) + recommended model (Haiku·Sonnet·Opus)" single mapping cannot be consistent with R/V/D 3-axis scoring. The new format can be re-scored with the same metadata during follow-up Gate model verification.

## Model Selection Criteria (reference summary)

> **Model Selection Criteria (reference summary)** → `SKILL_DETAIL.md §5` (not auto-loaded — load via `Read` when needed). Exact scoring: Step 0-A-a R/V/D classification + Step 0-A-b decision rule.

---

## This Gate response's mandatory final output

After completing the entire Gate A procedure (plan output + 3-document update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

```
---
**다음 단계**: Gate A 검토 후 「Gate A 승인」또는 「계획대로 구현」으로 승인하면 `/gate-b` (Gate B 구현)가 시작됩니다.
```
