# Release Policy — patrick-work-harness

## Semantic Versioning (MAJOR.MINOR.PATCH)

| 버전 구분 | 기준 | 예시 |
|-----------|------|------|
| **MAJOR** | 하네스 구조 변경 — Gate 순서 재편·스킬 인터페이스 파괴적 변경·훅 API 호환 불가 | `v1.0.0 → v2.0.0` |
| **MINOR** | 스킬 추가 / 훅 신규 / 기존 기능 확장 (하위 호환 유지) | `v1.0.0 → v1.1.0` |
| **PATCH** | 버그 수정 / 문서 보완 / 오탈자 교정 | `v1.0.0 → v1.0.1` |

## v1.0.0 첫 릴리스 기준

- Gate A~E 스킬 8종 완비: `/gate-a`, `/gate-b`, `/gate-c`, `/gate-d`, `/gate-e`, `/doc-cleanup`, `/audit`, `/comprehend-gate`
- 훅 시스템 3종: `master-plan-stale-guard`, `docker-command-guard`, `session-dashboard-sync`
- HARNESS-REVIEW-4 체인 (R-4-1~6) 검증 완료
- PLUGIN-TEST-1 E2E 통과 (C1~C5 PASS)

## 릴리스 절차

```
1. plugin.json version 필드 업데이트
2. CHANGELOG.md 항목 추가 (Added / Fixed / Changed)
3. git commit -m "chore: bump version to vX.Y.Z"
4. git tag vX.Y.Z
5. git push origin main
6. git push origin vX.Y.Z   ← GitHub Actions "Deploy Plugin" 워크플로우 자동 트리거
```

## CHANGELOG 작성 규약

- `Added` — 새로 추가된 스킬·훅·기능
- `Fixed` — 버그 수정
- `Changed` — 기존 동작 변경 (하위 호환 유지)
- `Removed` — 제거된 기능 (MAJOR 버전에서만)
- `Breaking` — 파괴적 변경 사항 (MAJOR 버전에서만, 최상단 강조)

## 핫픽스 절차 (긴급 PATCH)

```
git checkout main
# 수정 후
git commit -m "fix: <이슈 한 줄 설명>"
git tag v1.0.1
git push origin main && git push origin v1.0.1
```
