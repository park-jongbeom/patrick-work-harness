# GitHub 첫 릴리스 가이드 — v1.0.0

> 이 가이드는 사용자가 직접 실행하는 수동 단계입니다. AI(Claude Code)는 로컬 파일 준비까지만 수행했습니다.

## 사전 준비

- GitHub 계정: `park-jongbeom`
- 로컬 저장소 위치: `/media/ubuntu/data120g/patrick-work-harness/`

---

## Step 1 — GitHub에서 저장소 생성 (웹 UI)

1. https://github.com/new 접속
2. Repository name: `patrick-work-harness`
3. Visibility: **Public**
4. Initialize: **체크 없음** (로컬에 이미 파일 있음)
5. "Create repository" 클릭

---

## Step 2 — 로컬 git 초기화 및 첫 커밋

```bash
cd /media/ubuntu/data120g/patrick-work-harness

git init
git add .
git commit -m "chore: v1.0.0 첫 릴리스"
git remote add origin https://github.com/park-jongbeom/patrick-work-harness.git
git branch -M main
git push -u origin main
```

---

## Step 3 — v1.0.0 태그 생성 및 푸시

```bash
git tag v1.0.0
git push origin v1.0.0
```

> `v1.0.0` 태그가 푸시되면 `.github/workflows/deploy-plugin.yml`(ai-consulting-plans 저장소에 있음) 워크플로우가 트리거됩니다.
> `patrick-work-harness` 저장소 자체에는 GitHub Actions 워크플로우가 없으므로, Release는 수동으로 생성합니다(아래 Step 4).

---

## Step 4 — GitHub Release 수동 생성

1. https://github.com/park-jongbeom/patrick-work-harness/releases/new 접속
2. "Choose a tag" → `v1.0.0` 선택
3. Release title: `v1.0.0 — 첫 릴리스`
4. Description: `CHANGELOG.md` 내용 붙여넣기
5. "Publish release" 클릭

---

## 완료 확인

- [ ] `https://github.com/park-jongbeom/patrick-work-harness` 접속 → 파일 목록 확인
- [ ] Releases 탭 → `v1.0.0` 존재 확인
- [ ] `plugin.json` 내 URL이 `park-jongbeom`으로 표시되는지 확인

---

## 이후 버전 업 절차

버전 변경 시 `RELEASE_POLICY.md` 참조.

```bash
# plugin.json version 필드 수정 후
git add plugin.json CHANGELOG.md
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push origin main && git push origin vX.Y.Z
```
