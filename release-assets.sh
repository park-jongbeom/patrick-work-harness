#!/usr/bin/env bash
# 릴리스 자산 — install.sh 가 내려받아 검증하는 압축 파일과 그 SHA256 (2026-11-10).
#
# 왜: install.sh 는 릴리스에 `.sha256` 이 있을 때만 검증했는데, 어느 릴리스에도 올린 적이 없어 검증이 한 번도 돌지
#     않았다. GitHub 이 만드는 소스 압축본(archive/refs/tags)의 바이트는 GitHub 이 보장하지 않는다(2023-01 에 한 번
#     바뀌어 체크섬 검증이 일제히 깨졌다). 그래서 압축 파일을 여기서 만들어 함께 올리고, install.sh 는 그 파일을 받는다.
# 이름: 체크섬은 `<압축 파일>.sha256` 이다. 옛 install.sh 는 `patrick-work-harness-vX.Y.Z.sha256` 을 찾아 GitHub 소스 압축본과
#     비교하므로, 그 이름으로 올리면 옛 스크립트가 「불일치 — 변조 가능성」으로 설치를 멈춘다.
# 재현: `git archive` 는 같은 커밋이면 같은 tar 를 내고, `gzip -n` 은 이름·시각을 넣지 않는다 — 같은 git·gzip 으로 다시
#     만들면 같은 해시가 나와 올린 파일을 대조할 수 있다.
#
# 사용:
#   ./release-assets.sh vX.Y.Z            만들고 해시를 확인한 뒤 폴더 경로를 출력한다(올리지 않는다)
#   ./release-assets.sh vX.Y.Z --upload   위에 더해 `gh release upload` 로 같은 이름의 자산을 덮어 올린다
set -euo pipefail

TAG="${1:-}"
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "사용: ./release-assets.sh vX.Y.Z [--upload]" >&2
  exit 2
fi
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null || { echo "태그가 없다: ${TAG}" >&2; exit 1; }

NAME="patrick-work-harness-${TAG}"
OUT="$(mktemp -d)"
git archive --format=tar --prefix="patrick-work-harness-${TAG#v}/" "$TAG" | gzip -n -9 > "${OUT}/${NAME}.tar.gz"
(cd "$OUT" && sha256sum "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256" && sha256sum -c --quiet "${NAME}.tar.gz.sha256")
echo "만듦: ${OUT}/${NAME}.tar.gz · $(cut -d' ' -f1 "${OUT}/${NAME}.tar.gz.sha256")"

if [[ "${2:-}" == "--upload" ]]; then
  gh release upload "$TAG" "${OUT}/${NAME}.tar.gz" "${OUT}/${NAME}.tar.gz.sha256" --clobber
  echo "올림: ${TAG} 릴리스에 ${NAME}.tar.gz · ${NAME}.tar.gz.sha256"
fi
echo "$OUT"
