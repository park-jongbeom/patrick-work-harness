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
#   # 변경 없이 미리보기만 (파일 미설치)
#   curl -fsSL https://raw.githubusercontent.com/park-jongbeom/patrick-work-harness/main/install.sh | bash -s -- --dry-run
#
#   # 로컬 스크립트 직접 실행
#   ./install.sh --target /path/to/your-project

set -euo pipefail

REPO="park-jongbeom/patrick-work-harness"
BASE_URL="https://github.com/${REPO}"

# ── 기본값 ──────────────────────────────────────────────
VERSION="latest"
TARGET_DIR="$(pwd)"
INSTALL_HOOKS=true
INSTALL_SKILLS=true
DRY_RUN=false

# ── 인수 파싱 ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)   VERSION="$2";    shift 2 ;;
    --target)    TARGET_DIR="$2"; shift 2 ;;
    --no-hooks)  INSTALL_HOOKS=false; shift ;;
    --no-skills) INSTALL_SKILLS=false; shift ;;
    --dry-run)   DRY_RUN=true; shift ;;
    -h|--help)
      sed -n '/^# Usage/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0 ;;
    *) echo "[ERROR] 알 수 없는 옵션: $1"; exit 1 ;;
  esac
done

if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY-RUN] 설치 미리보기 모드 — 파일을 변경하지 않습니다."
fi

# ── 버전 결정 ────────────────────────────────────────────
if [[ "$VERSION" == "latest" ]]; then
  echo "[1/5] 최신 릴리즈 버전 조회 중..."
  # 🔴 `set -euo pipefail` 아래에서 `curl -f` 를 **대입문에 직접 쓰면 안 된다**
  #    (2026-09-25 실측). 403 이면 curl 이 rc=22 로 끝나고, 대입 실패가 곧
  #    스크립트 종료라 **아래 [ERROR] 안내가 한 번도 출력되지 않았다**.
  #    사용자 화면에는 `curl: (22) ... 403` 한 줄만 남아 무엇을 해야 할지
  #    알 수 없었다 — 안내를 적어두고도 도달하지 못하던 자리다.
  #
  #    그래서 ① rc 를 직접 받고 ② HTTP 코드를 따로 받아 **원인을 구분**한다.
  HTTP_CODE=$(curl -sS -o "${TMPDIR:-/tmp}/harness-latest.json" -w '%{http_code}' \
    "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null) || HTTP_CODE="000"

  if [[ "$HTTP_CODE" == "200" ]]; then
    VERSION=$(grep '"tag_name"' "${TMPDIR:-/tmp}/harness-latest.json" \
      | head -1 | sed 's/.*"tag_name": *"\(.*\)".*/\1/')
  else
    VERSION=""
  fi
  rm -f "${TMPDIR:-/tmp}/harness-latest.json"

  if [[ -z "$VERSION" ]]; then
    echo ""
    case "$HTTP_CODE" in
      403|429)
        echo "[ERROR] GitHub API 요청 한도를 초과했습니다 (HTTP ${HTTP_CODE})."
        echo ""
        echo "  버전 조회는 비인증 호출이라 IP 당 시간당 60회로 제한됩니다."
        echo "  공용 IP·CI·잦은 재설치 환경에서 걸릴 수 있으며, 보통 1시간 안에 풀립니다."
        echo ""
        echo "  ⏩ 지금 바로 설치하려면 버전을 직접 지정하세요 (조회를 건너뜁니다):"
        echo ""
        echo "       install.sh --version <태그>"
        echo ""
        echo "     최신 태그는 아래에서 확인할 수 있습니다:"
        echo "       https://github.com/${REPO}/releases/latest"
        ;;
      000)
        echo "[ERROR] GitHub API 에 연결하지 못했습니다 (네트워크·DNS·프록시)."
        echo ""
        echo "  연결을 확인한 뒤 다시 실행하거나, 버전을 직접 지정하세요:"
        echo "       install.sh --version <태그>"
        ;;
      *)
        echo "[ERROR] 최신 버전을 가져오지 못했습니다 (HTTP ${HTTP_CODE})."
        echo ""
        echo "  버전을 직접 지정해 설치할 수 있습니다:"
        echo "       install.sh --version <태그>"
        ;;
    esac
    echo ""
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

