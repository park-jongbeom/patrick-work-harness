---
name: harness-update
description: "Upgrade an existing harness-initialized repo to the latest engine release. Shows what changed (CHANGELOG), checks what needs applying (checklist), then applies on approval. Use on '/harness-update', 'harness upgrade', '하네스 업데이트', or when _engine_version is behind the latest release."
---

# /harness-update Skill — Harness Full Upgrade

> Implements the full harness upgrade path: version check → CHANGELOG → checklist → approval → apply.
> Analogous to `npm update` / `brew upgrade` — upgrades the entire installed harness, not just `CLAUDE.md`.
> Prerequisite: `/init` has been run (`.claude/harness-answers.yml` exists).

## When to Use

- After a new harness release is available (patrick-work-harness tag bump)
- When `session-dashboard.html` is missing, Stop hooks are unwired, or session stubs are absent on an existing init'd repo
- To verify whether a repo is fully up to date without applying changes (`--check` mode)

## Invocation Modes

| Mode | How to invoke | Effect |
|------|---------------|--------|
| **Default (upgrade)** | `/harness-update` | Steps 1→6 — check, report, await approval, apply |
| **Check only** | `/harness-update --check` | Steps 1→3 only — report without writing |

---

## Step 1 — Read provenance and resolve engine version

Read `.claude/harness-answers.yml` in the **current working repo** (the repo Claude Code is opened in):
- `_engine_version`: version at last `/init` or `/harness-update` run
- `session_docs`: bool — whether session stubs (SESSION_INDEX / CURRENT_SESSION) are expected

Resolve the latest engine version via this priority order:

1. `${CLAUDE_PLUGIN_ROOT}/plugin.json` → `version` (plugin-install topology)
2. Local patrick-work-harness clone: search for `plugin.json` under common paths
   (`/media/ubuntu/data120g/patrick-work-harness/plugin.json`, `~/.claude/plugins/*/plugin.json`)
3. If neither is found: halt with "Cannot resolve engine version — ensure CLAUDE_PLUGIN_ROOT is set or patrick-work-harness is cloned locally."

| Comparison | Action |
|------------|--------|
| `_engine_version == latest` | Output "✅ 이미 최신 버전 ({ver}) — 체크리스트만 실행합니다." then jump to Step 3 (checklist only, no zone rewrite) |
| `_engine_version < latest` | Proceed to Step 2 |
| `_engine_version > latest` | Halt: "⚠️ provenance가 설치 버전보다 높습니다 — 수동 확인 필요." |

---

## Step 2 — Display CHANGELOG

Read `CHANGELOG.md` from the engine source (same directory as `plugin.json` resolved in Step 1).

Extract all version sections **newer than `_engine_version`** (sections between `## [X.Y.Z]` headers where X.Y.Z > _engine_version, semver order).

Output format:
```
── 변경 내역 ({_engine_version} → {latest}) ──────────
  ## [1.0.1] - 2026-06-26
    Added: /harness-update 스킬 (버전 확인→체크리스트→승인→일괄 갱신)
  ...
──────────────────────────────────────────────────────
```

If `CHANGELOG.md` is absent or the section is empty, output "변경 내역 없음 (CHANGELOG 미존재)" and continue.

---

## Step 3 — Checklist: what needs applying

Inspect the current repo state across 4 axes. Mark each ✅ (ok) or ❌ (needs update):

| # | Axis | Check | Needs update condition |
|---|------|-------|------------------------|
| A | **HARNESS zone** | `CLAUDE.md` contains `<!-- HARNESS:START v{latest} -->` | Version tag differs from `latest` |
| B | **Stop hook 3종** | `.claude/settings.json` Stop array contains all 3: `session-dashboard-sync.py`, `gate-e-sync-guard.py`, `error-topics-guard.py` | Any of the 3 is absent |
| C | **session-dashboard.html** | File exists at repo root | Absent |
| D | **Session stubs** | `SESSION_INDEX.md` and `CURRENT_SESSION.md` exist at repo root | Either absent AND `session_docs: true` in harness-answers.yml |

Output the checklist table with ✅/❌ per row, then:
- If all ✅: "모든 항목 최신 상태 — 갱신 불필요합니다."
- If `--check` mode: stop here (no file writes).
- If ≥1 ❌: list the items needing update and proceed to Step 4.

---

## Step 4 — Await user approval

Output:
```
위 {N}항목을 적용하겠습니다.
「harness-update 승인」으로 응답하면 실행합니다.
```

**STOP — await user response before any file writes.**

Recognized approval phrases: 「harness-update 승인」「승인」「적용」「진행」.
On any other response, abort with "갱신을 취소했습니다."

---

## Step 5 — Apply updates (checklist-driven, conditional per axis)

Execute only the axes marked ❌ in Step 3. Axes already ✅ are skipped silently.

### Axis A — HARNESS zone reconcile

