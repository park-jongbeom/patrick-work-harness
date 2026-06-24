---
name: SKILL_DETAIL
description: "Shared model-rubric detail for gate-a, audit, doc-cleanup. Load on demand (not auto-loaded). Reference via Read when R-13 guard or Effort/Thinking rule is needed."
---

# Skill Common Model Rubric Detail

> **Load-on-demand** — this file is NOT auto-loaded. Load it explicitly via `Read` when the R-13 cost-justification guard, Effort/Thinking rule, or PROC-MODEL-RUBRIC rationale is needed during a Gate response.
> **Canonical home**: this file is the single source for the 4 shared sections below. Skill-specific R/V/D item tables and model decision rules remain inline in each skill.

---

## §Model Rubric Common

### §1. PROC-MODEL-RUBRIC Philosophy and Sources

> **Revision (PROC-MODEL-RUBRIC-1/2, 2026-05-06)**: Single-score summation → tier mapping abolished. Model is decided by **3-axis independent measurement** (R / V / D).
> Basis: Anthropic official positioning (Sonnet 4.6=coding mainstay·Opus 4.8=long horizon·science reasoning·Haiku 4.5=1/3 the cost of Sonnet coding)·METR multi-axis capability research·Anthropic's official recommended "Sonnet orchestrator + Haiku worker" pattern.
> Sources: [Anthropic Opus 4.8](https://www.anthropic.com/news/claude-opus-4) · [Sonnet 4.6](https://www.anthropic.com/news/claude-sonnet-4-6) · [Haiku 4.5](https://www.anthropic.com/news/claude-haiku-4-5) · [METR Time Horizon by Domain](https://metr.org/blog/2025-07-14-how-does-time-horizon-vary-across-domains/)

### §2. Estimation Guide

**Estimation guide**:
- The old "assume the upper bound / when tier is ambiguous go one step up" bias rule is **abolished** (a cause of systematic Opus bias).
- R items are qualitative — **if ambiguous, score 0** (conservative on Opus promotion, cost-saving).
- V is measured as-is. D is +1 only when there is an explicit requirement.
- When ambiguous, the model **converges to Sonnet default** (median balance).

### §3. R-13 Cost-Justification Guard (PROC-MODEL-RUBRIC-1/2)

> **PROC enforcement**: When producing an Opus 4.8 recommendation, **listing the R items in one line is mandatory**. Producing Opus while R = 0 is a PROC violation. If the ~1.67× output-token cost vs Sonnet ($25 vs $15 per 1M, current-gen Opus:Sonnet 4.6) is not justified by R items, auto-downgrade to Sonnet.

**Opus recommendation output format**:

```
> 💰 비용 정당화 (R-13): R{N}건 ({R 항목 1줄 나열}) — Sonnet 대비 약 1.67× 비용 정당화. 미충족 시 Sonnet 다운그레이드.
```

**Auto-downgrade conditions**:

- **R = 0 + Opus produced** → **PROC violation**, force-downgrade to Sonnet + output STOP format
- **R = 1 (single item, score 3) + Opus produced** → 1-line warning + recommend downgrade to user (not forced — borderline case)
- **R ≥ 2 (score 6+) + Opus produced** → normal

**Example (normal)**:
> 💰 비용 정당화 (R-13): R 2건 (R1 신규 도메인 모델 + R3 매칭 가중치 신규 알고리즘) — Sonnet 대비 약 1.67× 비용 정당화.

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
| **E** (cleanup) | always | low | off |

> **Thinking=auto condition**: only when an R≥2 item actually needs to be resolved. If D≥1, prefer thinking=off (CoT over-elaboration conflicts with deterministic output).
> **Dashboard notation**: `B: Sonnet 4.6 (medium/off)` — model·effort·thinking 3 items written together.

### §5. Model Selection Criteria (reference summary, PROC-MODEL-RUBRIC-1 revision)

> The exact production uses **Step 0-A-a R/V/D 3-axis classification** + **Step 0-A-b per-Gate decision rule** + **Step 0-A-b' R-13 cost-justification guard**. This table is a summary for intuitive understanding of the result, not the scoring canonical.

| Model | Price (in/out per 1M) | Fit work | Default Gate mapping |
|-------|----------------------|----------|----------------------|
| Opus 4.8 | $5 / $25 | Long-horizon agent · new architecture decision · science·math reasoning · high-resolution vision — **only when R items ≥ 2** | R≥6 only (A·B·D all) |
| Sonnet 4.6 | $3 / $15 | **Standard coding implementation·verification·refactor (default)** · strict instruction following · smallest-diff consistency · ~1.67× cheaper than Opus (output tokens) | A·B·C·D default |
| Haiku 4.5 | $1 / $5 | Cleanup·labeling·repeated-pattern application·real-time response·orchestration worker (Anthropic official recommendation) | E always, B/C on downgrade |

> Switch command: `/model opus` · `/model sonnet` · `/model haiku`
> Fast mode: `/fast` (same model, faster output) — usable alongside Haiku work
> **Anthropic official recommended pattern**: decompose complex work into "Sonnet orchestrator + Haiku worker parallel" — more cost-efficient than mapping a single Opus to a single task. ([Haiku 4.5 announcement](https://www.anthropic.com/news/claude-haiku-4-5))
