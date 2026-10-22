---
name: SKILL_DETAIL
description: "Shared model-rubric detail + plan-doc update pattern for gate-a~e, audit, doc-cleanup. Load on demand (not auto-loaded). Reference via Read when R-13 guard, Effort/Thinking rule, tier-aware plan-doc update wording, or the lane-routing limits and evidence (§Lane Routing) are needed."
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
> Basis: Anthropic's official selection matrix, 2026-10-15 (Opus 5.5=complex agentic coding·large refactors · Sonnet 5.5=everyday coding and agentic tool use · Haiku 5.5=lowest latency and price, sub-agent tasks · Fable 5.1=highest capability, hours-long agent sessions)·METR multi-axis capability research·Anthropic's official recommended "Sonnet orchestrator + Haiku worker" pattern·deep-research findings on the current 4-model lineup ((internal research note, if your project maintains one)).
> Sources: [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) · [Choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model) · [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) · [METR Time Horizon by Domain](https://metr.org/blog/2025-07-14-how-does-time-horizon-vary-across-domains/)

### §2. Estimation Guide

**Estimation guide**:
- The old "assume the upper bound / when tier is ambiguous go one step up" bias rule is **abolished** (a cause of systematic Opus bias).
- R items are qualitative — **if ambiguous, score 0** (conservative on Opus promotion, cost-saving).
- V is measured as-is. D is +1 only when there is an explicit requirement.
- When ambiguous, the model **converges to Sonnet default** (median balance).

### §3. R-13 Cost-Justification Guard (PROC-MODEL-RUBRIC-1/2)

> **PROC enforcement**: When producing an Opus 5.5 recommendation, **listing the R items in one line is mandatory**. Producing Opus while R = 0 is a PROC violation. If the **2× output-token cost vs Sonnet ($20 vs $10 per 1M, Opus 5.5 : Sonnet 5.5, verified 2026-09-24)** is not justified by R items, auto-downgrade to Sonnet.

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

### §4. Effort Decision Rule (PROC-MODEL-EFFORT-1)

> **Purpose**: Specify per-Gate the effort level independently of model selection.
> **Basis** (2026-10-15): every current model uses adaptive thinking steered by effort, and Opus 5.5 / Fable 5.1 reject
> `thinking: disabled` with a 400 error ([Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)) — so the old Thinking column (auto/off) no longer maps to a
> setting and is removed. Anthropic: "Tuning effort is often a better lever than switching models" ([choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)).

| Gate | Task character | Effort |
|------|----------------|--------|
| **A** (plan) | R≥2 new architecture decision | high |
| **A** (plan) | R=0 standard plan | medium |
| **B** (comprehension) | gate fires (question drafting·answer judging) | medium |
| **C** (implement) | D≥1 deterministic output (smallest diff·format) | medium |
| **C** (implement) | R≥2 unresolved-decision delegation | high |
| **D** (verify) | API/DB/SEC coupling·self-debug | medium |
| **D** (verify) | Simple regression re-confirm | low |
| **E** (cleanup) | always | low |

> **When an R≥2 item must be resolved**: raise effort (`high`, then `xhigh`) rather than asking for visible reasoning.
> **Dashboard notation**: `C: Sonnet 5.5 (medium)` — model and effort written together.
>
> 🔴 **Defaults are per model** (2026-10-15, verified against the official Models overview): Fable 5.1 `high` ·
> Opus 5.5 `medium` · Sonnet 5.5 `high` · Haiku 5.5 `medium`. All four accept effort (the legacy Haiku 4.5 did not).
> **Re-check by fetching the docs — do not assert from memory.** The previous table stayed two generations behind
> twice (Opus 4.8·Fable 5, then Sonnet 5·Haiku 4.5).

### §5. Model Selection Criteria (reference summary, PROC-MODEL-RUBRIC-1 revision)

> The exact production uses **Step 0-A-a R/V/D 3-axis classification** + **Step 0-A-b per-Gate decision rule** + **Step 0-A-b' R-13 cost-justification guard**. This table is a summary for intuitive understanding of the result, not the scoring canonical.

| Model | Price (in/out per 1M) | Fit work | Default Gate mapping |
|-------|----------------------|----------|----------------------|
| Opus 5.5 | **$4 / $20** | Long-horizon agent · new architecture decision · science·math reasoning · high-resolution vision — **only when R items ≥ 2** | R≥6 only (A·B·D all) |
| Sonnet 5.5 | **$2 / $10** | **Standard coding implementation·verification·refactor (default)** · everyday coding and agentic tool use (official matrix) · strict instruction following · smallest-diff consistency · **2× cheaper than Opus 5.5 (output tokens: $10 vs $20)** | A·B·C·D default |
| Haiku 5.5 | from $0.10 / $0.50 | Cleanup·labeling·repeated-pattern application·real-time response·sub-agent tasks (official matrix) | E always, B/C on downgrade |

> Switch command: `/model opus` · `/model sonnet` · `/model haiku`
> Fast mode: `/fast` (same model, faster output) — usable alongside Haiku work
> **Multi-model patterns** (official): an executor that escalates hard decisions to an advisor, or an orchestrator that delegates bulk work to lower-cost workers ([choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model) → Combine models). When the work is one dependent chain, "the orchestrator's model alone at lower effort came out ahead in every case measured" — "tune one model before you add a second" ([Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)).

### §Fable 5.1 (exception escalation only, HARNESS-MODEL-ROUTING-1, 2026-07-06)

> **SSOT for Fable 5.1**: all other skill files (`CLAUDE.md`, `gate-a`, `audit`, `doc-cleanup`) reference this section rather than re-describing Fable 5.1 — edit here only.

- **Positioning**: per Anthropic's official docs, Fable 5.1 is "Anthropic's most capable widely released model, built for the most demanding reasoning and long-horizon agentic work" (Mythos-class). Despite the name, it is **not** a storytelling/creative-writing specialist model — that framing appears only in third-party marketing blogs, not in Anthropic's own positioning.
- **In the official selection matrix** (corrected 2026-10-15 — the earlier "absent from the matrix" was wrong): Fable 5.1 is the row for "the highest available capability" (hours-long agent sessions, multistep deep research). Anthropic's rule is to move to it only when Opus 5.5 at `xhigh`/`max` effort still falls short ([choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)).
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

## §Why the Old Model-Routing Rules Were Abolished (PROC-MODEL-RUBRIC-1/2)

> Moved out of `gate-a/SKILL.md` on 2026-09-24 (HARNESS-CONTEXT-DIET-1). These explain **why the
> current rules replaced older ones**. The rules themselves stay in gate-a; only the "what it
> replaced" history lives here, because it is needed when someone questions the design — not on
> every Gate A run.

- **"Gate B = same model as A" auto-inheritance — abolished (PROC-MODEL-RUBRIC-1).** Each Gate is
  scored independently, so an Opus Gate A does not drag Gate B up with it. Gate B defaults to
  Sonnet per Anthropic's official coding positioning.
- **"Task complexity (L·M·H) → recommended model" single mapping — abolished (PROC-MODEL-RUBRIC-2).**
  A one-dimensional complexity label cannot stay consistent with R/V/D 3-axis scoring: two tasks
  with the same "M" can differ on every axis. The 3-axis format also makes a follow-up Gate's model
  verification **re-scorable with the same metadata**, which a collapsed label cannot support.

---

## §Lane Routing (review · autonomous)

> Canonical detail for `gate-a/SKILL.md §0-Lane` (added 2026-10-22). The trigger table and the
> block format stay in gate-a; the settings, defaults and evidence live here.
>
> **Status**: the lane-scope guard and the autonomous-lane procedure ship in v1.11.0. Until a
> project wires that guard, 0-Lane's entry condition (2) fails and every plan takes the review lane.

**Settings** — `.claude/harness-answers.yml`, read at the base commit (`git show HEAD:…`), never from
the working tree, so a running session cannot loosen its own policy (the same principle as a
protected default branch):

```yaml
autonomous_lane:
  enabled: false        # opt-in; absent = false
  max_files: 5          # files in the real diff, untracked files and both sides of a rename included; new test files excluded
  max_lines: 200        # Gate A's estimate must stay under this (added + deleted, new tests included)
  hard_max_lines: 400   # the real diff is never accepted above this
  protected_paths: []   # added to the defaults below; never replaces them
```

**Default protected paths**: dependency manifests and lock files; `**/migrations/**` and schema files;
auth/security code; CI (`.github/`, `.gitlab-ci.yml`, `Jenkinsfile`); hooks (`.husky/`, `.git/hooks/`);
`.claude/`; `.env*`; every test file that already exists at the base commit.

**Why these numbers.** 5 files and 200 lines are starting values chosen from this harness's own
session archive (599 sessions: 74% already touched ≤ 5 files), not a cited standard. External
references point the same way: Google's review guide calls ~100 lines reasonable and 1,000 too
large ([small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html)); across
~33k agent-authored PRs, merged and unmerged PRs differed more by lines changed than by file count
([Ehsani et al.](https://arxiv.org/abs/2601.15195)). Declared plan sizes undercount — in 100
archived sessions with both numbers, 14 grew past the plan — so the guard counts the real diff.

**Why these triggers** (where a change lands matters more than how big it is):

| Trigger | Evidence |
|---|---|
| Security · auth · secrets | ~40% of Copilot-generated programs in security-relevant scenarios were vulnerable ([Pearce et al.](https://arxiv.org/abs/2108.09293)); AI-assisted users wrote less secure code and believed it more secure ([Perry et al.](https://arxiv.org/abs/2211.03622)) |
| Schema · migration · stored data | 63% of upgrade failures surfaced only in production ([Zhang et al., SOSP '21](https://www.cs.purdue.edu/homes/yonglezh/pub/upgrade-sosp21.pdf)) |
| Destructive · irreversible | `git revert` cannot undo applied migrations, deleted data, external side effects or pushed secrets |
| Dependency manifests | package-name hallucination: 5.2% (commercial) and 21.7% (open) of suggested packages did not exist ([Spracklen et al.](https://arxiv.org/abs/2406.10279)) |
| Verification apparatus | an agent that may edit its own tests can pass by weakening them — the reason `test-write-guard.py` exists |
| R items · ambiguity | no external evidence validates model-scored reasoning risk, so the rule uses categories, not scores, and sends ambiguity to review |

**Tie rule.** R scoring leans low on purpose (「애매하면 0점」) to save model cost. Lane routing must
lean the other way, or ambiguous work drifts into the autonomous lane.

**Fail-closed reading.** `session_dashboard_parsers.parse_lane_decision` returns 검토 for a missing
section, a blank field, a lane value other than 자율, any trigger, a non-hash base commit, no
backticked acceptance command, or a file entry without a `` `path` ``. Every other parser in the
dashboard fails open; this one decides whether the autonomous lane opens, so it must not.
