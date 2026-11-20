---
name: vault-ref
description: "Finds and reads the project's Obsidian vault notes for the current topic, judges whether each passage is stale, and records what was read and used. Use when the context has a `[볼트 발췌 — vault-context]` block and you are about to plan (Gate A), decide, or answer a why/history question; or on '/vault-ref', '볼트 참조', '볼트 찾아봐'."
effort: low
---

# /vault-ref — read the vault for this topic, then record it

> The `vault-context.py` SessionStart hook puts only fixed parts of the vault into context (chosen sections, the latest
> daily, notes linking the hub). This skill covers the rest: the notes about **this** task. The vault holds direction,
> judgments and history; the repository stays canonical for code and session state.

## Step 1. Where

- The vault path is the `볼트: <path> — <last commit>` line under the `[볼트 발췌 — vault-context]` marker.
- The marker line says 「볼트 발췌 없음」 or 「볼트 발췌 실패」 → record `- 볼트 없음 — <that line>` and stop.
- The vault is outside the project, so each read may ask for permission. Adding the vault path to
  `permissions.additionalDirectories` in the project's `.claude/settings.json` stops the prompts — say so once if it happens.

## Step 2. Find

1. Take 2~4 keywords from the user's request and `next_action`.
2. `Grep` the vault's `*.md` for them (file list first). Skip `90 Private/`, `.obsidian/`, `.trash/`, `.git/`.
3. Prefer notes the excerpt already lists as linking the hub. Pick at most 3 notes.
4. Read only the matching sections — `Grep -n` for the line, then `Read` with an offset. Never read the whole vault or a
   whole long note; judge relevance from titles, headings, tags and front matter first.

## Step 3. Is it stale?

Date each passage in this order — the first that exists wins:

1. A 「YYYY-MM-DD 기준」 label inside that section or block
2. The note's last vault commit — `git -C <vault> log -1 --format=%ci -- "<note>"`
3. The file's modified date

A modified date alone never dates a section: editing another part of the same note changes it. Dated addenda inside the
block (「**11/20 덧붙임**」, year taken from the 기준 label) move the date forward for the line they are on — a line's
date is its last addendum, else the block's 기준 date. A `>` quote block can run on into an older 「이전 …」 block with
its own 기준 label — stop there; addenda are not a new block.

Compare with the repository's records (`SESSION_INDEX.md`, `CURRENT_SESSION.md`, the plan documents, `git log`). The
repository is newer and says something different → mark the passage **낡음**, do not use it as a basis, and state the
mismatch in one line.

## Never

- Open anything under `90 Private`.
- Copy secret values from the vault (keys, tokens, passwords, account numbers, personal contacts) into a plan, document,
  commit or reply — name the note and write 「값 생략」.
- Edit or commit the vault. This skill only reads.

## Record

In Gate A, right after `### 교훈 조회`:

```
### 볼트 참조
- 질의: <키워드>
- 읽은 노트: `<vault-relative path>` §<section> (<YYYY-MM-DD 기준 | 커밋 YYYY-MM-DD>) — 적용: <Step·decision it shaped> | 해당 없음: <why> | 낡음: <the newer repository record>
```

One `읽은 노트` line per note. Nothing matched → `- 일치 없음 (질의: …)`. Outside Gate A (a decision, a why question),
put the same lines in the reply.
