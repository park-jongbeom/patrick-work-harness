---
name: gate-d
description: "Verification after Gate C implementation (test plan + execution + FIX-B/DEP + optional refactor). Use on 'Gate D', '검증', '테스트', 'Gate D 시작', 'D~E 일괄', etc."
effort: high
---

# Gate D Procedure (follow order strictly)

## Permanent DEP Ledger (mandatory lookup at Gate D start)

**At Gate D start** → first consult `CLAUDE_DETAIL.md §Permanent DEP Ledger` (a project file — skip this section if your project has none):
- If the current failure matches a ledger entry → no new investigation needed, classify as DEP immediately
- If a dependent session has reached ✅E completion → **mandatory re-verification**, then update the entry

## 3-A. Test Plan·Execution·Failure Classification

> Header added 2026-09-24 (HARNESS-CONTEXT-DIET-1). Steps 1–3 below used to sit **under the DEP-ledger
> heading with no heading of their own**, so the ledger lookup (3 lines) and Gate D's main procedure
> (~5,000 chars) measured as one 5,042-char section. Same content, correct boundary.

1. **After reading all files changed in Gate C**, output the test plan as text — the items below are mandatory:
   - Test file list (new/modified distinction, paths)
   - Per-file test cases: state input·condition·expected result at the `describe` / `it` unit
   - Mocking strategy (mock target·return value·reason)
   - Coverage goal — classify each case as happy / edge / error. **A failure·error-path test ≥1 is mandatory per non-trivial logic unit** (operational reality scenarios: timeout·null/empty input·malformed response·auth/permission failure·duplicate/concurrent request·DB constraint violation·external API 4xx/5xx), or if the unit has no failure path, an **explicit 1-line N/A reason**. Listing only happy paths is a PROC candidate (Markdown-only·grep-verification sessions are N/A)
   - Execution command (write the Docker command verbatim, no host direct execution)

2. **Run the tests·build with the Docker command**
   - Markdown-only repositories (planning or docs-only repositories) need no Docker — verify with Bash commands such as `grep`/`ls`

   > **💡 Giant test-log delegation (HARNESS-DELEGATE-1)**: When the output log is giant, as with `gradlew`/`pytest`/`npm test`, delegate the execution to an `Explore`/`Agent` subagent (Bash) and **retrieve only the PASS/FAIL + failure-summary conclusion** to save main-context tokens (only when "intermediate output ≫ conclusion" — inline is better for small ones). The main performs self-debug (2-B)·FIX-B/DEP classification based on the delegated conclusion. Detail → `CLAUDE_DETAIL.md §Subagent Delegation Guidelines` (a project file — skip if your project has none).

**2-B. Verification loop (R-2, external-signal based)** — On finding a test·build failure, before immediately classifying FIX-B/DEP, perform a repeating verification loop that is **closed only by external execution signals** (basis: (internal research note, if your project maintains one) — Huang/DeepMind ICLR2024: pure self-correction without external signals lowers accuracy):

