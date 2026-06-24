---
name: comprehend-gate
description: "Risk-based comprehension gate between Gate A approval and Gate B start. Use on 'comprehend-gate', '이해도 게이트', '이해도 확인', or when the gate-a trigger decision is '발동'."
effort: medium
---

# Comprehension Gate Procedure (Gate A↔B, COMPREHEND-GATE-1)

> **Purpose**: Insert a risk-based comprehension check between Gate A approval → immediate Gate B, so that before implementing AI-written code, "how it runs end to end" is verified by free-form explanation. Defense against AI-era cognitive debt (MIT 2025) + generation/self-explanation effect. Canonical: `05_PLATFORM_MODERNIZATION/REPORTS/HARNESS_RIGOR_RESEARCH_V1.md §2`.
> **Location**: gate-a (produces the trigger verdict) → **this gate** → gate-b (code implementation). Non-triggered sessions skip this gate.
> **4 principles (research §2-3 corrections)**: ① ban "know Y/N" → force free-form explanation ② risk-based **selective** triggering (no all-gating·avoid rubber-stamping) ③ on failure, **not block** but route to learning then retry ④ evidence is **expiring** (date·scope stamped).

---

## Step 0. Trigger verdict (3-way risk classification)

Classify gate-a's produced 「이해도 게이트 발동 판정」 (AI auto + user override) by risk level:

| Risk level | Decision criteria | Explainer |
|--------|----------|----------|
| **Large blast radius** | auth·authorization·payment·concurrency·transaction boundary·migration·security policy (CORS·token·RBAC) | **User explains** (before seeing AI code) |
| **General risk** | new module·unfamiliar pattern·unfamiliar library·new algorithm/scoring | **AI self-explains** (user reviews) |
| **Trivial** | formulaic CRUD·docs·smallest-diff repeated pattern·config-value change | **Not triggered — pass** (skip this gate) |

> User override: if the user explicitly states 「스킵」 in the gate-a trigger line → pass; 「게이트 걸어줘」 → force trigger. Ambiguous responses keep the AI auto verdict.

## Step 1. Ledger expiry·re-verification prerequisite lookup

**Before** requiring an explanation, look up the same `scope` entry in `plans/learning/comprehension_ledger.md`:

- **Not expired** (within exp **AND** no material change to scope files) → **skip** (do not ask again). Pass the gate·record a 1-line reason
- **Expired** (exp elapsed **OR** material change to scope files occurred) → **proceed with re-verification** (spaced re-retrieval = memory reinforcement·two birds with one stone)
- **No record** → proceed with new verification

> Automatic expiry detection (Stop hook) is implemented by **COMPREHEND-GATE-1-b** (2026-06-21 ✅) — `plans/hooks/comprehension-ledger-stale-guard.py` notifies on response end of exp (`N개월`) date elapse in a **non-blocking** way (does not block termination). This Step's direct lookup remains the first-pass verdict at gate trigger, and material change to scope files is excluded from automation due to the absence of git → manual verdict in this Step.

## Step 2. Force free-form explanation

**Ban "know/don't-know" Y/N self-report** (IOED·Dunning-Kruger — those who know least pass most). Force free-form explanation in the format below:

> **How it runs end to end + what could break, 3~6 sentences** (or "draw the data flow").

- **Large blast radius**: **the user** writes → **before** seeing AI code (generation-effect condition). AI only evaluates the explanation.
- **General risk**: **the AI** writes a self-explanation based on the Gate A plan → the user reviews (isomorphic to the author explaining logic in code review).

## Step 3. Evaluation → corrective loop on failure (no blocking)

Inspect gaps in the explanation (flow omission·unrecognized break point·wrong premise):

- **Sufficient** → record Step 4 evidence then pass the gate → proceed to gate-b
- **Gap found** → **do not block**. Route to that area's learning doc (`plans/learning/{repo}/flows/{feature}.md` or the relevant code·canonical) → retry once. mastery learning corrective loop. If a gap remains after the retry, delegate the decision to the user (proceed/further learning).

## Step 4. Evidence record (expiring)

Add 1 row to the `plans/learning/comprehension_ledger.md` table:

| Item | Value |
|------|-----|
| `verified` | Verification date (absolute date) |
| `scope` | Verification scope (module/feature/file glob) |
| `exp` | Expiry condition (`N개월` or `{scope} 실질변경 시`) |
| 설명 주체 | User / AI |
| 결과 | Pass / Pass after retry / User-delegated |
| 설명 요약 | Core flow·break point, 1 line |

> Evidence is an **AI-track deliverable** — separate from Human Track `own_work/` (one's own direct work). This ledger is exclusive to gate-triggered sessions.

---

## After passing the gate

Gate passed (or not triggered) → proceed to `/gate-b` code implementation.

> **Expiry default guide**: when exp is unspecified, the earlier of `3개월` or `해당 scope 파일 실질변경 시`. Large-blast-radius areas use a short `1개월` (forgetting curve·high risk).
