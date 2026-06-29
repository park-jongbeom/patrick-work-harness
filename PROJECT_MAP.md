# PROJECT_MAP — patrick-work-harness

## Directory Structure (top 2 levels)

```
patrick-work-harness/
├── .claude-plugin/
│   ├── marketplace.json      # Community marketplace registration
│   └── plugin.json           # Plugin metadata (version, author, keywords)
├── .github/
│   └── workflows/            # GitHub Actions CI/CD
├── hooks/                    # Stop / PreToolUse event handlers (Python)
├── skills/                   # Gate A–E + utility skill definitions
│   ├── audit/
│   ├── doc-cleanup/
│   ├── gate-a/
│   ├── gate-b/
│   ├── gate-c/
│   ├── gate-d/
│   ├── gate-e/
│   ├── harness-update/
│   ├── init/
│   └── SKILL_DETAIL.md       # Shared rubric / advisor escalation detail
├── CHANGELOG.md
├── GITHUB_RELEASE_GUIDE.md
├── README.md
├── RELEASE_POLICY.md
├── install.sh                # CLI installer (--version / --target / --dry-run)
├── plugin.json               # Root plugin descriptor
└── sync-from-source.sh       # Source → deploy sync helper
```

## Technology Stack

- **Runtime**: Python 3.x (hooks), Markdown (skills)
- **Test**: pytest (hooks unit tests)
- **CI/CD**: GitHub Actions (`.github/workflows/`)
- **Plugin system**: Claude Code plugin spec (`.claude-plugin/`)

## Module List

### Skills (9종)

| Skill | File |
|-------|------|
| audit | `skills/audit/SKILL.md` |
| doc-cleanup | `skills/doc-cleanup/SKILL.md` |
| gate-a | `skills/gate-a/SKILL.md` |
| gate-b | `skills/gate-b/SKILL.md` |
| gate-c | `skills/gate-c/SKILL.md` |
| gate-d | `skills/gate-d/SKILL.md` |
| gate-e | `skills/gate-e/SKILL.md` |
| harness-update | `skills/harness-update/SKILL.md` |
| init | `skills/init/SKILL.md` |

### Hooks (Python, 14종)

| Hook | Role |
|------|------|
| `claude-gate-guard.py` | Gate 순서 강제 (PreToolUse) |
| `commit-msg-guard.py` | 커밋 메시지 형식 검사 |
| `comprehension-ledger-stale-guard.py` | 이해도 원장 만료 탐지 |
| `docker-command-guard.py` | 잘못된 docker 명령 차단 |
| `error-topics-guard.py` | 오류 주제 파일 동기화 |
| `gate-a-sync-guard.py` | Gate A 승인 대기 일관성 |
| `gate-e-sync-guard.py` | Gate E ✅ 완료 일관성 |
| `master-plan-stale-guard.py` | 마스터 플랜 스테일 감지 |
| `session-dashboard-sync.py` | session-dashboard.html 자동 갱신 |
| `session_dashboard_parsers.py` | 대시보드 파서 (라이브러리) |
| `session_dashboard_renderer.py` | 대시보드 렌더러 (라이브러리) |
| `skill-usage-auto.py` | 스킬 사용 집계 |
| `test-tampering-guard.py` | reward-hacking 탐지 |

### Config

| File | Role |
|------|------|
| `plugin.json` | 루트 플러그인 디스크립터 |
| `.claude-plugin/plugin.json` | 플러그인 메타데이터 |
| `.claude-plugin/marketplace.json` | 마켓플레이스 등록 |
