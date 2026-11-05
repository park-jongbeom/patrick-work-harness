---
name: gate-b
description: "Comprehension gate after Gate A approval. Use on 'Gate B 시작', 'Gate B 진행', 'Gate A 승인', '계획대로 구현', '구현해라', etc."
effort: low
---

# Gate B Procedure — Comprehension Gate (follow order strictly)

> **Purpose**: Check between Gate A approval → Gate C implementation: before AI-written code runs, can the user say how this change flows end to end? This is a **pre-implementation check on this plan, not skill training**. The plan stays open while the user answers, so a question works as open-book guided re-reading: it shows the plan was read and can expose a gap in it. We found no study showing that answering here carries over to debugging or catching AI mistakes, so do not claim it builds or keeps skill. Why the check exists: taking AI output directly lowers what people learn from new material (Shen & Tamkin 2026, arXiv:2601.20245: N=52, d=0.738 on an immediate quiz; Bastani et al. 2025, PNAS: ~1,000 students, −17% once the AI was removed). Whether experienced developers lose skill they already have has not been measured.
> **Location**: gate-a (produces trigger verdict) → **this gate** → gate-c (code implementation).

## Step 0. Does this plan get a question?

Run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/gate_b_trigger.py" "${CURRENT_SESSION_FILE}"`. It reads this plan's changed files and 「되돌리는 법」 and prints one line:

| Script output | Path |
|---------------|------|
| `발동 — …` | **One question** (Step 2). You may not downgrade this verdict, and the ledger does not waive it. |
| `미발동 — …` | **Pass-through** — 1~2 line confirmation, proceed to gate-c. Add a question only for something hard to undo that the script cannot see, and say what it is in one line. |
| `판정 불가 — …` | Apply the same rule yourself: stored data or schema, auth·permissions·payment, deploys, or anything already public → one question; otherwise pass-through. |

> Why a script: on 2026-10-20 a production migration was judged 「일반」 although this gate's table listed migration as its top risk class. Why so few questions: of 10 question rounds only 1 was answered to the end, and the user named time and habit as the reasons (2026-11-05). A change git can revert gets no question however wide it is — Gate D's real execution covers that.

> User override: if the user explicitly states 「스킵」 → pass-through; 「게이트 걸어줘」 → force trigger. Ambiguous responses keep the AI auto verdict.
>
> **A question is pending → an implementation phrase is neither an answer nor a skip.** If a question asked in Step 2 has no evaluation yet and the user replies 「구현」「진행」「Gate C 시작」 or the like, do **not** start gate-c and do **not** record it as skipped. Re-ask once in one line: the question stands, and proceeding without answering needs an explicit 「스킵」. Only 「스킵」 (or an answer) moves the gate; then record the 평가 as 「미답 — 사용자 스킵」. Why: the old final-output line told the user to reply 「구현」 to go on, so a pending question was skipped by that one word — the recurring 「Gate B 스킵」 pattern (2026-10-15 real use).

## Step 1. Ledger expiry·re-verification prerequisite lookup

**A 발동 verdict skips this Step and is always asked** — the question is about this plan, and a row from another plan does not cover it. Use this lookup only for a question you add yourself on a 미발동 plan.

**Before** requiring an explanation, look up entries in the comprehension ledger (`comprehension_ledger.md` — see `.claude/harness-answers.yml` → `learning_path` (SSOT); absent field means `plans/learning`) by `tech_tags` match first, then fall back to `scope` text match:

- **tech_tags matching (primary)**: if any tag in the ledger row's `tech_tags` column overlaps with this Gate A plan's technology area → apply expiry check
- **Only a 결과 of Pass or Pass after retry is evidence.** A row with any other 결과 (「미답 — 사용자 스킵」, 「피드백 후 진행」, User-delegated, 「힌트 후 통과」) counts as **No record**, however recent it is. Why: on 2026-10-29 a row recording a skip was read as 「유효」 about 26 minutes later, and a large-blast-radius change passed with no question.
- **Expiry verdict**:
  - **Not expired** (within exp AND no material change to scope files) → skip (pass the gate, record 1-line reason)
  - **Expired** (exp elapsed OR material change to scope files) → proceed with re-verification
  - **No record** → proceed with new verification

## Step 2. One question

