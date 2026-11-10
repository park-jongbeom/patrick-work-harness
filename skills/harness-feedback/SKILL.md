---
name: harness-feedback
description: "Sends this PC's harness usage summary to the engine maintainer's server over SSH, and sets up the automatic sending. Use on '/harness-feedback', '사용 기록 보내', '하네스 기록 전송', '보고서 보내기', or when asked where the harness usage data goes."
effort: low
---

# /harness-feedback — send the usage summary to the engine server

> The engine is improved from evidence in real work, and that evidence lives only in this PC's transcripts, which Claude Code
> deletes after 30 days. This skill sets up and runs `harness-feedback-sync.py`, which sends a summary — never transcripts or code.

## What is sent, where, and when

- **What**: the session rows `harness_report.py` builds from the last 30 days (Gate order, guard counts and errors, Gate B
  answers, fresh-context review counts, context cost — compactions, context per Gate A, what fills it by tool name and
  character count, how skills were reloaded, Claude Code version). Each row carries the project name, this PC's folder
  name, guard notice text and the engine version the session started with. One file per send, first line = PC name,
  time, reason, engine version, and when each engine version was first seen on this PC.
- **Where**: one SSH address, `[user@]host[:folder]` (folder defaults to `harness-inbox`). It uses this PC's own SSH
  config and keys with `BatchMode=yes` — it never asks for a password. For a port or key, put a `Host` alias in
  `~/.ssh/config` and use the alias. The address is stored only in `~/.claude/harness-feedback/config.json`.
- **When (automatic)**: the Stop hook checks at most once every 6 hours, in a detached process. It sends when, since the last
  send, there is ≥ 1 new harness internal error (an engine hook execution error or a fresh-review script failure), ≥ 10
  changed sessions, or 14 days have passed with ≥ 1 changed session. A failed send is logged and retried at the next check.

## Procedure

`S="${CLAUDE_PLUGIN_ROOT}/hooks/harness-feedback-sync.py"`

1. Run `python3 "$S" status` and show the user its lines.
2. **No address yet** → ask the user for the address (`[user@]host[:folder]`), then run `python3 "$S" setup <address>`.
   On 「실패」, explain the cause from its message — the usual ones:
   - host key not yet trusted → the user runs `ssh <host>` once in a terminal and accepts the key
   - no key for that host, or the key needs a passphrase without an agent → `BatchMode` cannot use it
   - the folder is not writable on the server
   Do not edit `~/.ssh` yourself.
3. **Send now** only when the user asked to send, or right after a successful setup when the user agrees:
   `python3 "$S" send`. Use `send --dry-run` first if the user wants to see what would go.
4. Report the result line (「보냄 — …」 or 「실패 — …」) as it is.

To stop automatic sending, delete `~/.claude/harness-feedback/config.json`. The log is `~/.claude/harness-feedback/send.log`.

## On the receiving server

`python3 hooks/harness-feedback-sync.py receive [--inbox ~/harness-inbox] [--out <folder>]` builds the usage report from
every received file and checks it against `DECISION_LOG.md`. A session sent several times is counted once (latest row).
