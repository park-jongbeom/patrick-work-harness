---
name: gate-e
description: "WORKLOG recording, session cleanup, and archiving after Gate C or Gate D confirmation. Use on 'Gate E', 'WORKLOG', '세션 정리', 'C~E 일괄', 'D~E 일괄', etc."
effort: low
---

# Gate E Procedure (follow order strictly)

---

1. **WORKLOG record** — add to the top of `${HARNESS_PLANS_DIR}/tasks/worklog/YYYY-Www.md` in the format below:
   ```
   ## YYYY-MM-DD | Claude | 작업 한줄 요약
   **요청 내용**: ...
   **변경 파일**: - `경로/파일.tsx` — 이유
   **핵심 변경**: 무엇을 왜 어떻게
   **검증 방법**: docker exec ... npm test
   **재사용 후보**: 이번 세션에서 반복된 시행착오·결정 중 다음 세션이 재활용할 만한 것을 1~2줄로 추출. 없으면 "없음".
   ```

   > The "재사용 후보" block is the ECC pattern-extraction (L1) deliverable. Prefer "없음" over meaningless repetitive entries.

2. **Long-form archive** — **newly create (copy)** the session Gate A~E body to `${HARNESS_PLANS_DIR}/current_work/archive/session_history/ARCHIVE_날짜_세션ID.md`.

   > **Separation of responsibility (SRP)**:
   > - **Gate E's responsibility**: create the new archive file + update the 3 documents (SESSION_INDEX·MASTER_PLAN §7·CURRENT_SESSION dashboard).
   > - **Gate E's non-responsibility**: **do not delete** the CURRENT_SESSION.md body (completed Gate A~D blocks). When the threshold (100 lines) is exceeded, a separate `/doc-cleanup` SKILL slims it down.
   > - **Reason**: Right after Gate E, the user must be able to review the Gate A~E flow as-is in CURRENT_SESSION.md. If the body disappears, the misunderstanding 「Gate E가 안 됐나?」 arises (reflecting 2026-04-27 user feedback).
   > - **User guidance**: After the Step 5 update, the archive path·WORKLOG path must be noted in this response's final output (securing location traceability).

### 2-B. Layer 2 document status finalization (if `--docs=full` was used at `/init`)

If `DOC_INDEX.md` exists at the target repo root:
- Review each Layer 2 row's `Status`:
  - If a document was expected to be filled by this session's gates but remains `Skeleton` → mark `Partial` with a note `(not filled — no applicable content this session)`
  - If all gates for this session have filled their sections → mark `Complete`
- This is the final DOC_INDEX.md touch for this session — subsequent sessions start fresh from the current status.
- If `DOC_INDEX.md` does not exist: skip silently.

3. **Error-case storage** (conditional) — perform the procedure below directly in this turn. (An inline copy of the same procedure as the `/error-log` Skill — that skill is not auto-loaded, so perform the below directly in this response. No separate load needed.)

   **Judgment**: Check the items below in the `CURRENT_SESSION.md` Gate B~D blocks:
   - Gate B build·type·runtime failure / Gate C FIX-B / Gate D re-verification failure / Docker·environment·permission retry
   - There is "value for the next session to reuse" (excluding simple typo·one-off mistakes)

   → **If there is no target, output "오류 기록 대상 없음 — 생략" and proceed to Step 4.**

   **Canonical location** (managed independently per repository):
   - `<code-repo>/docs/rules/error_topics/` for each repo listed in `.claude/harness-answers.yml → code_repos`
   - Each folder's `README.md` is the topic index (canonical). Do not write to the ledger `../error_analysis.md`.
   - Docs-only repos (no entry in `code_repos`) → record in the `error_topics/gate_process.md` of the code repository that this session worked on.

   **Topic file mapping** (common to the three repositories):
   | File | Tag | Target error |
   |------|-----|--------------|
   | `gate_process.md` | `PROC` | Gate approval·procedure·「구현」 interpretation·after-the-fact retroactive |
   | `runtime_env.md` | `ENV` | Docker/container/npm·gradle·pytest/lockfile/permission/path |
   | `git_commit.md` | `PROC` | commit message·git operation |
   | `testing.md` | `TYPE` `VERIFY` `LOGIC` | type·build·test failure·CI verification |
   | `security_schema.md` | `SEC` `API` | XSS·token·axios·API contract·DB schema |

   If the topic does not fit the existing 5 files, **create a new topic file + add 1 row to that repository's `error_topics/README.md` table**.

   **Append format** (append as a date section at the bottom of the relevant topic file):
   ```
   ## [YYYY-MM-DD] 세션ID — 한줄 요약
   - **발생 Gate**: B / C / D
   - **증상**: (로그·메시지 핵심 1~3줄)
   - **근본 원인**: 무엇이 왜 틀렸는가
   - **해결**: 파일·라인 포함 변경점
   - **재발 방지 규칙**: 다음 세션이 지켜야 할 1줄 규칙
   ```

   > No creating a new document per session — always append to an existing topic file.