- **Closing signal = external execution signals only** (test PASS/FAIL·build·type checker·linter). Do not close the loop on the model's self-judgment ("it's probably fixed").
- **Upper bound ~3 times**: Read the error message·failure line, and if the cause is **obvious** (typo·null check·missing import·contract mismatch), fix inline and re-run to re-confirm via external signal. If there is progress, repeat within the upper bound.
- **Stop immediately on no progress**: If the same error·same diff reproduces **2 times in a row**, stop the loop and enter Step 3 FIX-B/DEP classification (stop even if below the upper bound).
- **Autonomous lane**: the upper bound is **one retry**; still failing → stop with `막힘` (`gate-c/SKILL.md §Autonomous lane`).
- **If not obvious** (network·environment·design defect), enter Step 3 classification immediately without entering the loop.
- **★ reward-hacking guard (R-2-G)**: During the loop, **test files·test commands·CI config are read-only** (no modification) — disabling verification via `@Disabled`·`assert true`·tampering with expected values to force a pass is a PROC violation. After the loop ends, check the `tests/` diff, and **if there is a test change, treat the gate as failed** (a legitimate test reinforcement is a Gate C-stage deliverable, not this loop's deliverable — separate it as FIX-B). See CLAUDE.md 「검증 루프 중 통과 목적의 테스트 수정 금지」.
- **Spec–test conflict path**: if the only way to pass is to change a test because the spec and the test actually disagree, do **not** edit it — stop the loop and report 「명세·시험 충돌」 with the failing test, the spec line it contradicts, and the change you would make; the user decides. Repeated feedback rounds raise test-cheating rates (ImpossibleBench, arXiv:2510.20270), so this is also the exit when the upper bound is reached. The `test-write-guard` hook enforces the read-only rule when installed: during Gate D any Edit/Write to a test path asks the user first.
- **Loop result** (repeat count·stop reason [convergence/no-progress/classification entry]·`tests/` diff presence) must be recorded in 1 line in the Gate D output. Write the repeat count as `self-debug N회` (`self-debug 0회` when no loop ran) in the Gate D block of ${CURRENT_SESSION_FILE} — `error-topics-guard.py` reads this exact marker at Gate E to decide whether an error case must be recorded.
- **Rollback guide (on no-progress stop)**: Before entering FIX-B/DEP classification, restore the working state — ① `git diff` to confirm what changed ② `git restore .` (or `git stash`) to revert to the last clean state ③ verify the repo compiles/runs clean ④ report to the user: which files were reverted + why the fix could not proceed → request a new Gate A re-plan.

> Detail → `plans/agents_instructions/gate-c-instruction.md` (3-iteration protocol · reward-hacking 4 patterns)

3. **Analyze the execution result** and classify the failed items by the criteria below

   | Class | Criteria | Document handling |
   |-------|----------|-------------------|
   | **FIX-B** | Fixable right now with this repository's code (resolved by source·test·config change) | Reserve as next-session Gate A candidate — record in the ${CURRENT_SESSION_FILE} FIX-B item |
   | **DEP** | Verifiable only after other not-yet-implemented code·infra·external API completes first | Record in the DEP item with the dependent session ID, reserve verification after that session completes |

   → If even 1 failure exists, it must be recorded in the table format above (table omission = PROC candidate). If all pass, 「실패 0건」 suffices.

## 3-B. Code Review·Security Check (ECC code-review + security-review)

**Escalation trigger (R-14, scale review depth to blast radius)**: before running the inline 7-item checklist below, check whether **either** condition applies:
- The R/V/D decomposition recorded in `${CURRENT_SESSION_FILE}`'s Dashboard (per gate-a's "Dashboard Required Fields" — the R value from Gate A's own Step 0-A-a scoring, **not** Gate D's re-scored row) has R-axis total **≥ 6** (the same threshold Gate A uses for Opus promotion — new architecture/algorithm/security-policy decisions), **or**
- changed files **> 7** (same count already computed for the R-12 scope guard in Gate A)

**If triggered** → check whether the `/code-review` Skill is available in this environment (it is a Claude Code client capability, **not something this harness bundles or guarantees** — a project installing this harness may not have it). **If available**, invoke it (effort: `medium` when one condition holds, `high` when both hold) against the Gate C diff instead of the inline checklist below, then fold its findings into this Step's output (finding count·severity replace the 7-item table). **If unavailable**, fall back to the inline 7-item checklist below — never skip the review because a skill is missing. **If not triggered at all** → run the inline 7-item checklist below as-is (this is the default path for most sessions — small/standard changes don't need multi-agent review overhead).

> **Rationale**: `/code-review`'s multi-angle finder + independent verifier pattern catches more (cross-file breakage, reuse/simplification gaps, altitude issues) than a single-pass 7-item self-check, but costs materially more tokens/time and depends on a client capability outside this harness's control. Reserve it for sessions where the blast radius justifies the cost — the same R/V/D-based escalation principle Gate A already applies to model selection (R-13) and scope guarding (R-12) — and always keep the inline checklist as the guaranteed fallback.

**Inline checklist (default path, and fallback when `/code-review` is unavailable)** — check the 7 items below against the Gate C changed files, and record the result at the end of the summary output.

**[Code Review]**

| Item | Check content | N/A allowed condition |
|------|---------------|----------------------|
| API contract | Do new·modified endpoints·interfaces match your project's API contract doc (e.g. `<front-repo>/docs/04_BACKEND_COOPERATION.md`) | Session with no API change |
| Error handling | Are exception·null·failure paths handled (unhandled promise, NPE, unhandled exception, etc.) | Markdown-only repository |
| Duplication·pattern | Did you reuse the existing helper found in Gate A Pre-Plan; is there no duplication of the same logic | Always applied |

