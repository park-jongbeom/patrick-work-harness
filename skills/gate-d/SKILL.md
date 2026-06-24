---
name: gate-d
description: "Conditional code-quality improvement after Gate C verification. Use on '리팩터', '코드 정리', 'Gate D 진행', 'Gate D 시작', etc."
effort: medium
---

# Gate D Procedure (follow order strictly)

## Trigger Conditions

Gate D is a **conditional** Gate. Perform it only when at least one of the following applies:
- The user explicitly requests refactoring
- Gate C §3-B code review found **3+ issues** (1~2 issues are handled by a Gate B follow-up inline fix or §5 handoff registration)
- Gate A estimated score **≥ 10 (grade H)** + 1+ Gate C issues
- Performance optimization is explicitly required

If none apply, skip Gate D and go directly to Gate E.

## Procedure

1. **Read the Gate C verification result + Gate B code** and identify the refactoring targets
   - Write a list of code duplication·complexity·naming·structure improvement points
   - State the core before→after difference for each item

2. **Perform the refactoring**
   - No additional feature changes beyond the Gate A plan scope
   - The principle is to improve code quality only, with no behavior change

3. **Re-verify** — re-run the existing tests with the same Docker command as Gate C
   - Markdown-only repositories are re-verified with Bash commands such as `grep`/`ls`
   - Confirm no new failure was introduced by the refactoring

4. Summarize the result as text output — include the items below:
   - Change content per refactoring item
   - Re-verification result (all pass / if a new failure occurs, root-cause analysis)
   - Differences from the Gate A plan and their reasons (if none, "계획 그대로 구현")

5. Update the 3 documents (status: `D (확인 대기)`, write the Gate D block) — **run the file-editing tool**
   - `00_MODERNIZATION_MASTER_PLAN.md` §7
   - `SESSION_INDEX.md` YAML
   - `CURRENT_SESSION.md` — record the refactoring items + re-verification result
   > **session-dashboard.html update**: `session-dashboard-sync.py` always runs as the first entry of the `Stop` hook array, auto-regenerating the HTML (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

6. STOP — await user document review·confirmation

## Docker Execution Commands (for re-verification)

> For the re-verification test·build commands, **write the `CLAUDE.md §Build·Test` canonical table verbatim** (same canonical as Gate C). Do not duplicate the values into this SKILL — single canonical source (SSOT·recurrence prevention).
> Host direct execution·`-it` prohibited (Claude Code has no TTY). On permission error, work around with `sg docker -c "..."`. Wrong commands are blocked by `docker-command-guard.py` (PreToolUse).

---

## Advisor Escalation (optional)

During Gate D execution, if the situation below applies, you may make a **single call** to an Opus subagent for advice and then return.

**Gate D trigger conditions** (call only in these situations):
- Refactor scope boundary unclear — risk of exceeding the Gate A scope but cannot judge
- Architecture pattern choice needed (cannot choose among 2+ refactor directions)

**Call prohibited** (resolve directly): simple naming·format cleanup

**Session-cumulative max_uses**: 3 times. On exceeding → halt the session → request the user re-plan Gate A.

Detailed call template·recording method·guardrails → **CLAUDE_DETAIL.md §Advisor Escalation**

---

## This Gate response's mandatory final output

After completing the entire Gate D procedure (refactoring + re-verification + 3-document update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

```
---
**다음 단계**: Gate D 확인 후 「Gate E 진행」또는 「세션 정리」로 응답하면 `/gate-e` (Gate E WORKLOG·아카이브)가 시작됩니다.
**권장 모델 전환**: CURRENT_SESSION.md "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
```
