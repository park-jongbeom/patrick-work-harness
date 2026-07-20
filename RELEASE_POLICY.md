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

> **전부 로컬 절차** (2026-07-20, v1.2.1 직후 확정): GitHub Actions "Deploy Plugin" 워크플로우는 제거됨 — 하던 일(JSON 검증·버전 정합·Release 생성)이 전부 로컬로 수행 가능한데 러너 큐 지연에 릴리스가 인질로 잡히고, 봇 생성 Release가 수동 정리 노트를 덮어쓰는 충돌만 남기기 때문. Release 객체 자체는 여전히 필수(`install.sh`가 `releases/latest`로 버전 해석) — 아래 7단계에서 gh CLI로 생성한다.

```
1. 버전 3파일 동시 업데이트: plugin.json · .claude-plugin/plugin.json · .claude-plugin/marketplace.json
2. CHANGELOG.md 항목 추가 (Added / Fixed / Changed)
3. 로컬 정합 검증 (구 CI validate 잡 대체) — 아래 한 줄이 3값 동일을 출력해야 함:
   jq -r '.version' plugin.json .claude-plugin/plugin.json && jq -r '.plugins[0].version' .claude-plugin/marketplace.json
4. git commit -m "chore: bump version to vX.Y.Z"
5. git tag vX.Y.Z
6. git push origin main && git push origin vX.Y.Z
7. gh release create vX.Y.Z --title "vX.Y.Z — <한 줄 요약>" --notes-file <해당 버전 CHANGELOG 절만 담은 파일>
   (CHANGELOG 전문 붙여넣기 금지 — 해당 버전 절만. 자산 첨부 불요: install.sh는 태그 소스 tarball을 사용)
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
