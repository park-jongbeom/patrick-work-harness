---
name: init
description: "Initialize harness scaffold files in a new repo (CLAUDE.md with D-1 sentinel zones + session docs + D-2 provenance sidecar). Use on '/init', 'harness init', '하네스 초기화', or when bootstrapping a new project with the go-almond harness plugin."
---

# /init Skill — Harness Scaffold Initializer

> Implements R-4-4 from `REPORTS/HARNESS_PLUGINIZATION_DESIGN_V1.md`.
> Prerequisite: harness plugin installed (plugin.json present, marketplace registered).
> Constraint: F5 — CLAUDE.md at plugin root is NOT loaded as project context. This skill generates files directly in the target repo.

## When to Use

- Bootstrapping a new repository with the go-almond harness
- Setting up Gate A–E workflow + session document structure from scratch
- Re-initializing after a harness version bump (when `.claude/harness-answers.yml` is absent)

## Prerequisites

- Claude Code with patrick-work-harness plugin enabled
- Write access to the target repository root
- Know: repo name, primary stack, whether MVP Phase model applies, archive/worklog paths

## Procedure

### Step 1 — Codebase analysis

Scan the target repo to detect:
- Primary language/framework (look for `build.gradle.kts` / `package.json` / `requirements.txt` / `go.mod`)
- Existing `CLAUDE.md` (if present, warn before overwriting the HARNESS zone)
- Existing `.claude/harness-answers.yml` (if present, load existing answers as defaults)

### Step 2 — Answers interview

Ask the user (or infer from Step 1 scan) for the following fields:

| Field | Description | Default |
|-------|-------------|---------|
| `project_repo` | Short repo identifier (e.g. `go-almond`) | inferred from directory name |
| `stack` | Primary stack tag (e.g. `kotlin-spring`, `react-ts`, `python`) | inferred |
| `phase_model` | Enable MVP Phase 1–4 guardrail in CLAUDE.md? | `true` |
| `session_docs` | Generate SESSION_INDEX.md + CURRENT_SESSION.md stubs? | `true` |
| `archive_path` | Absolute path for session archive files | ask user |
| `worklog_path` | Absolute path for WORKLOG files | ask user |

### Step 3 — Write `.claude/harness-answers.yml` (D-2 provenance sidecar)

Create `.claude/harness-answers.yml` in the target repo root:

```yaml
# Harness provenance sidecar (D-2 — HARNESS_PLUGINIZATION_DESIGN_V1.md §3)
# Written by /init · Updated by /harness-update
# DO NOT edit _engine_version manually — managed by /harness-update
_engine_version: "<plugin version from plugin.json>"
_engine_commit: ""
project_repo: "<answers.project_repo>"
stack: "<answers.stack>"
phase_model: <answers.phase_model>
session_docs: <answers.session_docs>
archive_path: "<answers.archive_path>"
worklog_path: "<answers.worklog_path>"
```

> `_engine_version` must match `plugin.json` → `version` at init time.
> `archive_path` / `worklog_path` here are the SSOT — do NOT duplicate these values as prose in CLAUDE.md (SSOT-in-prose violation, [SSOT 서술에 값 금지] policy).

### Step 4 — Write `CLAUDE.md` with D-1 sentinel zones

Generate `CLAUDE.md` in the target repo root using the **2-zone structure** (D-1 decision):

```markdown
<!-- HARNESS:START v<_engine_version> -->
# <project_repo> — Claude Code Harness Instructions

## Language · Persona
- Rule files (CLAUDE.md · skills · hooks) = English. User-facing output = Korean.
- Unfamiliar tech → Spring Boot / JPA / AWS analogies

## Gate A → E (mandatory for all projects)
Each Gate is performed via /gate-a ~ /gate-e Skill commands.

| Gate | Skill | Deliverable | Stop point |
|------|-------|-------------|------------|
| A | /gate-a | Per-file detailed change plan | Await user approval |
| B | /gate-b | Code implementation | Await user confirmation |
| C | /gate-c | Verification (plan + execution) | Await user confirmation |
| D | /gate-d | Code quality improvement (conditional) | Await user confirmation |
| E | /gate-e | WORKLOG · archive | — |

## Build · Test
[Fill in per-repo test commands after /init]

## Archive Canonical Paths
See `.claude/harness-answers.yml` → `archive_path` / `worklog_path` (SSOT).
<!-- HARNESS:END -->
<!-- PROJECT-OWNED below -->

## Project Overview
[Fill in: project goal, stack, team context]

## MVP Demo Roadmap Guardrail
[Fill in if phase_model: true — Phase 1–4 table and per-Phase completion criteria]

## Prohibited (project-specific)
[Fill in per-repo prohibitions]
```

**Zone rules**:
- `<!-- HARNESS:START -->` … `<!-- HARNESS:END -->`: engine-owned. `/harness-update` overwrites this zone wholesale (Axis A).
- `<!-- PROJECT-OWNED below -->`: project-owned. `/harness-update` never touches below this marker.

### Step 5 — Write session document stubs (if `session_docs: true`)

