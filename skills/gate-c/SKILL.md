---
name: gate-c
description: "Verification after Gate B confirmation (test plan + execution + FIX-B/DEP classification). Use on 'Gate C', '검증', '테스트', 'Gate C 시작', 'C~E 일괄', etc."
effort: high
---

# Gate C Procedure (follow order strictly)

1. **After reading all files changed in Gate B**, output the test plan as text — the items below are mandatory:
   - Test file list (new/modified distinction, paths)
   - Per-file test cases: state input·condition·expected result at the `describe` / `it` unit
   - Mocking strategy (mock target·return value·reason)
   - Coverage goal — classify each case as happy / edge / error. **A failure·error-path test ≥1 is mandatory per non-trivial logic unit** (operational reality scenarios: timeout·null/empty input·malformed response·auth/permission failure·duplicate/concurrent request·DB constraint violation·external API 4xx/5xx), or if the unit has no failure path, an **explicit 1-line N/A reason**. Listing only happy paths is a PROC candidate (Markdown-only·grep-verification sessions are N/A)
   - Execution command (write the Docker command verbatim, no host direct execution)

2. **Run the tests·build with the Docker command**
   - Markdown-only repositories (ai-consulting-plans, plans) need no Docker — verify with Bash commands such as `grep`/`ls`

   > **💡 Giant test-log delegation (HARNESS-DELEGATE-1)**: When the output log is giant, as with `gradlew`/`pytest`/`npm test`, delegate the execution to an `Explore`/`Agent` subagent (Bash) and **retrieve only the PASS/FAIL + failure-summary conclusion** to save main-context tokens (only when "intermediate output ≫ conclusion" — inline is better for small ones). The main performs self-debug (2-B)·FIX-B/DEP classification based on the delegated conclusion. Detail → `CLAUDE_DETAIL.md §Subagent Delegation Guidelines`.

**2-B. Verification loop (R-2, external-signal based)** — On finding a test·build failure, before immediately classifying FIX-B/DEP, perform a repeating verification loop that is **closed only by external execution signals** (basis: `REPORTS/HARNESS_RIGOR_RESEARCH_V1.md §1` — Huang/DeepMind ICLR2024: pure self-correction without external signals lowers accuracy):