**Ban "know/don't-know" Y/N self-report.** Confidence in being able to explain is unreliable, and expertise raises that confidence without grounds (illusion of explanatory depth; Fisher & Keil 2016). Require an actual answer.

- **Ask one question**, before the user sees AI-written code: what would have to be false for this plan to break, or what stays behind if it is undone. Draw it from the Gate A plan's `### 이해 브리핑` — 「가장 깨지기 쉬운 곳」 or 「되돌리는 법」. Ask about **one thing**, answerable in one line and from the plan alone — a question with three parts costs what three questions cost. AI only evaluates — it does not answer for the user. If the plan has no briefing, write it into the Gate A block first (4 items, `gate-a/SKILL.md §Step 1`), then ask.
- **Record the question when you ask it** — append it to the Gate B block of `${CURRENT_SESSION_FILE}` in the same response, so the dashboard (regenerated on Stop) already shows it when the user opens it to answer:

  ```
  ### 질문 1
  <question text>
  - **읽을 곳**: 이해 브리핑 「<label>」 (optionally + a `###` section title of this session's Gate A block)
  - **평가**: (filled after the answer)
  ```

  「읽을 곳」 must name something **visible on the dashboard** — a briefing label or a `###` title. **Never line numbers**: the dashboard shows none and they drift when the document is edited. If the session file holds more than one plan, say which one (「이번 세션 Gate A의 …」) — in HARNESS-DASH-LEARN-1-a question 2, the pointer 「실행 순서 5」 matched the section 「5. 실행 순서」 of another plan in the same file and the user answered from that plan. Never write the answer before the user answers.

## Step 3. Feedback, no pass bar (no blocking)

Compare the answer with the plan and reply in 1~2 lines: what matched, what the plan actually says where it differs, and whether the answer exposes a gap in the plan. Give that feedback even when the answer is thin. **Do not re-ask and do not add a second question.** Correcting a wrong answer is where the value is; repeating the question is what made rounds take 7~23 minutes.

- **The answer exposes a real gap** → fix the plan, or list the gap for the user if the fix is a decision.
- **Then** write the 평가 (`답함 — <1-line feedback>`), record Step 4 and pass the gate. Stop at Step 5 so the user can read the feedback.
- **Record whether the answer changed the plan** — under the 평가 add one line: `- **계획 변경**: 있음 — <what changed>` or `- **계획 변경**: 없음`. A skipped question gets no such line. The usage report counts these: they are the data for deciding whether this gate earns its cost.

## Step 4. Evidence record (expiring, answered questions only)

> **Skipped gate → no row.** If the gate ended on 「스킵」, write nothing to the ledger: the 평가 「미답 — 사용자 스킵」 in the Gate B block is the whole record. The ledger holds only what the user actually answered.

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
  - The Gate B block keeps every asked question with its 「읽을 곳」 and 「평가」 (Step 2 format) — not just a pass/fail line.
> **session-dashboard.html update**: a hook regenerates the HTML automatically — `session-dashboard-sync.py` runs on `PostToolUse` (Edit|Write) in plugin and install.sh installs, and as the first `Stop` entry in projects wired by `/init` (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

6. STOP — await user document review·confirmation. **A 미발동 pass-through does not stop**: invoke `/gate-c` in this same response — the user has already approved the plan and there is nothing to read or answer (9 of 12 past rounds would have cost one more 「구현」 for nothing). Stop only if the session's 「Gate별 권장 모델」 table recommends a different model for Gate C than the one running now; switching model is the one thing this stop is for.

---

## This Gate response's mandatory final output

After completing the entire Gate B procedure (comprehension gate + plan document(s) update), output **one** of the blocks below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

**While a question is pending** (asked, no evaluation yet) — do not point to gate-c:

```
---
**다음 단계**: 위 질문에 답해 주세요. 답하지 않고 넘어가려면 「스킵」이라고 명시해 주세요 — 「구현」「진행」만으로는 넘어가지 않습니다.
```

**미발동 pass-through continuing to gate-c**: no block — gate-c's final output ends the response.

**Gate passed, explicitly skipped, or pass-through stopping for a model change**:

```
---
**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「구현」으로 응답하면 `/gate-c` (Gate C 구현)가 시작됩니다.
**권장 모델 전환**: ${CURRENT_SESSION_FILE} "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
```
