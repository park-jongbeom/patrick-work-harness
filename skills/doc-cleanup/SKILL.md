---
name: doc-cleanup
description: "Resolves session-document bloat and restores token optimization. Use via '/doc-cleanup' after a Gate E threshold-exceeded warning, or on '문서 정리', '토큰 최적화 복구' requests."
effort: low
---

# doc-cleanup Procedure (follow order strictly)

## Overview

Run when, after Gate E completion, the line counts of the 3 core documents exceed their thresholds.
Migrate completed-session details to the archive and restore active documents to the progressive-disclosure principle.

---

## Step 0-A — R/V/D 3-axis classification + model verification (mandatory, PROC-MODEL-RUBRIC-2 revision)

> **PROC enforcement**: This Step must be performed before the Step 0-B measurement. Proceeding past Step 0-B while ignoring this Step's STOP verdict is a **PROC violation**.
>
> **Single-canonical declaration**: This Step 0-A "doc-cleanup-specific R/V/D scoring" (0-A-a) + "tier verdict" (0-A-b) is the **shared canonical for doc-cleanup·gate-e**. The gate-e SKILL cites·applies this table directly.
> Philosophy, sources, estimation guide, and R-13 guard → `SKILL_DETAIL.md §Model Rubric Common` (not auto-loaded — load via `Read` when needed).

### Step 0-A-a. doc-cleanup-specific R/V/D 3-axis classification

**Measurement targets (5 metadata)** — measure directly with the 5 commands below, then substitute into the R/V/D items:

```bash
# (1) 4-document line counts
wc -l \
  ${CLAUDE_PROJECT_DIR}/CURRENT_SESSION.md \
  ${CLAUDE_PROJECT_DIR}/SESSION_INDEX.md \
  ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md \
  ${CLAUDE_PROJECT_DIR}/05_PLATFORM_MODERNIZATION/00_MODERNIZATION_MASTER_PLAN.md

# (2) §5 「즉시 처리 대상」 item count
awk '/^### 즉시 처리 대상/,/^### 의존 대기/' ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md | grep -c "^- \["

# (3) §5 「의존 대기」 item count
awk '/^### 의존 대기/,/^### 조건부/' ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md | grep -c "^- \["

# (4) §5 「조건부」 item count
awk '/^### 조건부/,/^---/' ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md | grep -c "^- \["

# (5) Index stale candidates (R-9 absorbed; assume 0 if Step 4-A not run)
#     Post-verify with the actual detected count after Step 4-A runs
```

> The 5 measured values above are produced by Bash execution **within this response**, and those numbers are substituted into the R/V/D items below. No estimation·omission.

#### R (Reasoning Depth) — Opus promotion gate

| Item | Definition | Score |
|------|------------|-------|
| R-D1 | §5 「외부 검증 필요 후보」 ≥ 3 items (user-explicit-response classification reasoning needed) | +3 |
| R-D2 | Index–canonical inconsistency (Step 4-A-d) ≥ 1 (canonical-decision reasoning) | +3 |
| R-D3 | Suspect candidates (Step 6) ≥ 5 (delete·move user-approval classification reasoning) | +3 |

> **R total ≥ 6 (= 2+ items)** → Opus 4.8 candidate. 0 items = standard slimming (most doc-cleanup calls land here).

#### V (Volume) — Sonnet ↔ Haiku branch signal

| Item | Measurement basis | Score |
|------|-------------------|-------|
| V-D1 | (1) Number of the 4 documents over threshold — 1 +1 / 2~3 +2 / 4 +3 | +1~3 |
| V-D2 | §5 reclaim-target items ((2)+(3)+(4)) 1~3 +0 / 4~7 +1 / 8+ +2 | +0~2 |
| V-D3 | §7/§5 slimming fired (double-count absorbed) — `MODERNIZATION_MASTER_PLAN.md > 700 lines` or `00_MASTER_PLAN.md > 450 lines` 1 +1 / 2 +2 | +0~2 |