# ── tarball 다운로드 + SHA256 검증 ───────────────────────
TARBALL_URL="${BASE_URL}/archive/refs/tags/${VERSION}.tar.gz"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[3/5] 다운로드 중: ${TARBALL_URL}"
TARBALL="${TMP_DIR}/harness.tar.gz"
curl -fsSL "$TARBALL_URL" -o "$TARBALL"

# SHA256 체크섬 검증 (릴리스에 .sha256 파일이 있을 때만 수행)
SHA256_URL="${BASE_URL}/releases/download/${VERSION}/patrick-work-harness-${VERSION}.sha256"
if curl -fsSL --head "$SHA256_URL" 2>/dev/null | grep -q "^HTTP.*200"; then
  EXPECTED=$(curl -fsSL "$SHA256_URL" | awk '{print $1}')
  ACTUAL=$(sha256sum "$TARBALL" | awk '{print $1}')
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    echo "[ERROR] SHA256 체크섬 불일치 — 다운로드 손상 또는 변조 가능성"
    echo "  예상: ${EXPECTED}"
    echo "  실제: ${ACTUAL}"
    exit 1
  fi
  echo "      SHA256 검증 완료 ✔"
else
  echo "      체크섬 파일 없음 — 검증 건너뜀 (이 릴리스에 .sha256 미발행)"
fi

tar -xzf "$TARBALL" -C "$TMP_DIR"

# tarball 압축 해제 후 생성되는 폴더명 (예: patrick-work-harness-1.0.0)
EXTRACTED=$(ls "$TMP_DIR" | grep -v 'harness\.tar\.gz')
SRC="${TMP_DIR}/${EXTRACTED}"

# ── 스킬 설치 ────────────────────────────────────────────
CLAUDE_DIR="${TARGET_DIR}/.claude"

if [[ "$INSTALL_SKILLS" == true && -d "${SRC}/skills" ]]; then
  if [[ "$DRY_RUN" == true ]]; then
    SKILL_COUNT=$(ls "${SRC}/skills/" | wc -l | tr -d ' ')
    echo "[4/5] [DRY-RUN] 스킬 ${SKILL_COUNT}종 설치 예정 → ${CLAUDE_DIR}/skills/ (미적용)"
  else
    echo "[4/5] 스킬 설치 중..."
    mkdir -p "${CLAUDE_DIR}/skills"
    # 🔴 --delete 를 쓰지 않는다 (2026-09-23, HARNESS-CROSSCHECK-FIX-1-a-6).
    #    이 경로는 대상 프로젝트의 `.claude/skills/` 이고 사용자가 직접 만든 스킬이
    #    함께 산다. --delete 는 그것들을 통째로 지웠다. 하네스 스킬만 덮어쓰고
    #    나머지는 건드리지 않는다. 구버전 하네스 스킬이 남는 문제는 아래에서 알린다.
    # 🔴 LC_ALL=C 로 정렬 기준을 고정한다 (2026-09-24, HARNESS-INSTALL-COMM-1).
    #    en_US.UTF-8 등에서 `sort` 는 대소문자를 무시해 "SKILL_DETAIL.md" 를 소문자
    #    항목 뒤에 놓는데, `comm` 은 바이트 순서('S' < 'a')를 기대한다. 두 도구의
    #    기준이 달라 "input is not in sorted order" 로 죽었다.
    #    ＊`sort` 에만 붙이면 안 된다 — 비교 기준을 실제로 쓰는 쪽은 `comm` 이라
    #      `comm` 자신에게도 같은 로케일을 줘야 한다(실측 2026-09-24).
    BEFORE_LIST=$(ls -1 "${CLAUDE_DIR}/skills/" 2>/dev/null | LC_ALL=C sort)
    rsync -a \
      --exclude="__pycache__/" \
      --exclude="*.pyc" \
      "${SRC}/skills/" "${CLAUDE_DIR}/skills/"
    SKILL_COUNT=$(ls -1 "${SRC}/skills/" | wc -l | tr -d ' ')
    echo "      하네스 스킬 ${SKILL_COUNT}종 설치 완료 → ${CLAUDE_DIR}/skills/"

    # 이 배포본에 없는데 대상에 남아 있는 스킬을 보고한다(지우지는 않는다).
    #
    # 🔴 이 블록은 **보고 전용**이므로 실패해도 설치를 멈추지 않는다.
    #    실제로 2026-09-24 에 위 정렬 문제로 `comm` 이 죽으면서 **훅 설치(5/5)까지
    #    통째로 건너뛰었다** — 부가 기능이 본체를 막았고, 스킬만 깔린 반쪽 상태가
    #    「설치 완료」로 보였다.
    SHIPPED_LIST=$(ls -1 "${SRC}/skills/" | LC_ALL=C sort)
    STALE=$(LC_ALL=C comm -23 <(echo "$BEFORE_LIST") <(echo "$SHIPPED_LIST") 2>/dev/null | tr '\n' ' ') || STALE=""
    if [[ -n "${STALE// /}" ]]; then
      echo "      ℹ️  이 배포본에 없는 스킬이 남아 있다: ${STALE}"
      echo "         사용자 스킬이거나 구버전 하네스 스킬이다. 판단해서 직접 정리한다."
    fi
  fi