- **Closing signal = external execution signals only** (test PASS/FAIL·build·type checker·linter). Do not close the loop on the model's self-judgment ("it's probably fixed").
- **Upper bound ~3 times**: Read the error message·failure line, and if the cause is **obvious** (typo·null check·missing import·contract mismatch), fix inline and re-run to re-confirm via external signal. If there is progress, repeat within the upper bound.
- **Stop immediately on no progress**: If the same error·same diff reproduces **2 times in a row**, stop the loop and enter Step 3 FIX-B/DEP classification (stop even if below the upper bound).
- **If not obvious** (network·environment·design defect), enter Step 3 classification immediately without entering the loop.
- **★ reward-hacking guard (R-2-G)**: During the loop, **test files·test commands·CI config are read-only** (no modification) — disabling verification via `@Disabled`·`assert true`·tampering with expected values to force a pass is a PROC violation. After the loop ends, check the `tests/` diff, and **if there is a test change, treat the gate as failed** (a legitimate test reinforcement is a Gate B-stage deliverable, not this loop's deliverable — separate it as FIX-B). See CLAUDE.md 「검증 루프 중 통과 목적의 테스트 수정 금지」.
- **Loop result** (repeat count·stop reason [convergence/no-progress/classification entry]·`tests/` diff presence) must be recorded in 1 line in the Gate C output.

3. **Analyze the execution result** and classify the failed items by the criteria below

   | Class | Criteria | Document handling |
   |-------|----------|-------------------|
   | **FIX-B** | Fixable right now with this repository's code (resolved by source·test·config change) | Reserve as next-session Gate A candidate — record in the CURRENT_SESSION.md FIX-B item |
   | **DEP** | Verifiable only after other not-yet-implemented code·infra·external API completes first | Record in the DEP item with the dependent session ID, reserve verification after that session completes |

   → If even 1 failure exists, it must be recorded in the table format above (table omission = PROC candidate). If all pass, 「실패 0건」 suffices.

## 3-B. Code Review·Security Check (ECC code-review + security-review)

Check the 7 items below against the Gate B changed files, and record the result at the end of the summary output.

**[Code Review]**

| Item | Check content | N/A allowed condition |
|------|---------------|----------------------|
| API contract | Do new·modified endpoints·interfaces match the `react-web-ga/docs/04_BACKEND_COOPERATION.md` contract | Session with no API change |
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
   - Build success or not
   - **Code review·security check: PASS / N issues / N/A** (3-B result summary)

   > **claim↔evidence cross-check (technique-8 low-cost core)**: Back each PASS claim with at least one of file·line·test name as evidence (e.g. "회귀 PASS284 — `ScoringServiceTest` 외 ⋯", "정합 PASS — `diff -q` exit 0"). No listing of bare "PASS" without evidence — secure the verifiability of your own output without calling a separate evaluation model.

5. **Judge whether Gate D (refactor) is needed** and recommend — see the trigger conditions below

6. Update the 3 documents (status: `C (확인 대기)`, write the Gate C block) — **run the file-editing tool**
   - `00_MODERNIZATION_MASTER_PLAN.md` §7
   - `SESSION_INDEX.md` YAML
   - `CURRENT_SESSION.md` — record the full test plan + execution result + FIX-B·DEP items
   > **session-dashboard.html update**: `session-dashboard-sync.py` always runs as the first entry of the `Stop` hook array, auto-regenerating the HTML (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

7. STOP — await user document review·confirmation

## Gate D (refactor) Trigger Conditions

Recommend Gate D (refactor) if **any one** of the below applies:
- The user explicitly requests refactoring
- §3-B code review found **3+ issues** (1~2 issues are handled by a Gate B follow-up inline fix or §5 handoff registration)
- Gate A estimated **grade H (R/V/D basis)** + 1+ §3-B issues
- Performance optimization is explicitly required

If none apply, skip Gate D and go directly to Gate E.

## Docker Execution Commands (mandatory in Gate C record)

> For the test·build commands, **write the `CLAUDE.md §Build·Test` canonical table verbatim** (each canonical for react-web-ga·college-crawler·ga-api-platform). Do not duplicate the values into this SKILL — single canonical source (SSOT·recurrence prevention).
> Host direct execution·`-it` prohibited (Claude Code has no TTY). On permission error, work around with `sg docker -c "..."`. Wrong commands (`docker exec ga-api-platform`·`-it`, etc.) are blocked by `docker-command-guard.py` (PreToolUse), which guides you to the canonical command.

## FIX-B Handling Example

```
[FIX-B] ProfileStep2.test.tsx — "이전 버튼" 단언 실패
  에러: Expected "Back" but found "이전"
  수정 방향: 버튼 텍스트를 한국어 "이전"으로 단언 수정
  예약 세션: 다음 세션 Gate B에서 수정
```

## DEP Handling Example

```
[DEP] ProfileSteps.e2e.test.tsx — runMatching API mock 실패
  에러: runMatching is not a function (ga-api-platform 엔드포인트 미구현)
  의존 대상: ga-api-platform 세션 2-D-3 완료 후 검증 가능
  검증 예약: 2-D-3 ✅E 이후
```

---

## Advisor Escalation (optional)

During Gate C execution, if the situation below applies, you may make a **single call** to an Opus subagent for advice and then return.

**Gate C trigger conditions** (call only in these situations):
- The same test failure reproduces 2 times in a row, cause unclear
- FIX-B vs DEP classification ambiguous — cannot judge which side
- Security-check boundary case (situation where applicability is unclear)

**Call prohibited** (resolve directly): errors already in the standard failure·error taxonomy (PROC/ENV/TYPE/LOGIC/VERIFY/SEC/API)

**Session-cumulative max_uses**: 3 times. On exceeding → halt the session → request the user re-plan Gate A.

Detailed call template·recording method·guardrails → **CLAUDE_DETAIL.md §Advisor Escalation**

---

## This Gate response's mandatory final output

After completing the entire Gate C procedure (test plan + execution + result classification + 3-document update), output **whichever applies** of the blocks below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

**When recommending Gate D (refactor):**
```
---
**다음 단계**: Gate C 확인 후 「Gate D 진행」또는 「리팩터 시작」으로 응답하면 `/gate-d` (Gate D 코드 품질 개선)가 시작됩니다.
**권장 모델 전환**: CURRENT_SESSION.md "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
💡 **캐시 TTL 참고**: Gate C 결과를 검토할 때, 5분 이내에 응답하면 프롬프트 캐시가 유지되어 토큰 비용이 절감됩니다. 길게 검토할 경우 한 번에 모아서 피드백하는 것이 효율적입니다.
```

**When Gate D is unnecessary:**
```
---
**다음 단계**: Gate C 확인 후 「Gate E 진행」또는 「세션 정리」로 응답하면 `/gate-e` (Gate E WORKLOG·아카이브)가 시작됩니다.
**권장 모델 전환**: CURRENT_SESSION.md "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
💡 **캐시 TTL 참고**: Gate C 결과를 검토할 때, 5분 이내에 응답하면 프롬프트 캐시가 유지되어 토큰 비용이 절감됩니다. 길게 검토할 경우 한 번에 모아서 피드백하는 것이 효율적입니다.
```
