---
name: commit-up
description: "Closes finished work in one request: slims over-threshold session documents, runs the audit only when it is due, then commits work and records by explicit path and reports — never pushes. Use on '/commit-up', '커밋하고 정리해라', '커밋하고 정리', '커밋 정리', or when asked to commit and wrap up after Gate E. Not for a plain mid-work commit request."
effort: low
---

# commit-up Procedure (follow order strictly)

One request closes the work: documents → audit check → commits → report.

> **Why** (2026-11-11 — closing turns read back from real sessions): after almost every cycle the user typed the same inputs by hand — `/doc-cleanup`, sometimes `/audit`, then 「커밋하고 정리해라」. No Gate commits, yet Gate D's facts block counts everything since the base commit, so an uncommitted cycle leaks into the next one's numbers. 「정리」 came out different each time — the commit was noted in a different place, or nowhere — and the audit was skipped without a word.

## Step 0. What is being closed

- Run `git status --short` in each repository this work touched. Nothing to commit anywhere → say so and stop.
- Read `> **현재 상태**` in `${CURRENT_SESSION_FILE}`. If a Gate A~D is still open (not `✅E`, not 「세션 없음」), say which one and ask whether to finish Gate E first — do not close a half-done cycle silently. Work done outside a Gate cycle (a report, a harness update) closes here without Gate E.

## Step 1. Documents

- Measure now with `wc -l`: `${CURRENT_SESSION_FILE}` over 100 lines or `${SESSION_INDEX_FILE}` over 80 → over threshold. A plan document that Gate E flagged `⚠️ 초과` in this conversation and that has not been cleaned since also counts.
- Over → invoke the `doc-cleanup` skill **through the Skill tool with no arguments**. Do not ask the user to type `/doc-cleanup`: a typed command reloads the whole skill body every cycle.
- Not over → skip it and say so in the final block.

## Step 2. Audit check

- Due = `sessions_since_audit ≥ 3` in the `${SESSION_INDEX_FILE}` YAML, or `last_audit_date` absent, or Gate E recommended the audit in this conversation and it has not run since.
- Due → invoke the `audit` skill through the Skill tool. Not due → do not run it.
- Either way the final block states the decision (「실행」 or 「건너뜀 — N/3」). A silent skip reads as "the audit ran".

## Step 3. Stage — by path, in two groups

- Split the changes into **work** (code, tests, deliverables) and **records** (session documents, archive, WORKLOG, session ledger, dashboard, lessons).
- Read the diff of what you are about to add for secrets (keys, tokens, passwords, `.env` files). In a file that is not this work's → leave that file out and name it in the final block. Inside a file this work must commit → stop and ask before any commit; do not commit around it.
- Stage by explicit path. Never `git add -A`, `git add .` or `git commit -a` — they sweep in files this work did not make. A file you leave out goes in the final block with the reason.
- If the project's rules require a check before a commit, run it only when code changed after Gate D passed. Do not repeat a check that already passed on the same files.

## Step 4. Work commit

- Commit the work group first, in the project's message convention (the commit-message guard enforces it where wired). No work files → go to Step 5.

## Step 5. Record commit

- Note the work commit's short hash in one place: a `**커밋**: <해시>` line on this work's WORKLOG entry (`<worklog_path>/YYYY-Www.md`). Do not copy it into the session documents as well. No entry yet (work outside a Gate cycle) → add one: date, one-line summary, hash. No `worklog_path` → skip the note.
- Bring `next_action` in `${SESSION_INDEX_FILE}` (and 「다음 행동」 in `${CURRENT_SESSION_FILE}`, if present) to the state **after** the commit. Replace the whole value with what comes next — drop finished items, including the commit just made; a 「커밋 필요」 left behind costs another edit and another commit.
- The next work starts in a new conversation that will not see this one. A decision the user gave here that the next work depends on and that no document holds yet → add it to `next_action` in one line.
- Make these edits with the editing tool, not a one-off script.
- Commit the record group. Another repository in play (a notes vault, a second code repository) → commit there too, in that repository's convention.

## Never

- No `git push`. The user decides when (「올려라」). If the branch has an upstream, report ahead/behind in the final block.
- Beyond what `doc-cleanup` does under its own guard, delete nothing. No `git reset`, `git clean` or `git stash`, no amending or rebasing. If something looks like it should go, list it and ask.

## This Skill's mandatory final output

Output the block below at the **very end** of the response — one 「커밋」 line per commit.

```
── 마무리 ──────────────────────────────────
  문서 정리 : CURRENT_SESSION N → M줄 / 건너뜀 — 임계값 이하
  audit     : 실행 — <판정 한 줄> / 건너뜀 — N/3
  커밋      : <해시> <제목> (파일 N개)
  남긴 파일 : 없음 / <경로> — <이유>
  push      : 하지 않음 (<원격보다 N 앞섬 / 원격 없음>)
  다음 작업 : 새 대화(`/clear`)에서 `/gate-a` — 이어 갈 일은 next_action 에 있다
────────────────────────────────────────────
```

> **Why a new conversation** (2026-11-12 — usage summary): the two harness conversations ran three days with 11 and 17 cycles; each cycle started with 365k–465k tokens already loaded against a 50k–58k fresh start, about 420k–470k per response, with six automatic compactions each. Everything the next cycle needs is in the session documents.