Reuse `/doc-update` Step 4 logic:
- Locate `<!-- HARNESS:START` … `<!-- HARNESS:END -->` sentinels in `CLAUDE.md`
- Overwrite the zone wholesale with the current engine template, substituting `project_repo` from `harness-answers.yml`
- Update version tag to `<!-- HARNESS:START v{latest} -->`
- Everything after `<!-- PROJECT-OWNED below -->` is never touched

If sentinels are absent: output "⚠️ HARNESS sentinel 없음 — `/init`을 먼저 실행하세요." and skip this axis.

### Axis B — Wire Stop hooks

Read `.claude/settings.json` (create `{"hooks":{}}` if absent).

Check which of the 3 guards are missing from the Stop array:
- `session-dashboard-sync.py`
- `gate-e-sync-guard.py`
- `error-topics-guard.py`

**Prepend** the missing guards to the existing Stop array (preserve all existing entries).
`session-dashboard-sync.py` must always be the **first** Stop entry (HARNESS-STALE-GUARD-3 ordering).

Use `${CLAUDE_PLUGIN_ROOT}/hooks/` paths. All 3 guards resolve their target repo via `CLAUDE_PROJECT_DIR` (3-tier fallback) — no per-repo path edits needed.

Result JSON shape:
```json
{
  "hooks": {
    "Stop": [{
      "hooks": [
        { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-dashboard-sync.py\" 2>/dev/null || true", "timeout": 10 },
        { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/gate-e-sync-guard.py\" 2>/dev/null || true", "timeout": 10 },
        { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/error-topics-guard.py\" 2>/dev/null || true", "timeout": 10 }
        /* existing entries preserved after this point */
      ]
    }]
  }
}
```

### Axis C — Generate session-dashboard.html

Run the sync script once manually:
```bash
CLAUDE_PROJECT_DIR=<repo root> python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-dashboard-sync.py"
```

If `CLAUDE_PLUGIN_ROOT` is unavailable, use the source path:
```bash
CLAUDE_PROJECT_DIR=<repo root> python3 /media/ubuntu/data120g/plans/hooks/session-dashboard-sync.py
```

Confirm `session-dashboard.html` exists at the repo root after execution.

### Axis D — Create session stubs

Only when `session_docs: true` in `harness-answers.yml` AND stub(s) are absent.

Create missing stubs using the same templates as `/init` Step 5:

**SESSION_INDEX.md** stub:
```markdown
---
project: "{project_repo}"
last_updated: "{YYYY-MM-DD}"
gate: "신규 — 다음 작업 시 /gate-a로 시작"
sessions_since_audit: 0
last_audit_date: ""
priority_note: ""
next_action: "새 작업 시 /gate-a로 시작."
---

# 세션 인덱스

| 세션 ID | 제목 | 저장소 | 상태 |
|---------|------|--------|------|
```

**CURRENT_SESSION.md** stub:
```markdown
# 현재 세션 상태

> **세션 ID**: (미정 — /gate-a로 시작)
> **현재 상태**: 신규
> **직전 세션**: —

> **세션 주제**: harness-update 백필 적용 완료 — 다음 작업 시 /gate-a로 시작
```

After writing, verify both files exist (`ls` check). If either is absent after write, retry once.

---

## Step 6 — Update `_engine_version`

Write `_engine_version: "{latest}"` back to `.claude/harness-answers.yml`.
All other fields remain unchanged.

---

## Verification Checklist (for Gate C after /harness-update)

- [ ] C1: `harness-answers.yml` → `_engine_version` equals latest engine version
- [ ] C2: `CLAUDE.md` HARNESS zone version tag matches latest: `<!-- HARNESS:START v{latest} -->`
- [ ] C3: `.claude/settings.json` Stop array contains all 3 guards with `session-dashboard-sync.py` first
- [ ] C4: `session-dashboard.html` exists at repo root
- [ ] C5: Already-up-to-date repo exits cleanly at Step 1 with "✅ 이미 최신 버전"
- [ ] C6: `--check` mode produces no file writes (read-only confirmed by grep)

---

## Notes

- `/harness-update` is **explicit-invoke only** — same trust-boundary as `/doc-update` (D-4 decision). The SessionStart hook may detect version mismatch and *notify*, but reconciliation requires explicit invocation.
- Idempotent: re-running when already up to date exits cleanly at Step 1 or reports all-✅ at Step 3.
- **Relation to `/doc-update`**: `/doc-update` is narrow (CLAUDE.md HARNESS zone only). `/harness-update` is the full upgrade (HARNESS zone + hooks + dashboard + stubs). Use `/harness-update` as the standard upgrade path; `/doc-update` is retained for HARNESS-zone-only reconciliation.
- **Relation to `/init`**: `/init` is for new repos. `/harness-update` is for existing init'd repos. Never run `/init` on an existing repo to apply updates — use `/harness-update`.
