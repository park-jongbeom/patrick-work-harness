---
name: SKILL_DETAIL
description: "Shared model-rubric detail + plan-doc update pattern for gate-a~e, audit, doc-cleanup. Load on demand (not auto-loaded). Reference via Read when R-13 guard, Effort/Thinking rule, or tier-aware plan-doc update wording is needed."
---

# Skill Common Model Rubric Detail

> **Load-on-demand** — this file is NOT auto-loaded. Load it explicitly via `Read` when the R-13 cost-justification guard, Effort/Thinking rule, PROC-MODEL-RUBRIC rationale, or the tier-aware plan-doc update pattern is needed during a Gate response.
> **Canonical home**: this file is the single source for the shared sections below. Skill-specific R/V/D item tables and model decision rules remain inline in each skill.

---

## §Plan-Doc Update Pattern

> **Canonical home**: every gate-a~e/audit/doc-cleanup reference to "update the plan document(s)" or "§7" cites this section by name rather than restating tier-specific wording inline. Edit here only.

Consuming projects track work-in-progress via one of two plan-doc **tiers**, recorded in `harness-answers.yml → plan_tier`:

- **`plan_tier: "2"`** (or **field absent** — pre-existing repos initialized before this field existed default to `"2"`, never error or re-prompt): a separate **index** doc (`<master_plan_file>`, default `${MASTER_PLAN_FILE}`) plus a **sub-platform detail-plan** doc (`<detail_plan_file>`) that owns its own session table (conventionally §7).
- **`plan_tier: "1"`**: a single **plan doc** (`<single_plan_file>`, default `WORK_PLAN.md`) that carries both index and session-table roles via `## Phase N` sections.

**Plan-doc update (tier-aware)** — apply this whenever a Gate needs to record session status into the plan document(s):