else
  echo "[4/5] 스킬 설치 건너뜀"
fi

# ── 훅 설치 (전역 settings.json) ─────────────────────────
GLOBAL_SETTINGS="${HOME}/.claude/settings.json"

if [[ "$INSTALL_HOOKS" == true && -d "${SRC}/hooks" ]]; then
  GLOBAL_HOOKS_DIR="${HOME}/.claude/hooks/patrick-work-harness"
  if [[ "$DRY_RUN" == true ]]; then
    HOOK_COUNT=$(ls "${SRC}/hooks/" | grep '\.py$' | grep -v '^test_' | wc -l | tr -d ' ')
    echo "[5/5] [DRY-RUN] 훅 ${HOOK_COUNT}종 설치 예정 → ${GLOBAL_HOOKS_DIR}/ (미적용)"
    echo "      [DRY-RUN] settings.json 훅 등록 예정: ${GLOBAL_SETTINGS} (미적용)"
  else
    echo "[5/5] 훅 설치 중..."

    # 훅 파일을 ~/.claude/hooks/patrick-work-harness/ 에 복사.
    # 이 폴더는 하네스 전용이라 --delete 로 구버전 훅을 정리하는 것이 맞다.
    # 다만 사용자가 같은 이름의 폴더를 다른 용도로 쓰고 있을 수 있으므로,
    # 하네스가 만든 폴더인지 표식으로 확인한 뒤에만 지운다 (2026-09-23).
    OWNER_MARK="${GLOBAL_HOOKS_DIR}/.harness-owned"
    if [[ -d "$GLOBAL_HOOKS_DIR" && ! -f "$OWNER_MARK" ]]; then
      if [[ -n "$(ls -A "$GLOBAL_HOOKS_DIR" 2>/dev/null)" ]]; then
        echo "      ⚠️  ${GLOBAL_HOOKS_DIR} 가 하네스가 만든 폴더가 아니다(표식 없음)."
        echo "         내용을 지우지 않고 덮어쓰기만 한다. 구버전 훅이 남을 수 있다."
        DELETE_OPT=""
      else
        DELETE_OPT="--delete"
      fi
    else
      DELETE_OPT="--delete"
    fi
    mkdir -p "$GLOBAL_HOOKS_DIR"
    rsync -a ${DELETE_OPT} \
      --exclude="__pycache__/" \
      --exclude="*.pyc" \
      --exclude="test_*.py" \
      --exclude=".harness-owned" \
      "${SRC}/hooks/" "$GLOBAL_HOOKS_DIR/"
    # 🔴 표식에 설치 버전을 기록한다 (HARNESS-INSTALL-PROVENANCE-2, 2026-09-24).
    #    이전에는 문구 한 줄뿐이라 **설치된 것이 어느 판인지 알 방법이 없었다**.
    #    `/harness-update` 는 harness-answers.yml 의 `_engine_version` 만 보고 판정하는데,
    #    그 필드가 틀리면 교차 확인할 근거가 없다. 기계가 읽는 `version:` 줄을 둔다.
    {
      printf 'patrick-work-harness install marker. Safe to delete this folder.\n'
      printf 'version: %s\n' "${VERSION#v}"
      printf 'installed_at: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$OWNER_MARK"
    echo "      훅 파일 → ${GLOBAL_HOOKS_DIR}/"

    # 훅 배선에 쓸 Python 인터프리터 결정 (HARNESS-SYNC-RECONCILE-2-a, 2026-08-07)
    #   Windows: `py` (Python Launcher) — Claude Code 훅은 로그인 셸을 거치지 않아
    #            Git Bash 의 `python3` shim 을 신뢰할 수 없다.
    #   그 외:   `python3` (POSIX 표준)
    # 배선 문자열에만 적용 — 아래 헤레독 자체는 설치 셸(Git Bash/POSIX)에서 실행되므로 python3 유지.
    case "${OSTYPE:-}" in
      msys*|cygwin*|win32*) HOOK_PY="py" ;;
      *)                    HOOK_PY="python3" ;;
    esac
    echo "  훅 인터프리터: ${HOOK_PY} (OSTYPE=${OSTYPE:-unknown})"

    # settings.json 에 훅 등록
    python3 - <<PYEOF
