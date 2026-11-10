---
name: gate-b
description: "Confirmation stop before a hard-to-undo change, after Gate A approval. Use on 'Gate B 시작', 'Gate B 진행', 'Gate A 승인', '계획대로 구현', '구현해라', etc."
effort: low
---

# Gate B Procedure — Confirmation before a hard-to-undo change (follow order strictly)

> **Purpose**: Between Gate A approval and Gate C, stop once before a change that is hard to undo so the user can review the direction — what cannot be taken back, where it breaks first, how to undo it. This is a **confirmation, not a quiz**: 「진행」 is a full answer. The 4-item briefing is already at the top of the dashboard for every plan; this gate only adds a stop where undoing is hard. A question comes only when the user asks for one. Why: all 13 questions after the 2026-11-05 narrowing were skipped, the user named time and habit, and said the gate exists for reviewing the work's direction (2026-11-10).
> **Location**: gate-a (produces trigger verdict) → **this gate** → gate-c (code implementation).

## Step 0. Does this plan stop here?

Run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/gate_b_trigger.py" "${CURRENT_SESSION_FILE}"`. It reads this plan's changed files and 「되돌리는 법」 and prints one line:

| Script output | Path |
|---------------|------|
| `발동 — …` | **Confirmation** (Step 2). You may not downgrade this verdict, and the ledger does not waive it. |
| `미발동 — …` | **Pass-through** — 1~2 line confirmation, proceed to gate-c. Add a confirmation only for something hard to undo that the script cannot see, and say what it is in one line. |
| `판정 불가 — …` | Apply the same rule yourself: stored data or schema, auth·permissions·payment, deploys, or anything already public → confirmation; otherwise pass-through. |

> Why a script: on 2026-10-20 a production migration was judged 「일반」 although migration was listed as the top risk class. A change git can revert gets no stop however wide it is — Gate D's real execution covers that.

> User override: 「스킵」 → pass-through; 「게이트 걸어줘」 → force the confirmation. **While the confirmation is pending, do not start gate-c until the user replies** — the `comprehension-pending-guard` hook blocks gate-c·d·e until the 평가 is written.

## Step 1. Ledger expiry·re-verification prerequisite lookup

**A 발동 verdict skips this Step and always stops** — the confirmation is about this plan, and a row from another plan does not cover it. Use this lookup only for a confirmation you add yourself on a 미발동 plan.

**Before** requiring an explanation, look up entries in the comprehension ledger (`comprehension_ledger.md` — see `.claude/harness-answers.yml` → `learning_path` (SSOT); absent field means `plans/learning`) by `tech_tags` match first, then fall back to `scope` text match:

- **tech_tags matching (primary)**: if any tag in the ledger row's `tech_tags` column overlaps with this Gate A plan's technology area → apply expiry check
- **Only a 결과 of Pass or Pass after retry is evidence.** A row with any other 결과 (「미답 — 사용자 스킵」, 「확인 — 진행」, 「피드백 후 진행」, User-delegated, 「힌트 후 통과」) counts as **No record**, however recent it is. Why: on 2026-10-29 a row recording a skip was read as 「유효」 about 26 minutes later, and a large-blast-radius change passed with no question.
- **Expiry verdict**:
  - **Not expired** (within exp AND no material change to scope files) → skip (pass the gate, record 1-line reason)
  - **Expired** (exp elapsed OR material change to scope files) → proceed with re-verification
  - **No record** → proceed with new verification

## Step 2. Confirmation (three lines, one stop)

Show three lines in the response and append the same block to the Gate B block of `${CURRENT_SESSION_FILE}` in that response (the dashboard shows it next to the briefing):

```
### 질문 1
되돌리기 전에 확인 — <the trigger line's reason, e.g. 운영 DB 스키마 변경>
- **가장 깨지기 쉬운 곳**: <from 이해 브리핑>
- **되돌리는 법**: <from 이해 브리핑>
- **읽을 곳**: 이해 브리핑 「가장 깨지기 쉬운 곳」·「되돌리는 법」
- **평가**: (filled after the answer)
```

