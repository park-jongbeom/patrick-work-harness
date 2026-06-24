---
name: gate-b
description: "Code implementation after Gate A approval. Use on '구현해라', '계획대로 구현', 'Gate B 시작', 'Gate B 진행', 'Gate A 승인', etc."
effort: medium
---

# Gate B Procedure (follow order strictly)

0. **Comprehension gate before start** (COMPREHEND-GATE-1) — If Gate A's 「이해도 게이트 발동 판정」 is **발동** (triggered), run `/comprehend-gate` first before code implementation (code implementation is blocked until the gate passes). If **미발동** (not triggered; trivial CRUD·docs·format change), skip this Step and proceed to Step 1. Procedure → `comprehend-gate/SKILL.md`.

1. **Based on the Gate A detailed plan**, implement the code
   - Follow the file list·change direction·execution order approved at Gate A verbatim
   - No additional changes·refactoring·comment cleanup beyond the plan
   - **Ladder check (R-4-6)**: if an abstraction·helper not in the Gate A plan emerges mid-implementation, it is a ladder rung-1 violation — stop and apply the rung at the actual call site, or escalate per the Advisor rule below. (Restates the `Exceeding change scope` prohibition as a ladder check — no new rule.)

2. After implementation, summarize the result as text output — include the items below:
   - The actual changed-file list (state the reason if it differs from the Gate A plan)
   - Per-file key implementation summary (design decisions·core before→after difference)
   - Differences from the Gate A plan and their reasons (if none, "계획 그대로 구현")
   - **ReAct deliverable guard (R-3)**: For each changed file, output one pair of 「Reasoning(왜 이 변경) → Action(실제 diff 요약)」.
     No listing diffs without reasons — Gate C cannot trace change intent otherwise.
     Compress each pair to within 3 lines (no verbose reasoning).

3. Update the 3 documents (status: `B (확인 대기)`, write the Gate B block) — **run the file-editing tool**
   - `00_MODERNIZATION_MASTER_PLAN.md` §7
   - `SESSION_INDEX.md` YAML
   - `CURRENT_SESSION.md` dashboard + Gate B block
   > **session-dashboard.html update**: `session-dashboard-sync.py` always runs as the first entry of the `Stop` hook array, auto-regenerating the HTML (HARNESS-STALE-GUARD-3). No skill Bash Step needed.

4. STOP — await user document review·confirmation

> **No test·build execution in this turn after Gate B completion** (`npm test` / `pytest` / `./gradlew test`, etc.).
> Proceed in a separate turn after Gate C verification confirmation.

## Scope of 「구현해라」-like Instructions

「구현해」「계획대로 구현」「다음 계획을 구현해라」 mean **Gate B only**.
To allow B→E, the user must specify the scope in a sentence such as 「Gate B부터 E까지 한 번에」「B~E 일괄로 진행해」.

---

## Advisor Escalation (optional)

During Gate B execution, if the situation below applies, you may make a **single call** to an Opus subagent for advice and then return.

**Gate B trigger conditions** (call only in these situations):
- A design branch not in the Gate A plan is discovered
- Conflict with an existing architecture pattern — cannot judge which direction is correct
- Cannot choose among 2+ implementation options

**Call prohibited** (resolve directly): syntax·API reference lookup (Grep/WebFetch suffices)

**Session-cumulative max_uses**: 3 times. On exceeding → halt the session → request the user re-plan Gate A.

Detailed call template·recording method·guardrails → **CLAUDE_DETAIL.md §Advisor Escalation**

---

## This Gate response's mandatory final output

After completing the entire Gate B procedure (code implementation + 3-document update), output the block below at the **very end** of the response.
Omitting it or replacing it with other content is a **PROC violation**.

```
---
**다음 단계**: Gate B 확인 후 「Gate C 시작」또는 「검증」으로 응답하면 `/gate-c` (Gate C 검증)가 시작됩니다.
**권장 모델 전환**: CURRENT_SESSION.md "Gate별 권장 모델" 표를 참조하여 필요 시 `/model {모델}` 실행 후 진행하세요.
💡 **compact 권장 시점**: Gate B 구현이 끝난 지금이 `/compact` 최적 타이밍입니다. Gate C는 테스트 결과라는 새로운 맥락으로 시작하므로, B의 시행착오 컨텍스트를 정리하면 토큰을 절약할 수 있습니다.
```
