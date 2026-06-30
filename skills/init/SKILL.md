---
name: init
description: "Initialize harness scaffold files in a new repo (CLAUDE.md with D-1 sentinel zones + session docs + D-2 provenance sidecar). Use on '/init', 'harness init', '하네스 초기화', or when bootstrapping a new project with the patrick-work-harness plugin."
---

# /init Skill — Harness Scaffold Initializer

> Implements R-4-4 from `REPORTS/HARNESS_PLUGINIZATION_DESIGN_V1.md`.
> Prerequisite: harness plugin installed (plugin.json present, marketplace registered).
> Constraint: F5 — CLAUDE.md at plugin root is NOT loaded as project context. This skill generates files directly in the target repo.

## When to Use

- Bootstrapping a new repository with the patrick-work-harness plugin
- Setting up Gate A–E workflow + session document structure from scratch
- Re-initializing after a harness version bump (when `.claude/harness-answers.yml` is absent)

## Prerequisites

- Claude Code with patrick-work-harness plugin enabled
- Write access to the target repository root
- Know: repo name, primary stack, whether MVP Phase model applies, archive/worklog paths

## Procedure

### Step 1 — Codebase analysis

#### 1-a. Code scan

Scan the target repo to detect:
- Primary language/framework (look for `build.gradle.kts` / `package.json` / `requirements.txt` / `go.mod`)
- Existing `CLAUDE.md` (if present, warn before overwriting the HARNESS zone)
- Existing `.claude/harness-answers.yml` (if present, load existing answers as defaults)

#### 1-b. Context document discovery (project intent the code scan cannot reveal)

Code scan reveals *structure*; it cannot reveal *why the project exists*. Discover existing planning /
business / discussion documents already in the repo so the generated baseline docs carry product intent —
not just code facts. This `context_summary` is consumed downstream by Step 4 (CLAUDE.md Project Overview)
and Step 8-b (ARCHITECTURE / DATA_FLOW). Ordering 1 → 4 → 8 guarantees it exists before consumption.

**Search locations**: repo root + `docs/` + planning dirs (`docs/planning/` · `docs/spec/` · `docs/product/` · `기획/` · `docs/기획/`).

**Filename patterns** (case-insensitive, English + Korean):
`PRD` · `PRODUCT` · `REQUIREMENT(S)` · `ROADMAP` · `VISION` · `PROPOSAL` · `BUSINESS` · `SPEC`
· `기획` · `사업계획` · `제안` · `요구사항` · `논의` · `회의` · plus `README.md`.

**Bound (token-blowup guard)**: read at most ~5 most-relevant files (prefer explicit product/business
docs over `README.md`); bound the per-file read. Never read the whole repo.

**Extract**: project goal/purpose · target users · key domain entities · business constraints · scope boundaries.

**Output**: `context_summary` = discovered source paths + a 3–6 line synthesized summary.
If nothing is found → `context_summary = none`.

