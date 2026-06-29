# ARCHITECTURE — patrick-work-harness

## Entry Points

- `install.sh` — CLI installer (--version / --target / --dry-run / SHA256 체크섬)
- `sync-from-source.sh` — 소스 저장소 → 배포본 파일 동기화
- `skills/*/SKILL.md` — 하네스 스킬 정의 (9종, frontmatter `name:` 식별)
- `hooks/*.py` — Stop / PreToolUse 이벤트 핸들러

## Layer Structure

| Layer | Path | Role |
|-------|------|------|
| Skills | `skills/` | Gate A–E + audit + doc-cleanup + harness-update + init 스킬 정의 |
| Hooks | `hooks/` | Stop / PreToolUse 이벤트 핸들러 (가드·동기화·집계) |
| Config | `plugin.json` · `.claude-plugin/` | 플러그인 메타데이터 · 마켓플레이스 등록 |
| Docs | `README.md` · `CHANGELOG.md` · `RELEASE_POLICY.md` | 사용자 문서 |
| CI | `.github/workflows/` | GitHub Actions 자동화 |

## Dependency Chain

```
session-dashboard-sync.py
  └─ imports session_dashboard_parsers.py  (parse_current_session, parse_session_index)
  └─ imports session_dashboard_renderer.py (generate_html)
       └─ reads  CURRENT_SESSION.md / SESSION_INDEX.md  (target repo)
       └─ writes session-dashboard.html    (target repo)

claude-gate-guard.py
  └─ reads  CURRENT_SESSION.md  (target repo, Gate 상태 파싱)
  └─ exit 2 on violation (PreToolUse 차단)

master-plan-stale-guard.py
  └─ reads  CURRENT_SESSION.md + 00_MASTER_PLAN.md  (target repo)
  └─ warns  on L7 status mismatch

gate-e-sync-guard.py / gate-a-sync-guard.py
  └─ reads  SESSION_INDEX.md + CURRENT_SESSION.md  (target repo)
  └─ blocks response termination on ✅E mismatch
```

## System Boundaries

<!-- PRD not found — fill in manually -->
<!-- System Boundaries: 플러그인은 Claude Code Stop / PreToolUse 훅 이벤트를 통해 target repo와 통신.
     target repo의 CURRENT_SESSION.md / SESSION_INDEX.md / 00_MASTER_PLAN.md를 읽기 전용 또는 경고 목적으로 사용.
     실제 파일 수정은 스킬(SKILL.md 지시)이 수행하며 훅은 감시·차단 역할만 담당. -->
