#!/usr/bin/env bash
# sync-from-source.sh
# Syncs harness skills and hooks from the private source repo to this public repo.
#
# Usage:
#   ./sync-from-source.sh [SOURCE_REPO_PATH]
#
# If SOURCE_REPO_PATH is not provided, SOURCE_REPO env var is used.
# Example:
#   SOURCE_REPO=/path/to/your/private-repo ./sync-from-source.sh
#   ./sync-from-source.sh /path/to/your/private-repo

set -euo pipefail

DEST="$(cd "$(dirname "$0")" && pwd)"

SOURCE="${1:-${SOURCE_REPO:-}}"
if [[ -z "$SOURCE" ]]; then
  echo "[ERROR] Source repo path required."
  echo "  Usage: ./sync-from-source.sh /path/to/private-repo"
  echo "  Or:    SOURCE_REPO=/path/to/private-repo ./sync-from-source.sh"
  exit 1
fi

if [[ ! -d "$SOURCE" ]]; then
  echo "[ERROR] Source directory not found: $SOURCE"
  exit 1
fi

SKILLS_SRC="$SOURCE/.claude/skills"
HOOKS_SRC="${HOOKS_SOURCE_DIR:-$SOURCE/../plans/hooks}"

echo "=== patrick-work-harness sync ==="
echo "Source repo : $SOURCE"
echo "Hooks source: $HOOKS_SRC"
echo "Destination : $DEST"
echo ""

# 1. Sync skills
if [[ -d "$SKILLS_SRC" ]]; then
  echo "[1/3] Syncing skills..."
  rsync -av --delete \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    "$SKILLS_SRC/" "$DEST/skills/"
  # Sanitize: replace absolute paths and internal references in synced skill files
  find "$DEST/skills" -name "*.md" | xargs sed -i \
    -e 's|/media/ubuntu/data120g/ai-consulting-plans|\${CLAUDE_PROJECT_DIR}|g' \
    -e 's|/media/ubuntu/data120g/plans|\${HARNESS_PLANS_DIR}|g' \
    -e 's|/media/ubuntu/data120g/ga-api-platform|\${GA_API_PLATFORM_DIR}|g' \
    -e 's|/media/ubuntu/data120g/react-web-ga|\${REACT_WEB_DIR}|g' \
    -e 's|go-almond-harness|patrick-work-harness|g'
  echo "      Done."
else
  echo "[WARN] Skills source not found: $SKILLS_SRC — skipped."
fi

# 2. Sync hooks
if [[ -d "$HOOKS_SRC" ]]; then
  echo "[2/3] Syncing hooks..."
  rsync -av --delete \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="fixtures/" \
    --exclude="progress-report-stale-guard.py" \
    --exclude="test_progress_report_stale_guard.py" \
    "$HOOKS_SRC/" "$DEST/hooks/"
  # Sanitize: replace absolute paths in synced hook files
  find "$DEST/hooks" -name "*.py" | xargs sed -i \
    -e 's|"/media/ubuntu/data120g/ai-consulting-plans"|os.environ.get("CLAUDE_PROJECT_DIR", ".")|g' \
    -e 's|"/media/ubuntu/data120g"|os.environ.get("HARNESS_ROOT_DIR", ".")|g' 2>/dev/null || true
  echo "      Done."
else
  echo "[WARN] Hooks source not found: $HOOKS_SRC — skipped."
fi

# 3. Sync CHANGELOG
if [[ -f "$SOURCE/CHANGELOG.md" ]]; then
  echo "[3/3] Syncing CHANGELOG.md..."
  cp "$SOURCE/CHANGELOG.md" "$DEST/CHANGELOG.md"
  echo "      Done."
else
  echo "[WARN] CHANGELOG.md not found in source — skipped."
fi

echo ""
echo "=== Sync complete ==="
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Update plugin.json / .claude-plugin/marketplace.json if needed"
echo "  3. Tag a release:  git tag v1.x.x && git push --tags"