**[Security Check]**

| Item | Check content |
|------|---------------|
| Hardcoded secrets | Are API keys·tokens·passwords·DB credentials not exposed in source/config |
| SQL injection | Is user input not concatenated into a query without parameter binding |
| Auth/authorization | Is an auth guard applied to new endpoints·routes |
| Input validation | Is validation·escaping applied to external input (request body·query·filename) |

> Markdown-only repository·Skill-file modification sessions may record the security check as "N/A".

4. **Summarize the result as text output** — include the items below:
   - Total test pass/fail count
   - Per-failure error content + FIX-B/DEP classification and basis
   - FIX-B: one-line fix direction + reserved session
   - DEP: dependency-target session/code + when verifiable
   - Classification count line, verbatim format `FIX-B N건 · DEP N건` (write 0 for none), also copied into the Gate D block of ${CURRENT_SESSION_FILE} — the same guard reads `FIX-B N건`
   - Build success or not
   - **Code review·security check: PASS / N issues / N/A** (3-B result summary — if the `/code-review` escalation fired and the Skill was available, prefix with `[/code-review 위임]` and cite the finding count/severity it returned instead of the inline 7-item table; if escalation fired but the Skill was unavailable and the inline checklist ran instead, prefix with `[/code-review 미가용 — 인라인 대체]`)

   > **Counts come from a generated facts block, not from memory** (2026-10-15 — final reports said "5 files" for 4 hooks + 4 tests and "all new tests fail on old code" for 17 of 19). Run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/report_facts.py" --base <Gate C base commit>` (add `--junit <xml>` when the test runner writes JUnit, and `--fail-on-base "<test command>" --base-junit <xml>` to get the per-test "fails on old code" table) and paste the block into the result. Every number in this summary — changed files, pass/fail counts, "N of M new tests fail on the base" — is copied from that block. Write N/M instead of 「모두·전부·all」. If a number cannot be produced by a command, say so instead of estimating.
   >
   > **claim↔evidence cross-check (technique-8 low-cost core)**: Back each PASS claim with at least one of file·line·test name as evidence (e.g. "회귀 PASS284 — `ScoringServiceTest` 외 ⋯", "정합 PASS — `diff -q` exit 0"). No listing of bare "PASS" without evidence — secure the verifiability of your own output without calling a separate evaluation model.

5. **Conditional Refactor** — perform only when at least one of the following applies:
   - The user explicitly requests refactoring
   - §3-B code review found **3+ issues** (1~2 issues are handled by a Gate C follow-up inline fix or §5 handoff registration)
   - Gate A estimated **grade H (R/V/D basis)** + 1+ §3-B issues
   - Performance optimization is explicitly required

   If none apply, skip refactor and proceed to Step 6.

   **Refactor procedure** (when triggered):
   - Read the Gate D verification result + Gate C code and identify refactoring targets
   - Write a list of code duplication·complexity·naming·structure improvement points
   - Perform the refactoring — no additional feature changes beyond the Gate A plan scope
   - Re-verify — re-run the existing tests with the same Docker command

### Layer 2 document update (if `--docs=full` was used at `/init`)

Fill the following if the respective files exist at the target repo root:

**TEST_PLAN.md** — `## Verification Checklist` section:
- Fill after Gate D run completes: list happy/error test PASS results, regression count
- Update `DOC_INDEX.md` `TEST_PLAN.md` row → `Complete` (both Gate C and D sections now filled)

**ERROR_HANDLING.md** — `## Failure Paths` + `## Recovery Strategies`:
- Fill only if Gate D found failures or documented error paths (FIX-B/DEP items qualify)
- If Gate D found no failures → leave marker in place (correct empty state — do not write "N/A")
- Update `DOC_INDEX.md` `ERROR_HANDLING.md` row → `Partial` or `Complete`

**DECISION_LOG.md** — append one ADR entry per non-obvious architectural decision made in this session:
- Format: `### [YYYY-MM-DD] <Decision title>` + Context / Decision / Evidence / Consequences, plus Prediction / check by when the decision is expected to change behavior (per `/init` Step 10-b format). If an earlier entry's check date has passed, fill its Outcome line in the same pass
- If no non-obvious decision → leave marker in place
- Update `DOC_INDEX.md` `DECISION_LOG.md` row → `Partial` or `Complete`

