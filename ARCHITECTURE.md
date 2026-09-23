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

master-plan-stale-guard.py
  └─ reads  CURRENT_SESSION.md + 00_MASTER_PLAN.md  (target repo)
  └─ warns  on L7 status mismatch

gate-e-sync-guard.py / gate-a-sync-guard.py
  └─ reads  SESSION_INDEX.md + CURRENT_SESSION.md  (target repo)
  └─ blocks response termination on ✅E mismatch
```

## System Boundaries

플러그인은 Claude Code 의 **Stop / PreToolUse 훅 이벤트**를 통해 대상 저장소와 통신한다.
대상 저장소의 `CURRENT_SESSION.md` · `SESSION_INDEX.md` · `00_MASTER_PLAN.md` 는 읽기 또는
경고 목적으로만 쓴다. **실제 파일 수정은 스킬(SKILL.md 지시)이 수행하고, 훅은 감시·차단만 한다.**

### 하지 않는 것 (2026-09-23 확정)

- **Gate A 승인 전 편집을 사전 차단하지 않는다.** 그 역할을 하던 `claude-gate-guard.py` 를
  제거했다. 면제 목록(`.claude/`·`.github/`·`CURRENT_SESSION`·모든 `.md`)과 `Bash` 전용
  분기 때문에 실제로 걸러내는 것이 거의 없었고, 면제를 걷어내면 하네스가 자기 자신을
  고치는 것까지 막혀 오탐 비용이 이득을 넘는다. Gate 순서는 **절차와 Stop 시점 검사**가 지킨다.
- **사용자 자산을 지우지 않는다.** 설치 스크립트는 대상 프로젝트의 `.claude/skills/` 에서
  배포본에 없는 항목을 **보고만 하고 지우지 않으며**, 전역 `settings.json` 은 수정 전에
  타임스탬프 백업을 남긴다. 훅 전용 폴더는 소유 표식이 있을 때만 정리한다.
- **원본 저장소를 자동으로 덮어쓰지 않는다.** `sync-from-source.sh` 는 기본이 보고 전용이고,
  훅 반영은 `--apply-hooks` 를 명시하고 사설 경로 검사를 통과할 때만 일어난다.

> 공통 기준: **막지 못하는 가드보다 없는 가드가 낫고, 되돌릴 수 없는 삭제보다 남는 잔여가 낫다.**