- **`plan_tier: "2"`** → update `<detail_plan_file>` §7 (this session's row/entry) **and** `<master_plan_file>` (index — priority/next-action touch only; the index is not a per-session refresh target, per the existing rule)
- **`plan_tier: "1"`** → update the matching `## Phase N` section of `<single_plan_file>` (create/update the session's row under that Phase). No separate index update — the single doc *is* the index.

Do not assert a fixed document count ("3 documents", "4 documents") in prose — say "the applicable plan document(s)" and let the tier-aware bullets above do the counting. The actual total also depends on `session_docs` (whether `${SESSION_INDEX_FILE}`/`${CURRENT_SESSION_FILE}` exist as separate files), which is orthogonal to `plan_tier`.

---

## §Model Rubric Common

### §1. PROC-MODEL-RUBRIC Philosophy and Sources

> **Revision (PROC-MODEL-RUBRIC-1/2, 2026-05-06 · model-generation refresh HARNESS-MODEL-ROUTING-1, 2026-07-06)**: Single-score summation → tier mapping abolished. Model is decided by **3-axis independent measurement** (R / V / D).
> Basis: Anthropic official positioning (Sonnet 5=coding mainstay·Opus 5.5=long horizon·science reasoning·Haiku 4.5=1/3 the cost of Sonnet coding)·METR multi-axis capability research·Anthropic's official recommended "Sonnet orchestrator + Haiku worker" pattern·deep-research findings on the current 4-model lineup ((internal research note, if your project maintains one)).
> Sources: [Anthropic Opus 5.5](https://www.anthropic.com/news/claude-opus-4) · [Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) · [Haiku 4.5](https://www.anthropic.com/news/claude-haiku-4-5) · [METR Time Horizon by Domain](https://metr.org/blog/2025-07-14-how-does-time-horizon-vary-across-domains/)

### §2. Estimation Guide

**Estimation guide**:
- The old "assume the upper bound / when tier is ambiguous go one step up" bias rule is **abolished** (a cause of systematic Opus bias).
- R items are qualitative — **if ambiguous, score 0** (conservative on Opus promotion, cost-saving).
- V is measured as-is. D is +1 only when there is an explicit requirement.
- When ambiguous, the model **converges to Sonnet default** (median balance).

### §3. R-13 Cost-Justification Guard (PROC-MODEL-RUBRIC-1/2)

> **PROC enforcement**: When producing an Opus 5.5 recommendation, **listing the R items in one line is mandatory**. Producing Opus while R = 0 is a PROC violation. If the **2× output-token cost vs Sonnet ($20 vs $10 per 1M, Opus 5.5 : Sonnet 5, verified 2026-09-24)** is not justified by R items, auto-downgrade to Sonnet.

**Opus recommendation output format**:

```
> 💰 비용 정당화 (R-13): R{N}건 ({R 항목 1줄 나열}) — Sonnet 대비 2× 비용 정당화. 미충족 시 Sonnet 다운그레이드.
```

**Auto-downgrade conditions**:

- **R = 0 + Opus produced** → **PROC violation**, force-downgrade to Sonnet + output STOP format
- **R = 1 (single item, score 3) + Opus produced** → 1-line warning + recommend downgrade to user (not forced — borderline case)
- **R ≥ 2 (score 6+) + Opus produced** → normal

**Example (normal)**:
> 💰 비용 정당화 (R-13): R 2건 (R1 신규 도메인 모델 + R3 매칭 가중치 신규 알고리즘) — Sonnet 대비 2× 비용 정당화.

**STOP format (on violation)**:

```
⚠️ R-13 비용 정당화 미충족 — Opus 산출이지만 R = 0
   변경 내용: V={점수 분해} + D={항목}만 발생, R 항목 없음
   조치: 자동 Sonnet 다운그레이드. /model sonnet 후 재진입 권고.
```

### §4. Effort·Thinking Decision Rule (PROC-MODEL-EFFORT-1)

> **Purpose**: Specify per-Gate the effort (token budget)·thinking (reasoning-chain exposure) settings independently of model selection.
> **Basis**: Mollick et al. 2025 — recent models internalize CoT, reducing the effect of external thinking display; D≥1 deterministic work induces thinking=auto over-elaboration.

| Gate | Task character | Effort | Thinking |
|------|----------------|--------|----------|
| **A** (plan) | R≥2 new architecture decision | high | auto |
| **A** (plan) | R=0 standard plan | medium | off |
| **B** (implement) | D≥1 deterministic output (smallest diff·format) | medium | off |
| **B** (implement) | R≥2 unresolved-decision delegation | high | auto |
| **C** (verify) | API/DB/SEC coupling·self-debug | medium | off |
| **C** (verify) | Simple regression re-confirm | low | off |
| **D** (refactor) | default | medium | off |
| **E** (cleanup) | always | low (Haiku 4.5 → —) | off |

> **Thinking=auto condition**: only when an R≥2 item actually needs to be resolved. If D≥1, prefer thinking=off (CoT over-elaboration conflicts with deterministic output).
> **Dashboard notation**: `B: Sonnet 5 (medium/off)` — model·effort·thinking 3 items written together.
>
> 🔴 **Effort is a per-model capability, not just a per-Gate choice** (2026-09-24, verified against the
> official Models overview). **Haiku 4.5 does not support the effort parameter**, so a row that selects
> Haiku writes `—` for effort instead of `low`. Gate E defaults to Haiku, which is why that row is
> annotated above. Official defaults as of 2026-09-24: Fable 5.1 `high` · Opus 5.5 `medium` ·
> Sonnet 5 `high` · Haiku 4.5 unsupported. **Re-check by fetching the docs — do not assert from memory.**

### §5. Model Selection Criteria (reference summary, PROC-MODEL-RUBRIC-1 revision)

> The exact production uses **Step 0-A-a R/V/D 3-axis classification** + **Step 0-A-b per-Gate decision rule** + **Step 0-A-b' R-13 cost-justification guard**. This table is a summary for intuitive understanding of the result, not the scoring canonical.

| Model | Price (in/out per 1M) | Fit work | Default Gate mapping |
|-------|----------------------|----------|----------------------|
| Opus 5.5 | **$4 / $20** | Long-horizon agent · new architecture decision · science·math reasoning · high-resolution vision — **only when R items ≥ 2** | R≥6 only (A·B·D all) |
| Sonnet 5 | **$2 / $10** | **Standard coding implementation·verification·refactor (default)** · strict instruction following · smallest-diff consistency · **2× cheaper than Opus (output tokens: $10 vs $20)** · near-parity with Opus on general reasoning/knowledge work, still ~6–17pt behind on deep-coding/olympiad-math benchmarks | A·B·C·D default |
| Haiku 4.5 | $1 / $5 | Cleanup·labeling·repeated-pattern application·real-time response·orchestration worker (Anthropic official recommendation) | E always, B/C on downgrade |

> Switch command: `/model opus` · `/model sonnet` · `/model haiku`
> Fast mode: `/fast` (same model, faster output) — usable alongside Haiku work
> **Anthropic official recommended pattern**: decompose complex work into "Sonnet orchestrator + Haiku worker parallel" — more cost-efficient than mapping a single Opus to a single task. ([Haiku 4.5 announcement](https://www.anthropic.com/news/claude-haiku-4-5))

### §Fable 5.1 (exception escalation only, HARNESS-MODEL-ROUTING-1, 2026-07-06)

> **SSOT for Fable 5.1**: all other skill files (`CLAUDE.md`, `gate-a`, `audit`, `doc-cleanup`) reference this section rather than re-describing Fable 5.1 — edit here only.

- **Positioning**: per Anthropic's official docs, Fable 5.1 is "Anthropic's most capable widely released model, built for the most demanding reasoning and long-horizon agentic work" (Mythos-class). Despite the name, it is **not** a storytelling/creative-writing specialist model — that framing appears only in third-party marketing blogs, not in Anthropic's own positioning.
- **Absent from the official routing matrix**: Anthropic's "choosing a model" matrix lists only Opus 5.5 / Sonnet 5 / Haiku 4.5 as routing targets for coding/agentic/enterprise/cost-sensitive work. Fable 5.1 sits outside that matrix as a separate premium option.
- **Price**: $10 / $50 per 1M (in/out) — **2.5× Opus 5.5 ($4/$20)**, verified against the official
  pricing table on 2026-09-24. *(The pre-2026-09-24 text said "2× ($5/$25)"; that was the Opus 4.8-era
  price left behind when the model names were updated. Re-check prices when you re-check model names.)*
- **Benchmark edge**: a real capability edge exists on agentic coding benchmarks, but whether it justifies the price gap at single-developer session scale is unproven (no usage data yet). *(Benchmark figures are not repeated here — they go stale faster than this file is edited.)*
- **Harness rule (user decision, 2026-07-06)**: Fable 5.1 is **not** part of the regular R/V/D routing table for any Gate. Invoke it only when **both** conditions hold: (a) the task is a large-scale migration or a multi-day full-autonomy session, and (b) the user has explicitly approved the escalation in a sentence (e.g. 「Fable 5.1로 진행 승인」). It never appears as an auto-produced recommendation — only as a current-model value once the user has manually switched to it.
- **Basis**: (internal research note, if your project maintains one) (106-agent deep research, 2026-07-06).

## §Claim↔Evidence Cross-Check Background (HARNESS-CLAIM-EVIDENCE-1)

> Moved out of `gate-a/SKILL.md` on 2026-09-24 (HARNESS-CONTEXT-DIET-1). The **procedure** stays in
> gate-a; this is the *why*, which does not need to be re-read on every Gate A run.

**Why this check exists.** The three checks before it examine **the plan's content** (internal
consistency · external complement · minimality). This one examines **the epistemic status of the
plan's sentences**: a sentence you verified by opening a file and one you filled in by inference are
**indistinguishable in style**, so an inference error survives into Gate C as if it were fact.
It reuses the `gate-d/SKILL.md` "claim↔evidence cross-check" (technique-8) canonical, pulled forward
from the verification point to the planning point.

**Why immediately before Step 1 output.** Run it *after the plan's sentences already exist*.
Step 0 (Pre-Plan) decides *what to investigate* and is finished by then; it does not re-examine
sentences already written. That gap is what this check covers.

**Where it earns its cost.** Especially load-bearing in an unfamiliar repository: the less prior
context you have about a codebase, the more blanks get filled by inference — so this check pays off
most on new · rarely-touched repositories, not on the one you have been editing all week.

**Known limit (do not overstate).** This is a **self-check**, so it reduces the frequency of
inference errors — it does not replace a reviewer's explicit cross-verification request. The check
was introduced because its **own founding Gate A plan** self-reported 「ⓒ 0건」 while actually
containing 1 ⓒ (an insertion point written from structural inference without opening the line that
specified it). The `파일:줄` test is what caught it — which is both the evidence that the criterion
works and the reason the criterion must stay falsifiable.

## §Recommended-Model Computation (forced procedure, shared by gate-e → doc-cleanup / audit)

> Moved out of `gate-e/SKILL.md` on 2026-09-24 (HARNESS-CONTEXT-DIET-1). gate-e carried this
> 4–5 step procedure **twice** — once for doc-cleanup and once for audit — differing only in which
> skill's scoring table to apply. The shared steps live here; gate-e keeps the per-target differences.

When Gate E produces a recommended model for a follow-up skill, all of the following are mandatory:

1. **Shared scoring table** — apply the *target skill's* scoring table and grade-judgment table
   **directly to the current-point metadata**. This is not "delegation": it is **executing the shared
   canonical inside this response**.
2. **Measurement commands** — run the target skill's measurement commands directly in this response
   to secure the metadata. **No estimation, no omission.**
3. **R/V/D decomposition output obligation** — the 「R/V/D 분해: …」 line **must not show a total
   score** (R/V/D 3-axis independent decomposition obligation). Omitting the breakdown is a
   **PROC violation**.
4. **Sync guarantee** — the recommended model **must be re-computed with the same metadata and the
   same table when the target skill actually runs right after Gate E, and must yield the same
   result**. A mismatch means operator measurement error; the explicit score breakdown is what makes
   both responses traceable.

**Per-target differences** (stated at each call site in gate-e, not here):
the table section id, the command count/kind, and — for `audit` only — the current-model detection
obligation from the system context.