4. **FIX-B / DEP handoff** — process Gate C's FIX-B·DEP items at the source in the same turn:
   - FIX-B item → register as a master plan §7 or next-session Gate A candidate
   - Next-session decision → record in the `SESSION_INDEX.md` YAML `next_action` field
   - `SESSION_INDEX.md` YAML `sessions_since_audit += 1`
   - ※ **The session-status ✅E flip is performed in bulk at Step 5, not this step** — preventing Step 4/5 duplication (GATE-E-ENFORCE-1)
   - ⛔ **No counter value in prose (AUDIT-COUNTER-STALE-FIX-1)**: Do not copy the `sessions_since_audit` **number or the `=N → /audit 권장` phrase** into the `next_action`·`priority_note`·`CURRENT_SESSION.md` 「다음 행동」 prose. Whether to recommend audit is announced by ② below, which reads the canonical YAML and **outputs only in this response** (a number baked into prose goes stale immediately after the audit reset → misleads the next session. The same recurring incident is recorded in the SESSION_INDEX YAML comment·HARNESS_EVOLUTION_LOG PLAN-SYNC-21). If a recommendation must be left in prose, only the qualitative expression 「⚡ /audit 권장(정본 YAML 기준)」 without a number is allowed.

4-B. **§5 handoff retrieval** (conditional) — If there is an item pulled into this session's scope from §5 at Gate A 0-A, confirm the processing trace and delete that line from `00_MASTER_PLAN.md §5`.

   - If there is no pulled-in item, skip this step.
   - The 「⚠️ 영구 기록」「✅ 결정사항 영구 기록」 subsections are not retrieved at Gate E (absolute preservation).
   - The retrieval is performed together in this response turn.

5. **3-document ✅E status flip** (same response turn) — update all 3 documents below to ✅E. **The status flip is this step's single responsibility** (no duplication with Step 4):

   **(a) `00_MODERNIZATION_MASTER_PLAN.md` §7** — that session's row status → `✅E (날짜, 핵심지표)`

   **(b) `SESSION_INDEX.md` YAML** — that session's `gate:` → `✅E (...)`

   **(c) `CURRENT_SESSION.md`** — update **all** of ①②③ below (PROC violation if even one is omitted):
   - ① Header block `> **현재 상태**:` → `✅E 완료 (날짜)`
   - ② Dashboard table `| 현재 Gate |` → `✅E 완료`
   - ③ Dashboard table `| Gate 진행 |` row → the last `E☐`/`E⏳` to `E✅`

   **Self-verification (mandatory)**: Right after the update, run `grep -c "✅E" CURRENT_SESSION.md` → confirm result ≥ 2 (header + dashboard). If less, re-check ②③.
   > **session-dashboard.html update**: `session-dashboard-sync.py` always runs as the first entry of the `Stop` hook array, reading the ✅E `CURRENT_SESSION.md`·`SESSION_INDEX.md` from the previous Step 5 and auto-regenerating the HTML (HARNESS-STALE-GUARD-3). No skill Bash Step needed. Separation of responsibility: the Stop hook `gate-e-sync-guard.py` is the ✅E consistency guard, `session-dashboard-sync.py` is the HTML-deliverable sync — separate responsibilities, and dashboard-sync is fail-open so it does not affect the guard behavior.

> **Enforcement device**: Omitting this Step 5(c) is detected by `plans/hooks/gate-e-sync-guard.py` (Claude Code `Stop` hook) as a SESSION_INDEX ↔ CURRENT_SESSION ✅E mismatch, blocking response termination (GATE-E-ENFORCE-1).
> Splitting content output and document update across different turns is a PROC violation.

---

## This Gate response's mandatory final output

