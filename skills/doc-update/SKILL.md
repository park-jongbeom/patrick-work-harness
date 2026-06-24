---
name: doc-update
description: "Update the HARNESS zone in a downstream repo's CLAUDE.md after an engine version bump, and sync _engine_version in harness-answers.yml. Use on '/doc-update', 'harness update', '하네스 업데이트', or when the engine version in plugin.json is newer than harness-answers.yml._engine_version."
---

# /doc-update Skill — Harness CLAUDE.md Reconciler

> Implements R-4-5 from `REPORTS/HARNESS_PLUGINIZATION_DESIGN_V1.md`.
> Prerequisite: `/init` has been run (`.claude/harness-answers.yml` exists, `CLAUDE.md` has D-1 sentinel zones).
> Design primitives: F7 (Copier-style zone overwrite) · F9 (cruft-style `--check`) · F10 (Nx-style version-key migration).

## When to Use

- After bumping `plugin.json` → `version` in the engine repo (patrick-work-harness)
- To check whether a downstream repo's HARNESS zone has drifted from the current engine (`--check` mode)
- To reconcile the HARNESS zone and update provenance after an engine version bump

## Prerequisites

- `.claude/harness-answers.yml` exists in the target repo (written by `/init`)
- `CLAUDE.md` contains D-1 sentinel zones:
  - `<!-- HARNESS:START v{N} -->` … `<!-- HARNESS:END -->`
  - `<!-- PROJECT-OWNED below -->`
- `plugin.json` is accessible (engine repo root)

## Invocation Modes

| Mode | How to invoke | Effect |
|------|---------------|--------|
| **Default (reconcile)** | `/doc-update` | Overwrites HARNESS zone + updates `_engine_version` |
| **Check only** | `/doc-update --check` | Reports drift without writing; exits with signal if drift found |

## Procedure

### Step 1 — Read provenance

Read `.claude/harness-answers.yml` and extract:
- `_engine_version`: the version at last `/init` or `/doc-update` run
- `project_repo`, `stack`, `archive_path`, `worklog_path` (needed to regenerate HARNESS zone content)

### Step 2 — Version comparison

Read `plugin.json` → `version` (current engine version).

| Comparison result | Action |
|-------------------|--------|
| `_engine_version == plugin.json.version` | Report "already up to date — no changes needed" and stop |
| `_engine_version < plugin.json.version` | Proceed to Step 3 |
| `_engine_version > plugin.json.version` | Warn "provenance is newer than installed plugin — manual check required" and stop |

> **Migration table** (F10 Nx-style): For each version between `_engine_version` and `plugin.json.version`,
> apply version-specific migration steps if defined. Current engine is at `0.1.0` — single version,
> no migration entries yet. Add entries here when bumping to `0.2.0+`.
>
> ```
> migrations:
>   # "0.1.0" -> "0.2.0": [describe breaking change, e.g. renamed sentinel tag]
> ```

### Step 3 — (--check mode) Drift report

*Skip this step in default (reconcile) mode.*

Compare the current `<!-- HARNESS:START -->` … `<!-- HARNESS:END -->` block in `CLAUDE.md`
against what the current engine version would generate (using `harness-answers.yml` answers).

Output a diff summary:
- Lines present in current HARNESS zone but absent from engine template
- Lines present in engine template but absent from current HARNESS zone

Finish with: **"Drift detected — run `/doc-update` (without `--check`) to reconcile."**
Do NOT write any files. Return exit signal (note in response) indicating drift found.

### Step 4 — Reconcile HARNESS zone

Read `CLAUDE.md` and locate the sentinel boundaries:
- Start: `<!-- HARNESS:START` (any version suffix)
- End: `<!-- HARNESS:END -->`

**Zone rules (D-1 decision)**:
- Everything between `<!-- HARNESS:START -->` and `<!-- HARNESS:END -->` is **engine-owned** → overwrite wholesale
- Everything after `<!-- PROJECT-OWNED below -->` is **project-owned** → never touch

Generate the new HARNESS zone content using the engine template (same template as `/init` Step 4),
substituting `project_repo` from `harness-answers.yml`.

Replace the old HARNESS zone with the new content. Update the version tag:
`<!-- HARNESS:START v{new_version} -->`.

> If `CLAUDE.md` does NOT contain the sentinel markers, halt and instruct the user to run `/init` first.

### Step 5 — Update `_engine_version` in harness-answers.yml

Write back `_engine_version: "{new_version}"` to `.claude/harness-answers.yml`.
All other fields (`project_repo`, `stack`, `phase_model`, `session_docs`, `archive_path`, `worklog_path`) remain unchanged.

## Verification Checklist (for Gate C after /doc-update)

- [ ] C1: `.claude/harness-answers.yml` → `_engine_version` equals `plugin.json` → `version`
- [ ] C2: `CLAUDE.md` HARNESS zone version tag matches new version: `<!-- HARNESS:START v{new_version} -->`
- [ ] C3: `<!-- PROJECT-OWNED below -->` content is unchanged (diff confirms no writes below the marker)
- [ ] C4: `--check` mode produced no file writes (read-only confirmed)
- [ ] C5: Version-equal case exits cleanly with "already up to date" message (no spurious writes)

## Notes

- `/doc-update` is **explicit-invoke only** (D-4 trust boundary decision: no SessionStart auto-mutate).
  The SessionStart hook may detect a version mismatch via manifest-diff (F6) and *notify* the user,
  but the actual reconciliation requires explicit `/doc-update` invocation.
- Re-running `/doc-update` when already up to date is safe (idempotent — Step 2 exits early).
- If the HARNESS zone contains project-specific customizations (e.g. additional `##` sections inserted
  inside the zone), those will be lost on reconcile. Move such content below `<!-- PROJECT-OWNED below -->`
  before running `/doc-update`.
