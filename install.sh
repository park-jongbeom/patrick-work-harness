#!/usr/bin/env bash
# install.sh — patrick-work-harness installer
#
# Usage:
#   # 최신 릴리즈 설치 (현재 디렉터리 기준)
#   curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash
#
#   # 특정 버전 설치
#   curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --version v1.0.0
#
#   # 특정 프로젝트 경로에 설치
#   curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --target /path/to/your/project
#
#   # 로컬 스크립트 직접 실행
#   ./install.sh --target /media/ubuntu/data120g/college-crawler

set -euo pipefail

REPO="park-jongbeom/patrick-work-harness"
BASE_URL="https://github.com/${REPO}"

# ── 기본값 ──────────────────────────────────────────────
VERSION="latest"
TARGET_DIR="$(pwd)"
INSTALL_HOOKS=true
INSTALL_SKILLS=true

# ── 인수 파싱 ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)  VERSION="$2";    shift 2 ;;
    --target)   TARGET_DIR="$2"; shift 2 ;;
    --no-hooks) INSTALL_HOOKS=false; shift ;;
    --no-skills) INSTALL_SKILLS=false; shift ;;
    -h|--help)
      sed -n '/^# Usage/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0 ;;
    *) echo "[ERROR] 알 수 없는 옵션: $1"; exit 1 ;;
  esac
done

# ── 버전 결정 ────────────────────────────────────────────
if [[ "$VERSION" == "latest" ]]; then
  echo "[1/5] 최신 릴리즈 버전 조회 중..."
  VERSION=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\(.*\)".*/\1/')
  if [[ -z "$VERSION" ]]; then
    echo "[ERROR] GitHub API에서 최신 버전을 가져오지 못했습니다."
    exit 1
  fi
fi
echo "[1/5] 설치 버전: ${VERSION}"

# ── 대상 경로 확인 ───────────────────────────────────────
TARGET_DIR="$(realpath "$TARGET_DIR")"
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[ERROR] 대상 디렉터리가 없습니다: ${TARGET_DIR}"
  exit 1
fi
echo "[2/5] 설치 대상: ${TARGET_DIR}"

# ── tarball 다운로드 ─────────────────────────────────────
TARBALL_URL="${BASE_URL}/archive/refs/tags/${VERSION}.tar.gz"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[3/5] 다운로드 중: ${TARBALL_URL}"
curl -fsSL "$TARBALL_URL" | tar -xzf - -C "$TMP_DIR"

# tarball 압축 해제 후 생성되는 폴더명 (예: patrick-work-harness-1.0.0)
EXTRACTED=$(ls "$TMP_DIR")
SRC="${TMP_DIR}/${EXTRACTED}"

# ── 스킬 설치 ────────────────────────────────────────────
CLAUDE_DIR="${TARGET_DIR}/.claude"
mkdir -p "$CLAUDE_DIR"

if [[ "$INSTALL_SKILLS" == true && -d "${SRC}/skills" ]]; then
  echo "[4/5] 스킬 설치 중..."
  mkdir -p "${CLAUDE_DIR}/skills"
  rsync -a --delete \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    "${SRC}/skills/" "${CLAUDE_DIR}/skills/"
  SKILL_COUNT=$(ls "${CLAUDE_DIR}/skills/" | wc -l | tr -d ' ')
  echo "      스킬 ${SKILL_COUNT}종 설치 완료 → ${CLAUDE_DIR}/skills/"
else
  echo "[4/5] 스킬 설치 건너뜀"
fi

# ── 훅 설치 (전역 settings.json) ─────────────────────────
GLOBAL_SETTINGS="${HOME}/.claude/settings.json"

if [[ "$INSTALL_HOOKS" == true && -d "${SRC}/hooks" ]]; then
  echo "[5/5] 훅 설치 중..."

  # 훅 파일을 ~/.claude/hooks/ 에 복사
  GLOBAL_HOOKS_DIR="${HOME}/.claude/hooks/patrick-work-harness"
  mkdir -p "$GLOBAL_HOOKS_DIR"
  rsync -a --delete \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="test_*.py" \
    "${SRC}/hooks/" "$GLOBAL_HOOKS_DIR/"
  echo "      훅 파일 → ${GLOBAL_HOOKS_DIR}/"

  # settings.json 에 훅 등록
  python3 - <<PYEOF
import json, os, sys

settings_path = os.path.expanduser("${GLOBAL_SETTINGS}")
hooks_dir = "${GLOBAL_HOOKS_DIR}"

# 기존 settings.json 로드 (없으면 빈 dict)
if os.path.exists(settings_path):
    with open(settings_path) as f:
        cfg = json.load(f)
else:
    cfg = {}

hooks = cfg.setdefault("hooks", {})

# 등록할 훅 정의
NEW_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "Edit|Write|Bash",
            "hooks": [{"type": "command", "command": f"python3 {hooks_dir}/claude-gate-guard.py"}]
        },
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": f"python3 {hooks_dir}/docker-command-guard.py"}]
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [{"type": "command", "command": f"python3 {hooks_dir}/session-dashboard-sync.py"}]
        },
    ],
    "Stop": [
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"python3 {hooks_dir}/master-plan-stale-guard.py"}]
        },
    ],
}

def cmd_exists(hook_list, cmd):
    for entry in hook_list:
        for h in entry.get("hooks", []):
            if h.get("command") == cmd:
                return True
    return False

changed = False
for event, entries in NEW_HOOKS.items():
    existing = hooks.setdefault(event, [])
    for entry in entries:
        for h in entry["hooks"]:
            if not cmd_exists(existing, h["command"]):
                existing.append(entry)
                changed = True
                break

if changed:
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"      settings.json 훅 등록 완료: {settings_path}")
else:
    print("      훅이 이미 등록되어 있습니다 (중복 건너뜀)")
PYEOF
else
  echo "[5/5] 훅 설치 건너뜀"
fi

# ── 완료 ─────────────────────────────────────────────────
echo ""
echo "✔ patrick-work-harness ${VERSION} 설치 완료"
echo ""
echo "  스킬 경로: ${CLAUDE_DIR}/skills/"
echo "  훅  경로:  ${HOME}/.claude/hooks/patrick-work-harness/"
echo ""
echo "  사용 가능한 슬래시 커맨드:"
echo "    /gate-a  /gate-b  /gate-c  /gate-d  /gate-e"
echo "    /audit   /doc-cleanup"
echo ""
echo "  Claude Code를 재시작하면 스킬이 활성화됩니다."