**Hallucination guard** (DOCBASE spec constraint #6): synthesize only from facts actually read; cite the
source paths; mark anything uncertain with `<!-- verify -->`. Never invent goals not present in the sources.

**Failure-safe** (DOCBASE spec constraint #5): if a candidate file is unreadable, skip it and continue —
never abort `/init` or silently produce nothing. Worst case degrades to `context_summary = none`.

### Step 2 — Answers interview

Ask the user (or infer from Step 1 scan) for the following fields:

| Field | Description | Default |
|-------|-------------|---------|
| `project_repo` | Short repo identifier (e.g. `my-project`) | inferred from directory name |
| `stack` | Primary stack tag (e.g. `kotlin-spring`, `react-ts`, `python`) | inferred |
| `phase_model` | Enable MVP Phase 1–4 guardrail in CLAUDE.md? | `true` |
| `session_docs` | Generate SESSION_INDEX.md + CURRENT_SESSION.md stubs? | `true` |
| `archive_path` | Absolute path for session archive files | ask user |
| `worklog_path` | Absolute path for WORKLOG files | ask user |
| `code_repos` | List of repo dir names that have `docs/rules/error_topics/` (used by error-topics-guard) | ask user (empty = guard skipped) |
| `docker_blocked_containers` | List of container name rules for docker-command-guard (see format below) | ask user (empty = TTY-only guard) |

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

# Repo names that own docs/rules/error_topics/ (used by error-topics-guard).
# Leave empty [] to skip the guard entirely for this project.
code_repos:
  - "<repo-dir-name>"   # e.g. "my-api", "my-frontend", "my-crawler"

# Container rules for docker-command-guard (project-specific blocked containers).
# TTY (-it) blocking is always on regardless of this list.
# Leave empty [] to enforce TTY-only guard (no project-specific rules).
docker_blocked_containers:
  - name: "<container-name>"    # exact container name used in `docker exec <name>`
    reason: "<why it is blocked>"
  # - name: "<runtime-container>"
  #   gradle: true              # also block gradlew/gradle commands on this container
  #   reason: "JRE only, no Gradle"
```

> `_engine_version` must match `plugin.json` → `version` at init time.
> `archive_path` / `worklog_path` here are the SSOT — do NOT duplicate these values as prose in CLAUDE.md (SSOT-in-prose violation, [SSOT 서술에 값 금지] policy).
> `code_repos` / `docker_blocked_containers` are the SSOT for hook configuration — do NOT hardcode repo names or container names anywhere else.

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
[Populated from Step 1-b context_summary if found — project goal, target users, business context, with `> Source: <paths>`. Else: [Fill in: project goal, stack, team context]]

## MVP Demo Roadmap Guardrail
[Fill in if phase_model: true — Phase 1–4 table and per-Phase completion criteria]

## Prohibited (project-specific)
[Fill in per-repo prohibitions]
```

> **Project Overview population (Step 1-b → here)**: if `context_summary` ≠ none, write the synthesized
> project goal / target users / business context (2–5 lines) into `## Project Overview` and append a
> `> Source: <discovered paths>` line. If `context_summary` = none, keep the `[Fill in: …]` placeholder.
> This lands in the PROJECT-OWNED zone and is written only on a fresh `/init` (re-init keeps the existing
> HARNESS-zone warning — never overwrite a project's customized Project Overview).

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

### Step 8 — Generate document baseline (if `--docs` ≠ none)

Generate codebase documentation files in the target repo root. Controlled by the `--docs` flag:

| Flag | Effect |
|------|--------|
| `--docs=full` **(default)** | Generate all 4 files: PROJECT_MAP.md · ARCHITECTURE.md · DATA_FLOW.md · DOC_INDEX.md |
| `--docs=minimal` | Generate PROJECT_MAP.md only |
| `--docs=none` | Skip Step 8 entirely |

> Flag naming follows the `--check` precedent in `/harness-update` (consistent `--<key>=<value>` form).

#### 8-a. Brownfield guard (run before any write)

For each file to be generated, check if a same-named file already exists in the target repo root:
- **Not present** → write normally
- **Present** → write as `<name>_harness.md` (e.g. `PROJECT_MAP_harness.md`) + output warning:
  `⚠️ PROJECT_MAP.md already exists — wrote PROJECT_MAP_harness.md instead. Merge manually.`
  Never overwrite the existing file.

#### 8-b. Context incorporation (from Step 1-b discovery)

Reuse the `context_summary` produced in Step 1-b — do **not** re-search the repo. Incorporate it into the
generated baseline docs so they carry product intent:
- **`context_summary` ≠ none** → ARCHITECTURE.md: fill the `## Purpose / System Boundaries` section with
  the project goal · key domain entities · scope boundaries (cite source paths). DATA_FLOW.md: note the
  key domain entities / flows named in the summary.
- **`context_summary` = none** → leave a placeholder: `<!-- No context docs found — fill in manually -->`

The Step 1-b hallucination + failure-safe guards apply unchanged (read facts only · cite source paths ·
mark uncertain with `<!-- verify -->`).

#### 8-c. Generate PROJECT_MAP.md

Scan the repo and produce:

```markdown
# PROJECT_MAP — <project_repo>

## Directory Structure (top 2 levels)
<tree output, depth 2, skip .git / __pycache__ / node_modules>

## Technology Stack
<detected from build.gradle.kts / package.json / requirements.txt / go.mod>

## Module List
<skills/: list SKILL.md names | hooks/: list *.py filenames | config: plugin.json / marketplace.json>
```

#### 8-d. Generate ARCHITECTURE.md

Scan entry points and dependency chain:

```markdown
# ARCHITECTURE — <project_repo>

## Purpose / System Boundaries
<filled by Step 8-b from context_summary: project goal · key domain entities · scope boundaries + `> Source: <paths>`>
<!-- No context docs found — fill in manually -->

## Entry Points
- install.sh — CLI installer
- skills/*/SKILL.md — harness skill definitions (list names from frontmatter `name:`)

## Layer Structure
| Layer | Path | Role |
|-------|------|------|
| Skills | skills/ | Gate A–E + utility skill definitions |
| Hooks | hooks/ | Stop/PreToolUse event handlers |
| Config | plugin.json · marketplace.json | Plugin metadata |
| Docs | README.md · CHANGELOG.md | User-facing documentation |

## Dependency Chain
<parse `import` statements in hooks/*.py to list inter-module dependencies>
```

#### 8-e. Generate DATA_FLOW.md

Trace code-verifiable data paths:

```markdown
# DATA_FLOW — <project_repo>

## Session Dashboard Pipeline
CURRENT_SESSION.md / SESSION_INDEX.md
  → session-dashboard-sync.py (Stop hook)
  → session_dashboard_parsers.py (parse)
  → session_dashboard_renderer.py (render)
  → session-dashboard.html

## HARNESS Zone Update Path
CLAUDE.md (HARNESS zone)
  → harness-update skill
  → reconcile (overwrite HARNESS:START…HARNESS:END)
  → harness-answers.yml (_engine_version bump)

## Install Path
install.sh (--version / --target / --dry-run flags)
  → GitHub Releases tarball download
  → skills/ · hooks/ extracted to target repo

## Domain Entities / Flows
<filled by Step 8-b from context_summary if present>
<!-- No context docs found — fill in manually -->
```

#### 8-f. Generate DOC_INDEX.md

```markdown
# DOC_INDEX — <project_repo>

> Document status dashboard. Updated by `/init` on first run; sections updated by each Gate.

| Document | Layer | Updated by | Status |
|----------|-------|------------|--------|
| PROJECT_MAP.md | 1 | /init | Generated |
| ARCHITECTURE.md | 1 | /init | Generated |
| DATA_FLOW.md | 1 | /init | Generated |
| DOC_INDEX.md | meta | /init | Generated |
| FEATURE_SPEC.md | 2 | Gate A | Pending |
| API_SPEC.md | 2 | Gate B | Pending |
| TEST_PLAN.md | 2 | Gate C–D | Pending |
| ERROR_HANDLING.md | 2 | Gate D | Pending |
| DECISION_LOG.md | 2 | All gates (ADR) | Pending |
```

Status values: `Generated` / `Pending` / `Updated (YYYY-MM-DD)` / `Not present`

> Layer 2 documents (FEATURE_SPEC through DECISION_LOG) are **not** generated by Step 8 — they are created by Step 9 with skeleton + Gate markers only.

### Step 9 — Generate Layer 2 document skeletons (if `--docs=full`)

Generate 5 Layer 2 documents with skeleton structure and Gate markers only.
No content is filled in — markers indicate which Gate fills each section.

| Document | Updated by | Purpose |
|----------|------------|---------|
| FEATURE_SPEC.md | Gate A | Feature intent + acceptance criteria |
| API_SPEC.md | Gate B | Endpoint contracts + request/response shapes |
| TEST_PLAN.md | Gate C–D | Test cases + verification checklist |
| ERROR_HANDLING.md | Gate D | Failure paths + recovery strategies |
| DECISION_LOG.md | All gates (ADR) | Architecture decisions + rationale |

#### 9-a. Brownfield guard

Same rule as Step 8: if a same-named file already exists in the target repo root, write as `<name>_harness.md` and output a warning. Never overwrite.

#### 9-b. File naming

File names are fixed (`FEATURE_SPEC.md`, etc.). Replace `<session_id>` placeholder inside each file with the actual session name at Gate A time.

#### 9-c. Skeleton templates

**FEATURE_SPEC.md**:
```markdown
# FEATURE_SPEC — <session_id>

## Overview
<!-- Gate A에서 채워짐 -->

## Acceptance Criteria
<!-- Gate A에서 채워짐 -->

## Out of Scope
<!-- Gate A에서 채워짐 -->
```

**API_SPEC.md**:
```markdown
# API_SPEC — <session_id>

## Endpoints
<!-- Gate B에서 채워짐 -->

## Request / Response Shapes
<!-- Gate B에서 채워짐 -->

## Error Codes
<!-- Gate B에서 채워짐 -->
```

**TEST_PLAN.md**:
```markdown
# TEST_PLAN — <session_id>

## Test Cases
<!-- Gate C에서 채워짐 -->

## Verification Checklist
<!-- Gate D에서 채워짐 -->
```

**ERROR_HANDLING.md**:
```markdown
# ERROR_HANDLING — <session_id>

## Failure Paths
<!-- Gate D에서 채워짐 -->

## Recovery Strategies
<!-- Gate D에서 채워짐 -->
```

**DECISION_LOG.md**:
```markdown
# DECISION_LOG — <session_id>

## Architecture Decision Records (ADR)

<!-- 각 Gate에서 ADR 추가 -->
<!-- 형식: ### [YYYY-MM-DD] <결정 제목> / Context / Decision / Consequences -->
```

#### 9-d. DOC_INDEX.md update

After writing the 5 files, update DOC_INDEX.md: change each Layer 2 row's `Status` from `Pending` to `Skeleton`.

## Verification Checklist (for Gate C after /init)

- [ ] C1: `.claude/harness-answers.yml` exists and is valid YAML
- [ ] C2: `_engine_version` matches `plugin.json` → `version`
- [ ] C3: `CLAUDE.md` contains `<!-- HARNESS:START -->` and `<!-- HARNESS:END -->` and `<!-- PROJECT-OWNED below -->`
- [ ] C4: `archive_path` / `worklog_path` appear only in `harness-answers.yml`, not duplicated as hardcoded prose in `CLAUDE.md`
- [ ] C5: `SESSION_INDEX.md` and `CURRENT_SESSION.md` stubs exist (if `session_docs: true`)
- [ ] C6: `.claude/settings.json` has a `Stop` hook array wiring all 3 guards (`session-dashboard-sync.py` first, `gate-e-sync-guard.py`, `error-topics-guard.py`)
- [ ] C7: `session-dashboard.html` exists at the repo root (generated by Step 7)
- [ ] C8: `--docs=full` run → PROJECT_MAP.md · ARCHITECTURE.md · DATA_FLOW.md · DOC_INDEX.md all present at repo root
- [ ] C9: Brownfield conflict → `_harness` suffix file written, original file untouched
- [ ] C10: `--docs=none` run → none of the 4 doc files generated (skip confirmed)
- [ ] C11: `--docs=full` run → FEATURE_SPEC.md · API_SPEC.md · TEST_PLAN.md · ERROR_HANDLING.md · DECISION_LOG.md all present at repo root
- [ ] C12: Each Layer 2 file contains Gate markers (`<!-- Gate` appears ≥ 1 per file) and no filled content
- [ ] C13: DOC_INDEX.md Layer 2 rows show `Skeleton` status (not `Pending`) after Step 9
- [ ] C14: FEATURE_SPEC.md has content filled in the Gate A section (not just a marker)
- [ ] C15: API_SPEC.md has content filled in the Gate B section
- [ ] C16: TEST_PLAN.md has content filled in Gate C and D sections
- [ ] C17: ERROR_HANDLING.md has content filled in the Gate D section
- [ ] C18: DECISION_LOG.md has at least one ADR entry (any gate)
- [ ] C19: `--docs=full` on a repo containing a planning/business doc → ARCHITECTURE.md `Purpose / System Boundaries` references the discovered content (not just a placeholder) and cites the source paths
- [ ] C20: CLAUDE.md `Project Overview` is populated from the discovered context docs (or keeps the `[Fill in: …]` placeholder when none found)
- [ ] C21: no context docs found → `context_summary = none`, all consumers fall back to the placeholder gracefully (no crash / no silent doc skip)

### Step 10 — Fill Layer 2 document sections per Gate (if `--docs=full`)

This step defines **what content to write into each Layer 2 document** at each Gate. Step 9 created the skeleton with markers; Step 10 describes the fill rules. Actual filling happens as the AI works through Gates A~E — this step records the rules so every gate knows its responsibility.

| Document | Gate | Section to fill | Content guideline |
|----------|------|-----------------|-------------------|
| FEATURE_SPEC.md | A | Feature intent + acceptance criteria | Write 2–5 acceptance criteria based on the Gate A plan scope |
| API_SPEC.md | B | Endpoint contracts + request/response shapes | Write only endpoints touched in this session |
| TEST_PLAN.md | C | Test cases | List happy/edge/error cases per changed unit |
| TEST_PLAN.md | D | Verification checklist | Fill after Gate D run completes |
| ERROR_HANDLING.md | D | Failure paths + recovery strategies | Document failures found in Gate D verification |
| DECISION_LOG.md | Any | ADR entry | Add one ADR per non-obvious architectural decision |

#### 10-a. Brownfield guard

Same pattern as Step 9: if the Layer 2 file already exists with user content (not a harness-generated skeleton), do **not** overwrite the filled sections. Detect by checking whether a section contains text beyond `<!-- Gate` markers. If content exists, append new content in a `<!-- harness-added -->` block below the existing content.

#### 10-b. Fill format per document

**FEATURE_SPEC.md** (Gate A fills):
```markdown
## Overview
<!-- Gate A에서 채워짐 -->
<one-sentence summary of what this session adds or changes>

## Acceptance Criteria
<!-- Gate A에서 채워짐 -->
- AC1: <measurable criterion>
- AC2: <measurable criterion>
```

**API_SPEC.md** (Gate B fills):
```markdown
## Endpoints Changed
<!-- Gate B에서 채워짐 -->
### <METHOD> <path>
- Request: `<body or params>`
- Response 200: `<shape>`
- Response 4xx: `<error shape>`
```

**TEST_PLAN.md** (Gate C fills test cases, Gate D fills checklist):
```markdown
## Test Cases
<!-- Gate C에서 채워짐 -->
| Case | Input | Expected | Type |
|------|-------|----------|------|
| TC1  | …     | …        | happy/edge/error |

## Verification Checklist
<!-- Gate D에서 채워짐 -->
- [ ] All happy-path test cases PASS
- [ ] Error-path test cases PASS
- [ ] No regression in existing tests
```

**ERROR_HANDLING.md** (Gate D fills):
```markdown
## Failure Paths
<!-- Gate D에서 채워짐 -->
| Failure | Symptom | Root cause | Recovery |
|---------|---------|------------|----------|

## Recovery Strategies
<!-- Gate D에서 채워짐 -->
- <strategy 1>
```

**DECISION_LOG.md** (any Gate fills an ADR):
```markdown
### [<YYYY-MM-DD>] <Decision title>
<!-- Gate <X>에서 채워짐 -->
- **Context**: <why this decision was needed>
- **Decision**: <what was chosen>
- **Consequences**: <trade-offs, constraints, follow-ups>
```

#### 10-c. When NOT to fill

- If a Gate produces no artifact for a document (e.g. no API changes → API_SPEC unchanged), leave the marker in place. Do not write placeholder text like "N/A" — an empty marker is the correct state.
- Do not backfill sections from a later Gate into an earlier Gate's section (e.g. do not fill FEATURE_SPEC at Gate C).

#### 10-d. DOC_INDEX.md status progression

Update DOC_INDEX.md Layer 2 row `Status` as each section is filled:

| Status | Meaning |
|--------|---------|
| `Pending` | File not yet created (before Step 9) |
| `Skeleton` | File created with markers only (after Step 9) |
| `Partial` | At least one Gate section filled |
| `Complete` | All gates for this session have filled their sections |

## Notes

- `/harness-update` reads `_engine_version` from `harness-answers.yml` and reconciles the HARNESS zone in `CLAUDE.md` (Axis A) when the engine version bumps.
- Re-running `/init` on an existing repo: warn the user if `CLAUDE.md` already has a HARNESS zone to avoid overwriting customizations in that zone.
- `archive_path` and `worklog_path` in `harness-answers.yml` replace the hardcoded prose values that previously lived in `CLAUDE.md §Archive Canonical Paths` — this resolves the SSOT-in-prose violation.
- Step 6/7 (hook wiring + dashboard generation) close the gap where `/init` previously produced docs but no live dashboard/guards. All 3 wired guards resolve their target repo via `CLAUDE_PROJECT_DIR` (3-tier fallback), so the same hook scripts serve any repo without per-repo path edits.