After completing the entire Gate E procedure (WORKLOG + archive + 3-document update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

**Output order**: ① **Gate E 산출물 위치** → ② 문서 상태 요약 → ③ audit 권장 여부 → ④ 세션 완료 안내

**① Gate E deliverable location** — After Gate E completion, output the deliverable paths explicitly so the user can trace the result. This is the key output for preventing user misunderstanding, so do not omit it:

```
── Gate E 산출물 위치 ──────────────────────
  archive (장문 본문) : ${HARNESS_PLANS_DIR}/current_work/archive/session_history/ARCHIVE_YYYY-MM-DD_{세션ID}.md
  WORKLOG            : ${HARNESS_PLANS_DIR}/tasks/worklog/YYYY-Www.md (line N~M)
  3문서 갱신 (✅E)    : SESSION_INDEX.md · 00_MODERNIZATION_MASTER_PLAN.md §7 · CURRENT_SESSION.md 대시보드
  CURRENT_SESSION.md : 본문(Gate A~D 블록) 보존됨 — 슬림화는 별도 /doc-cleanup 호출 시 수행
────────────────────────────────────────────
```

> Explicitly stating that the CURRENT_SESSION.md body is preserved makes the user aware that 「Gate E 결과를 그대로 검토 가능」.

**② Document status summary** — Right after Gate E completion, measure the 4 document line counts and apply doc-cleanup Step 0-A 「공유 산정 표」 directly to the current-point metadata to compute the score·grade·recommended model. Output in the format below:

```
── 문서 상태 ──────────────────────────────
  CURRENT_SESSION.md          : N줄  (임계값 100줄) ✅ / ⚠️ 초과
  SESSION_INDEX.md            : N줄  (임계값  80줄) ✅ / ⚠️ 초과
  00_MASTER_PLAN.md           : N줄  (임계값 450줄) ✅ / ⚠️ 초과
  00_MODERNIZATION_MASTER_PLAN: N줄  (임계값 700줄) ✅ / ⚠️ 초과
────────────────────────────────────────────
  ⚠️ 초과 항목 있음 → `/doc-cleanup` 실행을 권장합니다.
     권장 모델: {Haiku/Sonnet/Opus} ({등급})
     R/V/D 분해: V-D1 4문서초과 +N / V-D2 §5 항목 N건 +N / V-D3 §7>700·00_MASTER>450 +N / D-D 정형 슬림화 +N
  (또는 모두 이하) → 문서 상태 정상
────────────────────────────────────────────
```

> **Recommended-model computation (forced procedure)**:
> 1. **Shared scoring table**: Apply the `doc-cleanup/SKILL.md §Step 0-A-a` table (including the double-add rule) and the §0-A-b grade-judgment table **directly to the current-point metadata** to compute. Not "delegation" but **executing the shared canonical in this response**.
> 2. **Measurement commands**: Run doc-cleanup §0-A-a's 4 Bash commands (wc + 3× awk|grep) directly in this response to secure the metadata. No estimation·omission.
> 3. **R/V/D decomposition output obligation**: The 「R/V/D 분해: …」 line **must not show a total score (R/V/D 3-axis independent decomposition obligation)** — omitting the breakdown is a **PROC violation**.
> 4. **Sync guarantee**: This recommended model **must, when doc-cleanup is called right after Gate E, be re-computed with the same metadata·same table at Step 0-A and yield the same result**. If different, operator measurement error → both responses traceable via explicit score breakdown.

**③ audit recommendation judgment** (SESSION_INDEX YAML single source):

Judge based on the `sessions_since_audit` field of the `SESSION_INDEX.md` YAML header (the value right after += 1 at Step 4). **The judgment·recommendation is performed only in this response output, and the counter number is not recorded in persistent-document prose** (same principle as Step 4 「카운터 값 서술 금지」 — the canonical YAML is the sole source).
- `sessions_since_audit ≥ 3` → output recommendation
- `last_audit_date` field absent (first time) → output recommendation
- **Chain-transition·priority-change point** (e.g. last ✅E of the MEETING-ALIGN chain → entering the next chain, MVP Phase transition, `00_MASTER_PLAN.md §2` priority-table update) → unconditionally output recommendation

When recommending:
```
⚡ 직전 /audit 이후 {sessions_since_audit}개 세션 완료 — `/audit` (방향성 점검) 호출을 권장합니다.
   권장 모델: {Haiku/Sonnet/Opus} ({등급})
   R/V/D 분해: §5 즉시 N건 +N / DEP 재검증 N건 +N / 체인 전환 +N / sessions_since_audit N +N
   {현재 모델이 권장보다 낮으면}: ⚠️ 현재 {현재모델} < 권장 {권장모델} — `/model {권장}` 전환 후 `/audit` 호출하세요.
   {현재 모델이 권장 이상이면}: ✅ 현재 {현재모델} ≥ 권장 — 바로 `/audit` 호출 가능
```

> **Recommended-model computation (forced procedure)**:
> 1. **Shared scoring table**: Apply the `audit/SKILL.md §Step 0-a` table (audit-specific scoring table) and the §0-b grade-judgment table **directly to the current-point metadata** to compute. Not "delegation" but **executing the shared canonical in this response**.
> 2. **Measurement commands**: Run audit §0-a's 5 measurement commands (grep + 2× awk|grep + operator judgment) directly in this response to secure the metadata. No estimation·omission.
> 3. **R/V/D decomposition output obligation**: The 「R/V/D 분해: …」 line **must not show a total score (R/V/D 3-axis independent decomposition obligation)** — omitting the breakdown is a **PROC violation**.
> 4. **Current-model detection obligation**: From the system context (`You are powered by the model named {모델명}` format), extract the model-family keyword (Opus / Sonnet / Haiku). Compare the detected current model with the recommended model, substitute into the output format's `{현재모델}` / `{권장모델}` slots, and output only the relevant guidance line depending on whether the model falls short (one of ⚠️ or ✅).
> 5. **Sync guarantee**: This recommended model **must, when `/audit` is called right after Gate E, be re-computed with the same metadata·same table at Step 0-a and yield the same result**. If different, operator measurement error → both responses traceable via explicit score breakdown.

If not applicable, omit this block.

**④ Session completion guidance**:

```
---
**세션 완료**: 다음 세션은 `SESSION_INDEX.md`의 `next_action` 항목을 확인하세요. 새 작업 시작 시 `/gate-a` (Gate A 계획)로 시작합니다.
```