import json, os, sys

settings_path = os.path.expanduser("${GLOBAL_SETTINGS}")
hooks_dir = "${GLOBAL_HOOKS_DIR}"
hook_py = "${HOOK_PY}"

# 기존 settings.json 로드 (없으면 빈 dict)
if os.path.exists(settings_path):
    with open(settings_path) as f:
        cfg = json.load(f)
else:
    cfg = {}

hooks = cfg.setdefault("hooks", {})

# 등록할 훅 정의
NEW_HOOKS = {
    # claude-gate-guard 는 2026-09-23 에 기본 구성에서 뺐다(HARNESS-CROSSCHECK-FIX-1-a-4).
    # 자기 자신(.claude/·모든 .md)을 면제하고 PowerShell 호출을 판정 없이 통과시켜
    # 「걸리는 척」만 했다. 07-27 에 오탐 22·정탐 0 으로 가드를 뺀 선례와 같은 기준이다.
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/docker-command-guard.py"}]
        },
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/commit-msg-guard.py"}]
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/session-dashboard-sync.py"}]
        },
    ],
    "Stop": [
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/master-plan-stale-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/gate-a-sync-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/gate-e-sync-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/error-topics-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/test-tampering-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/comprehension-ledger-stale-guard.py"}]
        },
        {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"{hook_py} {hooks_dir}/skill-usage-auto.py"}]
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
    # 🔴 사용자의 전역 설정을 고치기 전에 백업한다 (2026-09-23).
    #    이 파일에는 하네스와 무관한 사용자 설정이 함께 산다. 이전에는 백업 없이
    #    덮어써서, 병합이 잘못되면 되돌릴 방법이 없었다.
    if os.path.exists(settings_path):
        import shutil, time
        backup = f"{settings_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(settings_path, backup)
        print(f"      기존 설정 백업: {backup}")
    with open(settings_path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"      settings.json 훅 등록 완료: {settings_path}")
else:
    print("      훅이 이미 등록되어 있습니다 (중복 건너뜀)")
PYEOF
  fi
else
  echo "[5/5] 훅 설치 건너뜀"
fi

# ── provenance 갱신 (HARNESS-INSTALL-PROVENANCE-1, 2026-09-24) ──
#
# 🔴 install.sh 는 지금까지 harness-answers.yml 을 건드리지 않았고, 그래서
#    설치본은 새 버전인데 `_engine_version` 은 옛 값으로 남았다. `/harness-update`
#    는 그 필드만 보고 판정하므로 **이미 설치된 것을 다시 설치하라**고 안내한다
#    (2026-09-24 실측: 필드 1.3.4 / 실제 훅 12개·claude-gate-guard 0 = v1.4.1).
#
#    이 파일은 사용자 응답이 담긴 설정이므로 `_engine_version` 한 줄만 바꾸고
#    나머지는 건드리지 않는다. 수정 전 타임스탬프 백업을 남긴다.
ANSWERS="${CLAUDE_DIR}/harness-answers.yml"
if [[ "$DRY_RUN" == false && -f "$ANSWERS" ]]; then
  BARE_VERSION="${VERSION#v}"
  # 🔴 `|| true` 가 없으면 설치가 여기서 죽는다 (2026-09-25 실측).
  #    `set -euo pipefail` 아래에서 `grep` 은 **매치 실패 시 rc=1** 이고,
  #    `_engine_version` 이 없는 답변 파일(= `init` 스킬이 막 만든 신규
  #    프로젝트)에서 바로 그 일이 일어난다. 스크립트가 rc=1 로 끝나면서
  #    provenance 갱신·디렉터리 생성·완료 메시지가 **전부 실행되지 않고**,
  #    출력이 `[5/5]` 에서 끊긴 채 조용히 종료된다.
  #    필드 부재는 오류가 아니라 **처음 기록하는 경우**다.
  CURRENT_PROV=$(grep -E '^_engine_version:' "$ANSWERS" | head -1 | sed -E 's/.*"(.*)".*/\1/' || true)
  if [[ "$CURRENT_PROV" != "$BARE_VERSION" ]]; then
    cp "$ANSWERS" "${ANSWERS}.bak-$(date +%Y%m%d-%H%M%S)"
    if grep -qE '^_engine_version:' "$ANSWERS"; then
      sed -i.tmp -E "s|^_engine_version:.*|_engine_version: \"${BARE_VERSION}\"|" "$ANSWERS"
      rm -f "${ANSWERS}.tmp"
    else
      # 🔴 `sed` 는 **있는 줄만** 바꾼다. 필드가 없으면 아무 일도 안 하는데
      #    아래 메시지는 「갱신」이라고 말한다 — 2026-09-25 실측으로
      #    「미기재 → 1.5.0」 을 출력하고도 파일은 그대로였다.
      #    없으면 **추가**한다. 그래야 `/harness-update` 가 판정할 수 있다.
      printf '_engine_version: "%s"\n' "$BARE_VERSION" >> "$ANSWERS"
    fi
    echo "      provenance 갱신: _engine_version ${CURRENT_PROV:-미기재} → ${BARE_VERSION}"
  fi
