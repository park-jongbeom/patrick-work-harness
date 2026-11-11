# PROJECT_MAP — patrick-work-harness

## Directory Structure (top 2 levels)

```
patrick-work-harness/
├── .claude-plugin/
│   ├── marketplace.json      # Community marketplace registration
│   └── plugin.json           # Plugin metadata (version, author, keywords)
├── hooks/                    # Stop / PreToolUse event handlers (Python)
├── skills/                   # Gate A–E + utility skill definitions
│   ├── audit/
│   ├── commit-up/
│   ├── doc-cleanup/
│   ├── gate-a/
│   ├── gate-b/
│   ├── gate-c/
│   ├── gate-d/
│   ├── gate-e/
│   ├── harness-feedback/
│   ├── harness-update/
│   ├── init/
│   └── SKILL_DETAIL.md       # Shared rubric / advisor escalation detail
├── CHANGELOG.md
├── README.md
├── RELEASE_POLICY.md
├── install.sh                # CLI installer (--version / --target / --dry-run)
├── plugin.json               # Root plugin descriptor
├── release-assets.sh         # Release tarball + .sha256 (install.sh verifies them)
└── sync-from-source.sh       # Source → deploy sync helper
```

## Technology Stack

- **Runtime**: Python 3.x (hooks), Markdown (skills)
- **Test**: pytest (hooks unit tests)
- **CI/CD**: 없음 — 시험은 릴리스 전에 로컬과 깨끗한 컨테이너에서 돌린다(`RELEASE_POLICY.md`). 배포 워크플로는 2026-07-20 에 뺐다
- **Plugin system**: Claude Code plugin spec (`.claude-plugin/`)

## Module List

### Skills (11종)

| Skill | File |
|-------|------|
| audit | `skills/audit/SKILL.md` |
| commit-up | `skills/commit-up/SKILL.md` |
| doc-cleanup | `skills/doc-cleanup/SKILL.md` |
| gate-a | `skills/gate-a/SKILL.md` |
| gate-b | `skills/gate-b/SKILL.md` |
| gate-c | `skills/gate-c/SKILL.md` |
| gate-d | `skills/gate-d/SKILL.md` |
| gate-e | `skills/gate-e/SKILL.md` |
| harness-feedback | `skills/harness-feedback/SKILL.md` |
| harness-update | `skills/harness-update/SKILL.md` |
| init | `skills/init/SKILL.md` |

### Hooks (`hooks/hooks.json` 에 배선)

| Hook | Role |
|------|------|
| `commit-msg-guard.py` | 커밋 메시지 형식 검사 |
| `comprehension-pending-guard.py` | 이해도 질문이 대기 중이면 Gate C·D·E 진입 차단 |
| `docker-command-guard.py` | 잘못된 docker 명령 차단 |
| `error-topics-guard.py` | 오류 주제 파일 동기화 |
| `gate-a-sync-guard.py` | Gate A 승인 대기 일관성 |
| `gate-e-sync-guard.py` | Gate E ✅ 완료 일관성, Gate D 기록 확인 |
| `harness-feedback-sync.py` | 사용 기록 요약을 조건이 차면 SSH 로 엔진 서버에 전송(설정·받기 명령 포함) |
| `lane-scope-guard.py` | 자율 레인 범위 검사 |
| `master-plan-stale-guard.py` | 마스터 플랜 스테일 감지 |
| `session-dashboard-sync.py` | session-dashboard.html 자동 갱신 |
| `test-tampering-guard.py` | reward-hacking 탐지 |
| `test-write-guard.py` | 시험 파일 쓰기 전 확인 |

### Tools and modules (배선 없음)

| File | Role |
|------|------|
| `gate_b_trigger.py` | Gate B 발동 판정 |
| `fresh_review.py` | Gate A 새 문맥 검토 준비(시험 운영) |
| `gate_transcript.py` | 대화 기록에서 Gate 호출·쓰기 판정 |
| `harness_report.py` · `skill_usage_aggregator.py` | 사용 보고서(수동 실행) |
| `lane_card.py` · `session_ledger.py` · `report_facts.py` | 자율 레인 카드·세션 원장·변경 사실 |
| `session_dashboard_parsers.py` · `session_dashboard_renderer.py` | 대시보드 파서·렌더러 |
| `run_all_tests.py` | 전체 시험 실행 |

### Config

| File | Role |
|------|------|
| `plugin.json` | 루트 플러그인 디스크립터 |
| `.claude-plugin/plugin.json` | 플러그인 메타데이터 |
| `.claude-plugin/marketplace.json` | 마켓플레이스 등록 |
