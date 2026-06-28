---
name: gate-b
description: "Comprehension gate after Gate A approval. Use on 'Gate B 시작', 'Gate B 진행', 'Gate A 승인', '계획대로 구현', '구현해라', etc."
effort: low
---

# Gate B Procedure — Comprehension Gate (follow order strictly)

> **Purpose**: Structural comprehension check between Gate A approval → Gate C implementation. Before AI-written code runs, verify "how it flows end to end" via free-form explanation. Defense against AI-era cognitive debt (MIT 2025). Canonical: `05_PLATFORM_MODERNIZATION/REPORTS/HARNESS_RIGOR_RESEARCH_V1.md §2`.
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

**Before** requiring an explanation, look up entries in `plans/learning/comprehension_ledger.md` by `tech_tags` match first, then fall back to `scope` text match:

- **tech_tags matching (primary)**: if any tag in the ledger row's `tech_tags` column overlaps with this Gate A plan's technology area → apply expiry check
- **Expiry verdict**:
  - **Not expired** (within exp AND no material change to scope files) → skip (pass the gate, record 1-line reason)
  - **Expired** (exp elapsed OR material change to scope files) → proceed with re-verification
  - **No record** → proceed with new verification

> Automatic expiry detection (Stop hook `comprehension-ledger-stale-guard.py`) is non-blocking and notifies on response end. This Step's direct lookup is the first-pass verdict.

## Step 2. Force free-form explanation (non-trivial paths only)

**Ban "know/don't-know" Y/N self-report** (IOED·Dunning-Kruger). Force free-form explanation:

> **How it runs end to end + what could break, 3~6 sentences** (or "draw the data flow").

- **Large blast radius**: **the user** writes → **before** seeing AI code (generation-effect condition). AI only evaluates.
- **General risk**: **the AI** writes a self-explanation based on the Gate A plan → the user reviews.

## Step 3. Evaluation → corrective loop on failure (no blocking)

Inspect gaps in the explanation (flow omission·unrecognized break point·wrong premise):

- **Sufficient** → record Step 4 evidence then pass the gate → proceed to gate-c
- **Gap found** → **do not block**. Route to that area's learning doc → retry once. If a gap remains after retry, delegate decision to user (proceed/further learning).

## Step 4. Evidence record (expiring, non-trivial paths only)

Add 1 row to `plans/learning/comprehension_ledger.md`:

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
> Expiry default: the earlier of `3개월` or `해당 scope 파일 실질변경 시`. Large-blast-radius: `1개월`.

## Step 5. Update the 3 documents (status: `B (확인 대기)`) — **run the file-editing tool**

- `00_MODERNIZATION_MASTER_PLAN.md` §7
- `SESSION_INDEX.md` YAML
- `CURRENT_SESSION.md` dashboard + Gate B block
> **session-dashboard.html update**: `session-dashboard-sync.py` runs as the first Stop hook entry, auto-regenerating the HTML. No skill Bash Step needed.

6. STOP — await user document review·confirmation

---

## This Gate response's mandatory final output

After completing the entire Gate B procedure (comprehension gate + 3-document update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

```
---
**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「구현」으로 응답하면 `/gate-c` (Gate C 구현)가 시작됩니다.
**권장 모델 전환**: CURRENT_SESSION.md "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
```