Generate minimal `SESSION_INDEX.md` and `CURRENT_SESSION.md` in the target repo root.

**SESSION_INDEX.md stub**:
```markdown
---
project: "<project_repo>"
last_updated: "<today>"
gate: "⏸ (no active session)"
sessions_since_audit: 0
last_audit_date: ""
priority_note: ""
---

# Session Index

## Active / Planned Sessions

| Session ID | Title | Repo | Status |
|------------|-------|------|--------|

## Recent Completed (last 7)

| Session ID | Title | Repo | Status |
|------------|-------|------|--------|
```

**CURRENT_SESSION.md stub**:
```markdown
# Current Session State

> **Session ID**: (none — run /gate-a to start)
> **Status**: no active session

## Dashboard

| Item | Value |
|------|-------|
| Current Gate | — |
| Gate Progress | — |
| Start Date | — |
```

**Stub creation must be verified (do not silently skip)**: after writing each stub, confirm the file exists (`[ -f <repo>/SESSION_INDEX.md ]` / `[ -f <repo>/CURRENT_SESSION.md ]`). If either is absent, the Write step failed — retry it before proceeding. (Recurrence guard: a prior `/init` left a repo with `harness-answers.yml` present but both session stubs missing — `session_docs: true` was set yet Step 5 did not produce the files.)

### Step 6 — Wire Stop hooks into `.claude/settings.json`

Without this step, the session-dashboard·error-topics·gate-e guards never fire in the target repo (a prior `/init` produced `CLAUDE.md` + stubs but **no hook wiring** → `session-dashboard.html` was never generated).

Add a `Stop` hook array to the target repo's `.claude/settings.json` (create the file if absent; merge into the existing `hooks` object if present — do not clobber other hook events). Wire these 3 guards:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-dashboard-sync.py\" 2>/dev/null || true", "timeout": 10 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/gate-e-sync-guard.py\" 2>/dev/null || true", "timeout": 10 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/error-topics-guard.py\" 2>/dev/null || true", "timeout": 10 }
        ]
      }
    ]
  }
}
```

> **Path resolution**: prefer `${CLAUDE_PLUGIN_ROOT}/hooks/` (plugin-install topology). All 3 guards resolve their target repo via `CLAUDE_PROJECT_DIR` (3-tier fallback: custom env → `CLAUDE_PROJECT_DIR` → absolute), so wiring them here makes them operate on **this** repo, not the source repo. If the harness is used source-relative (not plugin-installed), substitute the source `plans/hooks/` absolute path instead.
> **dashboard-sync first**: keep `session-dashboard-sync.py` as the **first** Stop entry (HARNESS-STALE-GUARD-3 ordering — it is fail-open and regenerates the HTML before the consistency guards run).

### Step 7 — Generate the initial `session-dashboard.html`

After hook wiring, run `session-dashboard-sync.py` once manually so the dashboard exists immediately (subsequent Stop events auto-refresh it):

```bash
CLAUDE_PROJECT_DIR=<target repo root> python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-dashboard-sync.py"
```

Confirm `session-dashboard.html` was created at the repo root. If `CLAUDE_PLUGIN_ROOT` is unavailable (source-relative use), call the script at its source `plans/hooks/` path with the same `CLAUDE_PROJECT_DIR` env.

## Verification Checklist (for Gate C after /init)

- [ ] C1: `.claude/harness-answers.yml` exists and is valid YAML
- [ ] C2: `_engine_version` matches `plugin.json` → `version`
- [ ] C3: `CLAUDE.md` contains `<!-- HARNESS:START -->` and `<!-- HARNESS:END -->` and `<!-- PROJECT-OWNED below -->`
- [ ] C4: `archive_path` / `worklog_path` appear only in `harness-answers.yml`, not duplicated as hardcoded prose in `CLAUDE.md`
- [ ] C5: `SESSION_INDEX.md` and `CURRENT_SESSION.md` stubs exist (if `session_docs: true`)
- [ ] C6: `.claude/settings.json` has a `Stop` hook array wiring all 3 guards (`session-dashboard-sync.py` first, `gate-e-sync-guard.py`, `error-topics-guard.py`)
- [ ] C7: `session-dashboard.html` exists at the repo root (generated by Step 7)

## Notes

- `/harness-update` reads `_engine_version` from `harness-answers.yml` and reconciles the HARNESS zone in `CLAUDE.md` (Axis A) when the engine version bumps.
- Re-running `/init` on an existing repo: warn the user if `CLAUDE.md` already has a HARNESS zone to avoid overwriting customizations in that zone.
- `archive_path` and `worklog_path` in `harness-answers.yml` replace the hardcoded prose values that previously lived in `CLAUDE.md §Archive Canonical Paths` — this resolves the SSOT-in-prose violation.
- Step 6/7 (hook wiring + dashboard generation) close the gap where `/init` previously produced docs but no live dashboard/guards. All 3 wired guards resolve their target repo via `CLAUDE_PROJECT_DIR` (3-tier fallback), so the same hook scripts serve any repo without per-repo path edits.