If none of the above files exist: skip silently.

6. Update the plan document(s) (status: `D (확인 대기)`, write the Gate D block) — **run the file-editing tool**
   - Plan document(s) — tier-aware, see `SKILL_DETAIL.md §Plan-Doc Update Pattern`
   - `${SESSION_INDEX_FILE}` YAML
   - `${CURRENT_SESSION_FILE}` — record the full test plan + execution result + FIX-B·DEP items
   > **session-dashboard.html update**: a hook regenerates the HTML automatically — `session-dashboard-sync.py` runs on `PostToolUse` (Edit|Write) in plugin and install.sh installs, and as the first `Stop` entry in projects wired by `/init` (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

7. STOP — await user document review·confirmation. **Batch exception** (`gate-c/SKILL.md` §Batch runs): if the user authorized 「C~E 일괄」 or 「D~E 일괄」, the session is not high-risk, and this Gate ended with every test and build passing and no FIX-B/DEP item, continue to `/gate-e` instead of stopping. Any failure → STOP and report; never run Gate E on a failing verification

## Docker Execution Commands (mandatory in Gate D record)

> For the test·build commands, **write the `CLAUDE.md §Build·Test` canonical table verbatim** (one canonical row per code repository). Do not duplicate the values into this SKILL — single canonical source (SSOT·recurrence prevention).
> Host direct execution·`-it` prohibited (Claude Code has no TTY). On permission error, work around with `sg docker -c "..."`. Wrong commands (a repository name used as the container name, `-it`, etc.) are blocked by `docker-command-guard.py` (PreToolUse), which guides you to the canonical command.

## FIX-B Handling Example

```
[FIX-B] ProfileStep2.test.tsx — "이전 버튼" 단언 실패
  에러: Expected "Back" but found "이전"
  수정 방향: 버튼 텍스트를 한국어 "이전"으로 단언 수정
  예약 세션: 다음 세션 Gate C에서 수정
```

## DEP Handling Example

```
[DEP] ProfileSteps.e2e.test.tsx — runMatching API mock 실패
  에러: runMatching is not a function (API 저장소 엔드포인트 미구현)
  의존 대상: API 저장소 세션 2-D-3 완료 후 검증 가능
  검증 예약: 2-D-3 ✅E 이후
```

---

## Advisor Escalation (optional)

During Gate D execution, if the situation below applies, you may make a **single call** to an Opus subagent for advice and then return.

**Gate D trigger conditions** (call only in these situations):
- The same test failure reproduces 2 times in a row, cause unclear
- FIX-B vs DEP classification ambiguous — cannot judge which side
- Security-check boundary case (situation where applicability is unclear)

**Call prohibited** (resolve directly): errors already in the standard failure·error taxonomy (PROC/ENV/TYPE/LOGIC/VERIFY/SEC/API)

**Session-cumulative max_uses**: 3 times. On exceeding → **escalate**: ① run the rollback guide above (git restore to last clean state) ② report to the user — which files were reverted, what was attempted, and why it failed → request a new Gate A re-plan.

Detailed call template·recording method·guardrails → **CLAUDE_DETAIL.md §Advisor Escalation** (a project file — skip if your project has none)

---

## This Gate response's mandatory final output

After completing the entire Gate D procedure (test plan + execution + result classification + plan document(s) update), output the block below at the **very end** of the response — the same block whether or not a refactor was performed.
Omitting it or replacing it with other content is a **PROC violation**. Exception: in an authorized C~E·D~E batch run that passed Gate D, continue to `/gate-e` instead of printing it.

```
---
**다음 단계**: Gate D 확인 후 「Gate E 진행」또는 「세션 정리」로 응답하면 `/gate-e` (Gate E WORKLOG·아카이브)가 시작됩니다.
**권장 모델 전환**: ${CURRENT_SESSION_FILE} "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
💡 **캐시 참고**: 프롬프트 캐시 유지 시간은 구독 로그인 기본 1시간, API 키 사용 시 5분입니다. 그 안에 응답하면 다시 읽는 토큰 비용이 줄어듭니다.
```
