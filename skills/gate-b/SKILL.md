---
name: gate-b
description: "Comprehension gate after Gate A approval. Use on 'Gate B 시작', 'Gate B 진행', 'Gate A 승인', '계획대로 구현', '구현해라', etc."
effort: low
---

# Gate B Procedure — Comprehension Gate (follow order strictly)

> **Purpose**: Structural comprehension check between Gate A approval → Gate C implementation. Before AI-written code runs, verify "how it flows end to end" via retrieval forced through guided questioning. Defense against AI-era cognitive debt (MIT 2025). Canonical: (internal research note, if your project maintains one) (original design) + (internal research note, if your project maintains one) (guided-questioning redesign, 2026-07-06).
> **Location**: gate-a (produces trigger verdict) → **this gate** → gate-c (code implementation).

## Step 0. 3-way risk classification

Classify the Gate A plan by risk level and determine the path:

| Risk level | Decision criteria | Path |
|------------|-------------------|------|
| **Large blast radius** | auth·authorization·payment·concurrency·transaction boundary·migration·security policy (CORS·token·RBAC) | **User explains** — before seeing AI code |
| **General risk** | new module·unfamiliar pattern·unfamiliar library·new algorithm/scoring | **AI self-explains** — user reviews |
| **Trivial** | formulaic CRUD·docs·smallest-diff repeated pattern·config-value change | **Pass-through** — 1~2 line confirmation, proceed to gate-c |

> User override: if the user explicitly states 「스킵」 → pass-through; 「게이트 걸어줘」 → force trigger. Ambiguous responses keep the AI auto verdict.

## Step 1. Ledger expiry·re-verification prerequisite lookup

**Before** requiring an explanation, look up entries in the comprehension ledger (`comprehension_ledger.md` — see `.claude/harness-answers.yml` → `learning_path` (SSOT); absent field means `plans/learning`) by `tech_tags` match first, then fall back to `scope` text match:

- **tech_tags matching (primary)**: if any tag in the ledger row's `tech_tags` column overlaps with this Gate A plan's technology area → apply expiry check
- **Expiry verdict**:
  - **Not expired** (within exp AND no material change to scope files) → skip (pass the gate, record 1-line reason)
  - **Expired** (exp elapsed OR material change to scope files) → proceed with re-verification
  - **No record** → proceed with new verification

> Automatic expiry detection (Stop hook `comprehension-ledger-stale-guard.py`) is non-blocking and notifies on response end — **only when that hook is actually wired in your Claude Code settings**. If it is not wired, this Step's manual lookup is the sole detection path. Either way, this Step's direct lookup is the first-pass verdict.

## Step 2. Force retrieval via guided questioning (non-trivial paths only)

**Ban "know/don't-know" Y/N self-report** (IOED·Dunning-Kruger). Force actual retrieval — the active ingredient is retrieval, not the dialogue format itself (Dunlosky 2013 meta-review: retrieval/spaced practice = high utility, free self-explanation = only moderate utility). Basis and evidence-strength ratings → (internal research note, if your project maintains one).

- **Large blast radius**: AI asks **2~4 questions, one at a time** (do not reveal the next question until the current one is answered — prevents reading-ahead gaming), **before the user sees AI-written code**. Question template: ①why is this change needed ②what is the core mechanism ③what is the most fragile break point ④(if relevant) how to roll it back. AI only evaluates — it does not answer for the user.
- **General risk**: AI asks **1~2 targeted questions** about the just-approved Gate A plan. (Previously this path had the AI self-explain with the user only reviewing — zero user retrieval. This is the structural fix.) If the user cannot answer, AI gives one hint and re-asks; if still stuck, AI states the answer and marks the row 「힌트 후 통과」.
- **Gaming guard**: an answer must cite a concrete file/line/mechanism from the Gate A plan (reuses gate-d's claim↔evidence cross-check principle). A generic answer ("이해했어요") does not pass — ask once more.
- **Trivial**: unchanged, pass-through.

## Step 3. Per-question evaluation → corrective loop on failure (no blocking)

Evaluate **each question's answer independently** (not one holistic free-form paragraph as before): does it cite a concrete file/mechanism, does it match the Gate A plan's actual content, is there a flow gap or an unrecognized break point.

- **All questions answered concretely** → record Step 4 evidence then pass the gate → proceed to gate-c
- **Gap found in ≥1 question** → **do not block**. Give one hint, re-ask that question once. If a gap remains after retry, delegate decision to user (proceed/further learning). Record which question(s) needed a retry in the evidence row's 설명요약.

## Step 4. Evidence record (expiring, non-trivial paths only)

Add 1 row to the comprehension ledger (`comprehension_ledger.md` under `learning_path` — see Step 1):

| Field | Value |
|-------|-------|
| `verified` | Verification date (absolute date) |
| `tech_tags` | Comma-separated technology/library/system tags |
| `scope` | Verification scope (module/feature/file glob) |
| `exp` | Expiry condition (`N개월` or `{scope} 실질변경 시`) |
| 설명 주체 | User / AI |
| 결과 | Pass / Pass after retry / User-delegated |
| 설명 요약 | Core flow·break point, 1 line |

> Pass-through (trivial) sessions: skip this Step.
> **Expiry default (first pass)**: the earlier of `3개월` or `해당 scope 파일 실질변경 시`. Large-blast-radius: `1개월`.
> **Expiry on re-verification pass (adaptive, SM-2-lite)**: when Step 1 found a matching `tech_tags` row that had expired and this session's re-verification **passes again**, set the new `exp` to roughly **double the previous row's exp value** (e.g. 3개월→6개월, 1개월→2개월), capped at `12개월`. No new column — parse the previous exp text, double the numeric part, write it into the new row. On a **failed** re-verification (retry needed or user-delegated), reset `exp` back to the first-pass default instead of doubling.

## Step 5. Update the plan document(s) (status: `B (확인 대기)`) — **run the file-editing tool**

- Plan document(s) — tier-aware, see `SKILL_DETAIL.md §Plan-Doc Update Pattern`
- `${SESSION_INDEX_FILE}` YAML
- `${CURRENT_SESSION_FILE}` dashboard + Gate B block
> **session-dashboard.html update**: `session-dashboard-sync.py` runs as the first Stop hook entry, auto-regenerating the HTML. No skill Bash Step needed.

6. STOP — await user document review·confirmation

---

## This Gate response's mandatory final output

After completing the entire Gate B procedure (comprehension gate + plan document(s) update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

```
---
**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「구현」으로 응답하면 `/gate-c` (Gate C 구현)가 시작됩니다.
**권장 모델 전환**: ${CURRENT_SESSION_FILE} "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
```
