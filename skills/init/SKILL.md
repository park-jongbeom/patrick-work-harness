---
name: init
description: "Initialize harness scaffold files in a new repo (CLAUDE.md with D-1 sentinel zones + session docs + D-2 provenance sidecar). Use on '/init', 'harness init', '하네스 초기화', or when bootstrapping a new project with the patrick-work-harness plugin."
---

# /init Skill — Harness Scaffold Initializer

> Implements R-4-4 from `REPORTS/HARNESS_PLUGINIZATION_DESIGN_V1.md`.
> Prerequisite: harness plugin installed (plugin.json present, marketplace registered).
> Constraint: F5 — CLAUDE.md at plugin root is NOT loaded as project context. This skill generates files directly in the target repo.

## When to Use

- Bootstrapping a new repository with the patrick-work-harness
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
| `project_repo` | Short repo identifier (e.g. `YOUR_PROJECT`) | inferred from directory name |
| `stack` | Primary stack tag (e.g. `kotlin-spring`, `react-ts`, `python`) | inferred |
| `phase_model` | Enable MVP Phase 1–4 guardrail in CLAUDE.md? | `true` |
| `session_docs` | Generate SESSION_INDEX.md + CURRENT_SESSION.md stubs? | `true` |
| `archive_path` | Absolute path for session archive files | ask user |
| `worklog_path` | Absolute path for WORKLOG files | ask user |

### Step 3 — Write `.claude/harness-answers.yml` (D-2 provenance sidecar)

Create `.claude/harness-answers.yml` in the target repo root:

```yaml
# Harness provenance sidecar (D-2 — HARNESS_PLUGINIZATION_DESIGN_V1.md §3)
# Written by /init · Updated by /doc-update
# DO NOT edit _engine_version manually — managed by /doc-update (R-4-5)
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
- `<!-- HARNESS:START -->` … `<!-- HARNESS:END -->`: engine-owned. `/doc-update` overwrites this zone wholesale (R-4-5).
- `<!-- PROJECT-OWNED below -->`: project-owned. `/doc-update` never touches below this marker.

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

## Verification Checklist (for Gate C after /init)

- [ ] C1: `.claude/harness-answers.yml` exists and is valid YAML
- [ ] C2: `_engine_version` matches `plugin.json` → `version`
- [ ] C3: `CLAUDE.md` contains `<!-- HARNESS:START -->` and `<!-- HARNESS:END -->` and `<!-- PROJECT-OWNED below -->`
- [ ] C4: `archive_path` / `worklog_path` appear only in `harness-answers.yml`, not duplicated as hardcoded prose in `CLAUDE.md`
- [ ] C5: `SESSION_INDEX.md` and `CURRENT_SESSION.md` stubs exist (if `session_docs: true`)

## Notes

- `/doc-update` (R-4-5, not yet implemented) will read `_engine_version` from `harness-answers.yml` and reconcile the HARNESS zone in `CLAUDE.md` when the engine version bumps.
- Re-running `/init` on an existing repo: warn the user if `CLAUDE.md` already has a HARNESS zone to avoid overwriting customizations in that zone.
- `archive_path` and `worklog_path` in `harness-answers.yml` replace the hardcoded prose values that previously lived in `CLAUDE.md §Archive Canonical Paths` — this resolves the SSOT-in-prose violation.