If the plan has no briefing, write it into the Gate A block first (4 items, `gate-a/SKILL.md §Step 1`). 「읽을 곳」 names only what the dashboard shows — never line numbers.

## Step 3. The reply

- **「진행」「확인」「구현」 or similar** → 평가 `확인 — 진행`, pass the gate. This is the normal path; do not ask anything more.
- **A change or a concern** → handle it: fix the plan (back to gate-a if files or rollback change), or list the decision for the user. 평가 `확인 — 계획 변경` or `확인 — 질문에 답함`.
- **「질문해 줘」** → ask **one** question answerable in one line from the plan (what would have to be false for it to break, or what stays behind if undone). After the answer, reply in 1~2 lines: what matched, what the plan says where it differs, whether it exposes a gap. Do not re-ask. 평가 `답함 — <1-line feedback>`. Ban "know/don't-know" self-report — confidence in explaining is unreliable (Fisher & Keil 2016).
- Under every 평가 add one line: `- **계획 변경**: 있음 — <what changed>` or `- **계획 변경**: 없음`. The usage report counts confirmations, changes and questions — the data for keeping this stop or making it non-blocking.

## Step 4. Evidence record (expiring, answered questions only)

> **Skipped gate → no row.** If the gate ended on 「스킵」 or 「확인 — 진행」, write nothing to the ledger: the 평가 in the Gate B block is the whole record. The ledger holds only questions the user actually answered (Step 3 「질문해 줘」).

Add 1 row to the comprehension ledger (`comprehension_ledger.md` under `learning_path` — see Step 1):

| Field | Value |
|-------|-------|
| `verified` | Verification date (absolute date) |
| `tech_tags` | Comma-separated technology/library/system tags |
| `scope` | Verification scope (module/feature/file glob) |
| `exp` | Expiry condition (`N개월` or `{scope} 실질변경 시`) |
| 설명 주체 | User |
| 결과 | Pass (the answer matched the plan) / 피드백 후 진행 (the feedback corrected it — not evidence) |
| 설명 요약 | Core flow·break point, 1 line |

> Pass-through sessions: skip this Step.
> **Expiry default (first pass)**: the earlier of `3개월` or `해당 scope 파일 실질변경 시`.

## Step 5. Update the plan document(s) (status: `B (확인 대기)`) — **run the file-editing tool**

- Plan document(s) — tier-aware, see `SKILL_DETAIL.md §Plan-Doc Update Pattern`
- `${SESSION_INDEX_FILE}` YAML
- `${CURRENT_SESSION_FILE}` dashboard + Gate B block
  - The Gate B block keeps the confirmation (and any question) with its 「읽을 곳」 and 「평가」 (Step 2 format) — not just a pass/fail line.

6. STOP — await user document review·confirmation. **A 미발동 pass-through does not stop**: invoke `/gate-c` in this same response — the user has already approved the plan and there is nothing to read or answer (9 of 12 past rounds would have cost one more 「구현」 for nothing). Stop only if the session's 「Gate별 권장 모델」 table recommends a different model for Gate C than the one running now; switching model is the one thing this stop is for.

---

## This Gate response's mandatory final output

After completing the entire Gate B procedure (comprehension gate + plan document(s) update), output **one** of the blocks below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

**While the confirmation is pending** — do not start gate-c:

```
---
**다음 단계**: 위 세 줄을 확인하고 「진행」이라고 답하면 구현을 시작합니다. 묻고 싶은 것이나 바꿀 것이 있으면 그대로 적어 주세요 — 「질문해 줘」라고 하면 이해 확인 질문을 하나 냅니다.
```

**While a requested question is pending**:

```
---
**다음 단계**: 위 질문에 답해 주세요. 답하지 않고 넘어가려면 「스킵」이라고 적어 주세요.
```

**미발동 pass-through continuing to gate-c**: no block — gate-c's final output ends the response.

**Gate passed, explicitly skipped, or pass-through stopping for a model change** (after 「진행」 on a confirmation, go on to gate-c in the same response unless a model change is due):

```
---
**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「구현」으로 응답하면 `/gate-c` (Gate C 구현)가 시작됩니다.
**권장 모델 전환**: ${CURRENT_SESSION_FILE} "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
```