> **Double-count rule (V-D3 absorption)**: The old separate counts of #3·#4 are absorbed into V-D3 as a single item. When §7 slimming fires, V-D1 (over threshold +1) + V-D3 (slimming fired +1) = total +2 (differs from the old +5 — since single scoring is abolished, sum comparison is meaningless; R/V/D are evaluated independently).
>
> **#5 (index stale) handling**: Per detection in the Step 4-A scan, do not add to V-D2's item count (preserve only the PLAN-SYNC-N session-retirement absorption effect; V measures only call volume). Index stale is auto-corrected·recorded in Step 4-A.

#### D (Determinism / Format Strictness) — Sonnet forcing gate

| Item | Definition | Score |
|------|------------|-------|
| D-D1 | Fixed slimming pattern (Step 1~3·5 — category ### preservation guard + threshold-based branch) | +1 |
| D-D2 | Fixed output format (Step 7 result table) | +1 |
| D-D3 | Many reclaim·delete guards (permanent-record 2 sub-sections preserved·preserve-first when ambiguous·external-verification separated) | +1 |

> **D total ≥ 2** → Sonnet forced (Opus promotion blocked). doc-cleanup is also inherently D=3 (all 3 items satisfied) — fixed slimming·fixed output·reclaim guards are the SKILL definition itself. Hence a standard call with R = 0 is **always Sonnet default**, and Opus promotion is considered only when an R-D* item fires.

### Step 0-A-b. doc-cleanup per-Gate model decision rule

doc-cleanup is a single-SKILL one-shot run, so there is no Gate branching. Decision rule:

| Decision priority | Condition | Recommended model |
|-------------------|-----------|-------------------|
| (1) | R ≥ 6 (2+ R-D items) | **Opus 4.8** |
| (2) | R = 0 + V ≤ 1 + D ≥ 2 (most standard slimming) | **Haiku 4.5** (D forces Sonnet as default, but if R=0+V≤1 the simple fixed slimming allows Haiku downgrade) |
| (3) | otherwise (R = 0~3 + V ≥ 2) | **Sonnet 4.6 (default)** |

> **Revision meaning**: The old "total ≤3 = Haiku, 4~8 = Sonnet, 9+ = Opus" + "double-count" single mapping is abolished. R/V/D 3-axis independent measurement separates "complex classification reasoning (R)" from "over-threshold volume (V)" — Opus only when R fires.

### Step 0-A-b'. R-13 cost-justification guard

> R-13 guard (Opus output format·auto-downgrade conditions·STOP format) → `SKILL_DETAIL.md §3` (not auto-loaded — load via `Read` when needed). Note: use `{R-D 항목}` prefix in the Opus output format line when citing doc-cleanup-specific R items.

### Step 0-A-c. Current-model detection + Step 0-A-d. STOP verdict

Apply the **same procedure** as `audit/SKILL.md` Step 0-c / Step 0-d (single canonical). Format·bypass handling·detection-failure handling are all identical. However, the R/V/D decomposition output uses the doc-cleanup-specific item names (R-D1~D3 / V-D1~D3 / D-D1~D3).

Summary:
- Current tier ≥ recommended → proceed normally (to Step 0-B). Output 1 line at the start of this response: 「✅ 모델 검증: 현재 {모델} ≥ 권장 {권장} (R={항목 1줄 또는 0} / V={점수 분해} / D={항목 1줄})」.
- Current tier < recommended → STOP. Output the same format (only the R/V/D decomposition item names are doc-cleanup-specific). (a) on approval, proceed to Step 0-B + a final 1-line bypass record / (b) re-invoke after `/model` switch.

> **Decomposition output obligation**: Output the **R/V/D 3-axis decomposition** in the first line of this response. Showing only the total·omitting the decomposition is a **PROC violation**. When producing Opus, the R-13 cost-justification 1 line is also mandatory (Step 0-A-b' format).

> **R-12 self-contradiction avoidance (memo)**: The doc-cleanup SKILL itself is fixed slimming, so it is not a direct target of the R-12 guard (changed files ≤ 7 / Step ≤ 5). However, the "1-line entry principle" for the Step 1-b §5 append·Step 4-b reclaim is kept (no multi-line entries — inheriting the gate-a R-12 spirit).

---

## Step 0-B — Measure current line counts and identify over-threshold items

Measure the line counts of the 4 documents below and output a result table:

| Document | Threshold | Current lines | Over? |
|----------|-----------|---------------|-------|
| `CURRENT_SESSION.md` | 100 lines | ? | ? |
| `SESSION_INDEX.md` | 80 lines | ? | ? |
| `00_MASTER_PLAN.md` | 450 lines | ? | ? |
| `05_PLATFORM_MODERNIZATION/00_MODERNIZATION_MASTER_PLAN.md` | 700 lines | ? | ? |

→ **If nothing is over threshold, run only Step 4-A (index stale scan) + Step 4 (§5 reclaim verification) and finish**. Step 4-A·Step 4 run on every call regardless of threshold (preventing index-stale + handoff-stale accumulation). If all pass, output "임계 정리 불필요 — Step 4-A·Step 4만 수행".

---

## Step 1 — CURRENT_SESSION.md slimming (including handoff preservation)

**Condition**: Run only when over 100 lines.

> **Responsibility separation from Gate E (SRP)**:
> - This Step **deletes the CURRENT_SESSION.md body (completed Gate A~D blocks)**.
> - The original of the deleted body must already have been copied to `plans/current_work/archive/session_history/ARCHIVE_*.md` by Gate E Step 2 (a Gate E preceding precondition).
> - **User-notice obligation**: At the end of the Step 7 result output, always include 1 line 「슬림화된 본문 원본은 archive 참조: {경로}」 so the user can trace the Gate E output location.
> - **Reason**: 2026-04-27 user feedback — when doc-cleanup runs right after Gate E, the CURRENT_SESSION.md body disappears and causes the misunderstanding "did Gate E not happen?". The archive-path notice secures location traceability.

Rather than **simply deleting** the completed session's Gate blocks, first migrate items affecting follow-up sessions to the index (`00_MASTER_PLAN.md §5 인수인계 메모`), then delete. Preventing handoff omission is the core purpose of this Step.

### Step 1-a: Extract handoff items

From the completed Gate A~E blocks, extract content matching the **patterns** below:

| Pattern | Example phrase |
|---------|----------------|
| **FIX-B** | 「FIX-B」「FIX-B 1건 발견」「다음 세션에서 수정」 |
| **DEP** | 「DEP」「의존: <세션ID>」「선행 필요」 |
| **후속/차기** | 「후속」「차기 세션」「다음 세션에서」「후속 작업」 |
| **보류/차단** | 「보류」「차단」「연기」「블로커」 |
| **미해결** | 「미해결」「미완」「추후」 |

Simple completion summaries·test-pass counts·past progress history are **not extraction targets** (delete only).

### Step 1-b: Classify and append to §5 handoff notes

Classify each extracted item by dependency:

| Classification | Criterion | §5 placement sub-section |
|----------------|-----------|--------------------------|
| **Immediate** | Processable right away in the next session | 「즉시 처리 대상」 |
| **의존:<세션ID>** | Possible after a preceding session reaches ✅E | 「의존 대기」 |
| **조건부:<조건>** | After an external condition (Docker up·API implemented, etc.) is met | 「조건부」 |
| **Permanent record (no retroactive recording)** | archive physically absent + after-the-fact creation prohibited | 「⚠️ 영구 기록 (사후 소급 금지 — archive 물리 파일 부재)」 |
| **Decision permanent record** | Decision traceability (boss-meeting decisions, etc.; kept even after follow-up ✅E) | 「✅ 결정사항 영구 기록 (의사결정 추적성 — 후속 트랙 ✅E 후에도 유지)」 |

> **Sub-section operation rule**: Use only the 5 sub-sections above. No creating arbitrary new sub-sections like 「즉시 처리 대상 (추가)」. When items accumulate, add to the same sub-section, and when over the 450-line threshold, process via Step 5 (§5 slimming).

**Append** to `00_MASTER_PLAN.md §5 인수인계 메모` in the format below (no replacing existing items):

```markdown
- [YYYY-MM-DD / 원세션ID] 항목 제목
  - 유형: FIX-B | DEP | 후속 | 보류
  - 원인: 1줄 요약
  - 대응 방향: 1~2줄
  - 분류: 즉시 / 의존:<세션ID> / 조건부:<조건>
```

**Duplicate avoidance**: Before appending, if §5 already has an item with the same original-session-ID·same title, do **update only**; do not create a new row.

### Step 1-c: Delete completed blocks

Once handoff migration is done, delete the entire completed Gate A~E blocks. Keep only the current session's dashboard + active Gate block.

- Target: ≤ 90 lines
- **The migrated count is recorded in the Step 5 result output**

---

## Step 2 — SESSION_INDEX.md slimming

**Condition**: Run only when over 80 lines.

- YAML header: from the `sessions` array, remove all `gate: ✅E` completed-session entries, keep only current/upcoming sessions
- Body table: remove completed rows (`✅E`), keep only current·upcoming rows
- Target: ≤ 40 lines

---

## Step 3 — 00_MODERNIZATION_MASTER_PLAN.md §7 slimming

**Condition**: Run only when over 700 lines.

### Delete targets / preserve targets (guard)

§7's `###` sub-sections are of **two kinds**, and the two are clearly distinguished.

| Kind | Identification criterion | Handling |
|------|--------------------------|----------|
| **Category ###** (preserve) | A grouping sub-section that contains a table (session table). Title includes a category noun like 「체인」「정리」「Phase」「계획」 (e.g. `### Post-MVP 정리`, `### MEETING-ALIGN 체인`, `### Phase 2 매칭 품질`, `### MATCH-QUALITY-3 체인 분할`) | **Always preserve** — including its 1-line summary table |
| **Completed-session detail ###** (delete) | A standalone sub-section for a single session ID. Title is in session-ID form (e.g. `### MATCH-QUALITY-3-c 완료`, `### DEMO-DATA-9 결과 상세`) | Delete entirely |

> **Preserve-first when the verdict is ambiguous** — if you can't tell whether it's a category or a single-session detail, don't touch it. Deleting wrongly can erase an in-progress session row entirely.

### Handling

- Leave the **category ###** in the table above as-is, including its 1-line summary table.
- Delete only the **completed-session detail ###** blocks in the table above.
- After deletion, add once:
  > 세션 상세 내용은 `plans/current_work/archive/session_history/` 참조
- Target: ≤ 450 lines

---

## Step 4-A — Index canonical stale scan (R-9, runs every call regardless of threshold)

> **Introduction background**: 2026-05-04 HARNESS-OPTIMIZE-1-b-1. The PLAN-SYNC-1~5 (5 repetitions total) sessions were issued to correct stale between the `00_MASTER_PLAN.md` index §2(priority)/§3(active tracks)/§4(next action) markings and the canonical (`SESSION_INDEX.md` table·latest archive `final_status`). This Step absorbs that work and ends the separate session issuance.

### Step 4-A-a: Extract check targets

Use the command below to extract session IDs marked with an incomplete marker (「⏸/⏳/🟡/구현 진입 예정/구현 진행/대기」 etc.) within index §2/§3/§4.

```bash
# Candidate session IDs marked incomplete in the §2 priority + §3 active tracks + §4 next action area
awk '/^## 2\./,/^## 5\./' ${CLAUDE_PROJECT_DIR}/00_MASTER_PLAN.md \
  | grep -oE '(⏸|⏳|🟡)[^|]*[A-Z][A-Z0-9-]+' \
  | grep -oE '[A-Z][A-Z0-9-]+(-[a-z0-9-]+)*' \
  | sort -u
```

### Step 4-A-b: Canonical cross-verification

For each extracted session ID, confirm against these two canonicals via grep:

| Canonical | grep pattern | Verdict |
|-----------|--------------|---------|
| `SESSION_INDEX.md` table | `\| {세션ID} \|.*✅E` | If ✅E, index-stale candidate |
| Latest archive | `find ${HARNESS_PLANS_DIR}/current_work/archive/session_history -name "ARCHIVE_*_{세션ID}.md"` then `grep "^final_status:"` | If `✅ E` or `✅E`, index-stale confirmed |

> **Stale is confirmed only when both canonicals are ✅E.** If only one is ✅E, the canonicals themselves are inconsistent → await user-explicit decision (Step 4-A-d).

### Step 4-A-c: Stale correction (automatic)

Per stale-confirmed item:
1. The incomplete marker (⏸/⏳/🟡 etc.) on the relevant line of `00_MASTER_PLAN.md` §2/§3/§4 → replace with ✅E + append the completion date
2. After correction, grep-verify consistency (whether an incomplete marker remains near that session ID)

> Do not newly register the correction trace anywhere — neither on the corrected line nor in §5 「✅ 결정사항 영구 기록」 — index correction is routine sync work with low after-the-fact tracking value, so avoid noise accumulation.

### Step 4-A-d: When canonical inconsistency is found

When `SESSION_INDEX.md` and the latest archive are marked in different states (only one ✅E, etc.):
- Register 1 line 「인덱스-정본 비정합: 세션 {ID}」 in the Step 7 result output's 「§5 외부 검증 필요 후보」 block
- No auto-correction — only correct on the next call when the user responds explicitly with 「정본 결정: <정본 위치>」

### Step 4-A-e: Record result

Record the detected count and corrected count in the Step 7 result output's 「인덱스 스테일 정정 (R-9)」 item:
```
인덱스 스테일 정정 (R-9): N건 자동 정정 / M건 외부 검증 필요
```

> **PLAN-SYNC-N session retirement**: After this Step's introduction, no new issuance of PLAN-SYNC-N (N=6 or more) session IDs. If an issuance attempt is found, absorb it via a doc-cleanup call.

---

## Step 4 — §5 reclaim verification (runs every call regardless of threshold)

Iterate over all items in `00_MASTER_PLAN.md §5 인수인계 메모` and reclaim by the rules below. Run on every call regardless of threshold (preventing stale accumulation is the core purpose of this Step).

### Step 4-a: Identify reclaim targets

Judge by each item's 「분류」 field. **Conditional** splits into **two** depending on whether the SKILL can judge it automatically.

| Classification | Verdict procedure | Handling |
|----------------|-------------------|----------|
| `의존:<세션ID>` | Confirm whether that session is `✅E` in `SESSION_INDEX.md` | If ✅E, reclaim as "의존 해소" (Step 4-b) |
| `조건부:<조건>` **(auto-judgeable)** | Only when the condition is grep-confirmable — session ✅E·production deploy·Flyway migration·archive creation, etc. grep a clue from SESSION_INDEX·archive·WORKLOG | When a satisfaction clue is found, reclaim as "조건 해소" |
| `조건부:<조건>` **(external verification needed)** | Line threshold·locale activation·user behavior·external operational state, etc., conditions the SKILL cannot judge by grep alone | **Do not touch** — reclaim only when the user responds explicitly with 「§5 회수 승인: 항목명」 |
| `즉시` | grep the follow-up session ✅E archive·WORKLOG for a processing trace | Reclaim when a processing trace is found |
| `영구 기록` (⚠️) | **Not** a reclaim target — never delete |
| `결정사항 영구 기록` (✅) | **Not** a reclaim target — never delete |

> **Auto-judgeable vs external-verification-needed distinction examples**:
> - Auto: `조건부:PRIORITY-WEIGHT-1 ✅E 후` / `조건부:V23 Flyway 적용 후` / `조건부:JAR 배포 완료 후 (WORKLOG 단서)`
> - External: `조건부:라인 임계 초과 시` / `조건부:다른 locale 활성화 시점` / `조건부:사용자 수동 검증 후`

### Step 4-b: Reclaim handling

How to handle a reclaim-target item (one of two):
- **Delete**: an item a follow-up session has fully processed to ✅E → delete the entire line
- **Mark RESOLVED + preserve once**: an item with decision·recurrence-prevention value (ledger-type item) → add `→ ✅ RESOLVED (해소 세션 ID, YYYY-MM-DD)` to the item's first line; delete on the next doc-cleanup call

> **When the verdict is ambiguous, don't touch it** — at a clue-shortage·interpretation fork, do neither reclaim nor RESOLVED marking. Re-evaluate on the next call. The "ambiguous = preserve" principle holds because allowing 1 cycle of §5 bloat is safer than a handoff omission.

> **External-verification-needed items are not auto-processed in this Step** — only output 1 line in the Step 7 result output's 「§5 외부 검증 필요 후보」 block, and reclaim only after receiving user-explicit approval as a separate response.

### Step 4-c: Record result

Record the reclaimed count in the Step 7 result output's 「§5 회수」 item.

---

## Step 5 — 00_MASTER_PLAN.md §5 slimming

**Condition**: Run only when over 450 lines.

- The 2 sub-sections within §5, 「⚠️ 영구 기록」 and 「✅ 결정사항 영구 기록」, **must be kept**
- In the 「즉시 처리 대상」「의존 대기」「조건부」 sub-sections, delete all items marked RESOLVED in Step 4-b
- Target: ≤ 500 lines

> The body of §6 and below (document-structure guidance, etc.) is not changed in this Step.

---

## Step 6 — Unnecessary-file cleanup (conditional, safety guard)

For files matching the conditions below, **do not delete·move; output only as suspect candidates**. Process only when the user responds explicitly with 「삭제 승인」「이동 승인」.

| Condition | Handling (after user approval) |
|-----------|-------------------------------|
| File with only a redirect (body ≤ 3 lines + only a reference to another file) | Delete |
| Completed plan document (title includes a date, content already merged into the master plan) | Move to `archive/` |

Output format:
```
[의심 후보] {경로} — 사유: {1줄}  → 처리 제안: 삭제 | 이동
```

→ If there are no suspect candidates, skip this Step.

---

## Step 7 — Result verification and output

Re-measure line counts after the change and output in the following format:

```
## doc-cleanup 결과

| 문서 | 이전 | 현재 | 감소 |
|------|------|------|------|
| CURRENT_SESSION.md | N줄 | N줄 | -N줄 (-X%) |
| SESSION_INDEX.md | N줄 | N줄 | -N줄 (-X%) |
| 00_MASTER_PLAN.md | N줄 | N줄 | -N줄 (-X%) |
| 00_MODERNIZATION_MASTER_PLAN.md | N줄 | N줄 | -N줄 (-X%) |
| **합계** | **N줄** | **N줄** | **-N줄 (-X%)** |

인수인계 이관: N건 → `00_MASTER_PLAN.md §5` (즉시 N / 의존 N / 조건부 N)
§5 회수: N건 (삭제 N / RESOLVED 표시 N)
인덱스 스테일 정정 (R-9): N건 자동 정정 / M건 외부 검증 필요
§5 외부 검증 필요 후보 (사용자 명시 승인 대기): (없으면 "없음")
  - [YYYY-MM-DD / 원세션ID] 항목 제목 — 조건: <외부 조건>
의심 후보 (사용자 승인 대기): (없으면 "없음")

슬림화된 본문 원본 (Gate E archive 참조):
  - {세션ID}: plans/current_work/archive/session_history/ARCHIVE_YYYY-MM-DD_{세션ID}.md
  (Step 1에서 CURRENT_SESSION.md 본문을 삭제한 경우만 출력. 미삭제 시 "본문 슬림화 없음" 출력)
```

---

## Threshold-adjustment guidance

Adjust thresholds directly in this file (`SKILL.md`) Step 0-B table.
Adjustment basis: average added lines per session × allowed session count.
Current baseline (4 documents):
- CURRENT_SESSION.md 100 lines (+50~80 lines/session, slim at 1-session end)
- SESSION_INDEX.md 80 lines (+1~2 lines/session, slim after ~30 sessions accumulated)
- 00_MASTER_PLAN.md 450 lines (§4 log·completed chains·§5 handoff accumulation — +0~3 lines/session. In HARNESS-RESEARCH-5(2026-05-25), the 600-line threshold failed to catch 507-line bloat, so lowered to 450)
- 00_MODERNIZATION_MASTER_PLAN.md 700 lines (§7 session table — +1~5 lines/session, after ~20~50 sessions)

---

## This Skill's mandatory final output

After completing the entire doc-cleanup procedure, output the block below at the **very end** of the response.

```
---
**doc-cleanup 완료**: 토큰 최적화 원칙(progressive disclosure) 복구됨.
다음 세션은 `SESSION_INDEX.md`의 `next_action` 항목을 확인하세요.
```