fi

# ── 훅이 쓰는 디렉터리 보장 (HARNESS-INSTALL-DIRS-1, 2026-09-25) ──
#
# 🔴 `skill-usage-auto` 훅은 `<process_evolution_path>/skill_usage_YYYY-MM.md` 를
#    쓰는데, 설치는 그 디렉터리를 만들지 않았다. 새 프로젝트에는 그 경로가
#    없으므로 **첫 집계부터 매번 실패**하고, 훅은 항상 exit 0 이라 아무도 몰랐다.
#    실측(2026-09-25): Gate 를 가장 많이 쓴 세 프로젝트에 자기 기록이 0건이었다
#    (`homepage` 는 gate-a 만 33회를 쓰고도 산출물이 없었다).
#
#    집계기 쪽에도 `mkdir(parents=True)` 를 넣었지만(런타임 방어), 이식 시점에
#    자리를 만들어 두는 것이 정본이다 — 사용자가 손으로 만들 일이 아니다.
#
#    ⚠ 기본값을 박지 않는다. `process_evolution_path` 는 프로젝트마다 다르다
#    (실측: `docs/process_evolution` 로 지정한 프로젝트가 있다). 답변 파일이
#    있으면 그 값을, 없으면 훅과 같은 기본값(`plans/process_evolution`)을 쓴다.
if [[ "$DRY_RUN" == false ]]; then
  PE_PATH="plans/process_evolution"
  if [[ -f "$ANSWERS" ]]; then
    PE_FROM_ANSWERS=$(grep -E '^process_evolution_path:' "$ANSWERS" \
      | head -1 | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*#.*$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/')
    [[ -n "$PE_FROM_ANSWERS" ]] && PE_PATH="$PE_FROM_ANSWERS"
  fi
  # 상대경로는 대상 프로젝트 기준으로 해석한다 (훅의 해석 규칙과 동일)
  case "$PE_PATH" in
    /*|[A-Za-z]:*) PE_DIR="$PE_PATH" ;;
    *)             PE_DIR="${TARGET_DIR}/${PE_PATH}" ;;
  esac
  if [[ -d "$PE_DIR" ]]; then
    echo "      사용량 기록 경로 확인: ${PE_PATH}"
  elif mkdir -p "$PE_DIR" 2>/dev/null; then
    echo "      사용량 기록 경로 생성: ${PE_PATH}"
  else
    # 만들지 못해도 설치를 멈추지 않는다 — 집계기가 런타임에 다시 시도한다
    echo "      ⚠ 사용량 기록 경로를 만들지 못했습니다: ${PE_DIR}"
  fi
fi

# ── 완료 ─────────────────────────────────────────────────
echo ""
if [[ "$DRY_RUN" == true ]]; then
  echo "✔ --dry-run 완료 (변경 없음) — 실제 설치하려면 --dry-run 없이 재실행하세요."
else
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
fi
