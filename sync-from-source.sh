#!/usr/bin/env bash
# sync-from-source.sh
# Stages harness skills and hooks from the private source repo, sanitizes the staged copy, and
# reports how it differs from this public repo. By default it writes nothing into this repo.
#
# Usage:
#   ./sync-from-source.sh [--apply-hooks] [SOURCE_REPO_PATH]
#
#   (default)      report only: sanitized staging + per-area differences + private-path scan
#   --apply-hooks  additionally copy the sanitized hooks into hooks/. Refused when the scan finds a
#                  private path. Never deletes: a hook missing from the source is only reported.
#
# Skills are never copied into this repo. The public skills are a generalized superset of the
# source skills (placeholders + tier-aware wording), so a wholesale copy regresses them — port
# skill changes selectively, using the staged copy as the source text (CHANGELOG 1.3.0).
# CHANGELOG.md is written in this repo and is never copied from the source.
#
# If SOURCE_REPO_PATH is not provided, SOURCE_REPO env var is used.
# Example:
#   SOURCE_REPO=/path/to/your/private-repo ./sync-from-source.sh
#   ./sync-from-source.sh --apply-hooks /path/to/your/private-repo

set -euo pipefail

DEST="$(cd "$(dirname "$0")" && pwd)"

APPLY_HOOKS=0
if [[ "${1:-}" == "--apply-hooks" ]]; then
  APPLY_HOOKS=1
  shift
fi

SOURCE="${1:-${SOURCE_REPO:-}}"
if [[ -z "$SOURCE" ]]; then
  echo "[ERROR] Source repo path required."
  echo "  Usage: ./sync-from-source.sh [--apply-hooks] /path/to/private-repo"
  echo "  Or:    SOURCE_REPO=/path/to/private-repo ./sync-from-source.sh"
  exit 1
fi

if [[ ! -d "$SOURCE" ]]; then
  echo "[ERROR] Source directory not found: $SOURCE"
  exit 1
fi

SKILLS_SRC="$SOURCE/.claude/skills"
HOOKS_SRC="${HOOKS_SOURCE_DIR:-$SOURCE/../plans/hooks}"
STAGE="$(mktemp -d)"

# Private-path patterns, structural only: no user names and no repo-specific literals, so this
# public script does not itself disclose the layout it guards against.
#   1. /media/<name>/<something> · /home/<name>/<something> — the source workspace on a Linux host
#   2. <drive>:\Users\<name>...                             — the same workspace on a Windows host
# Elided forms such as "/media/ubuntu/..." inside a comment are deliberately not matched.
LEAK_PATTERN='/(media|home)/[A-Za-z0-9_.-]+/[A-Za-z0-9_]|[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+'

echo "=== patrick-work-harness sync ==="
echo "Source repo : $SOURCE"
echo "Hooks source: $HOOKS_SRC"
echo "Destination : $DEST"
echo "Staging     : $STAGE"
if [[ $APPLY_HOOKS -eq 1 ]]; then
  echo "Mode        : report + apply hooks"
else
  echo "Mode        : report only (nothing is written into this repo)"
fi
echo ""

# stage_dir <source dir> <staging subdir> [extra tar --exclude args...]
# tar keeps this portable: rsync is absent from a default Git Bash install on Windows.
stage_dir() {
  local src="$1" name="$2"
  shift 2
  mkdir -p "$STAGE/$name"
  tar -C "$src" --exclude="__pycache__" --exclude="*.pyc" --exclude=".pytest_cache" "$@" -cf - . \
    | tar -C "$STAGE/$name" -xf -
}

# 1. Stage skills (sanitized copy only — never written into this repo)
if [[ -d "$SKILLS_SRC" ]]; then
  echo "[1/3] Staging skills..."
  stage_dir "$SKILLS_SRC" skills
  # Sanitize: replace absolute paths in staged skill files
  find "$STAGE/skills" -name "*.md" | xargs sed -i \
    -e 's|/media/ubuntu/data120g/ai-consulting-plans|\${CLAUDE_PROJECT_DIR}|g' \
    -e 's|/media/ubuntu/data120g/plans|\${HARNESS_PLANS_DIR}|g' \
    -e 's|/media/ubuntu/data120g/ga-api-platform|\${GA_API_PLATFORM_DIR}|g' \
    -e 's|/media/ubuntu/data120g/react-web-ga|\${REACT_WEB_DIR}|g' \
    -e 's|go-almond-harness|patrick-work-harness|g'
  # Sanitize: source repo's SSOT doc names → generic placeholders (safe — plain filename swaps,
  # no 2-tier/threshold logic attached). ai-consulting-plans/ prefix already stripped above.
  find "$STAGE/skills" -name "*.md" | xargs sed -i \
    -e 's|00_MASTER_PLAN\.md|${MASTER_PLAN_FILE}|g' \
    -e 's|SESSION_INDEX\.md|${SESSION_INDEX_FILE}|g' \
    -e 's|CURRENT_SESSION\.md|${CURRENT_SESSION_FILE}|g'
  # Sanitize: internal research-doc citations (REPORTS/HARNESS_*.md) have no public equivalent —
  # collapse the file-path citation to a generic footnote, keep any public citation in the same sentence.
  find "$STAGE/skills" -name "*.md" | xargs sed -i \
    -E 's|`?[A-Za-z0-9_./]*REPORTS/HARNESS_[A-Za-z0-9_]+\.md( ?§[0-9]+)?`?|(internal research note, if your project maintains one)|g'
  echo "      Done."

  # Warn on patterns that still need human review — these are structurally tied to the
  # source repo's 2-tier plan structure (index + sub-platform detail plan), repo-tuned line-count
  # thresholds, or illustrative example repo/service names. Blind sed here would silently break
  # the skill's logic for consuming projects, so surface them instead of auto-replacing.
  # Also catches "ai-consulting-plans/${...}" hybrids — a relative-looking source-repo prefix
  # that survived the absolute-path sed pass concatenated with an unresolved shell variable from
  # the filename sed pass (recurrence guard: PATCHREVIEW-1, both sed passes must independently
  # sanitize every occurrence, but a stray prefix that predates the filename pass can slip through).
  REVIEW_HITS=$(grep -rlE '00_MODERNIZATION_MASTER_PLAN\.md|05_PLATFORM_MODERNIZATION|ga-api-platform|react-web-ga|college-crawler|REPORTS/HARNESS_|ai-consulting-plans/\$\{' "$STAGE/skills" 2>/dev/null || true)
  if [[ -n "$REVIEW_HITS" ]]; then
    echo ""
    echo "[WARN] The following staged skill files still reference source-repo-specific"
    echo "       structure (2-tier plan docs, tuned thresholds, or example repo names)."
    echo "       Review and localize manually before porting:"
    while IFS= read -r f; do
      echo "         - ${f#$STAGE/}"
    done <<< "$REVIEW_HITS"
  fi
else
  echo "[WARN] Skills source not found: $SKILLS_SRC — skipped."
fi

# 2. Stage hooks (sanitized copy — applied only with --apply-hooks)
if [[ -d "$HOOKS_SRC" ]]; then
  echo "[2/3] Staging hooks..."
  stage_dir "$HOOKS_SRC" hooks \
    --exclude="fixtures" \
    --exclude="progress-report-stale-guard.py" \
    --exclude="test_progress_report_stale_guard.py"
  # Sanitize: replace absolute paths in staged hook files
  # NOTE: the two rules below only match the exact-quoted forms. Sub-path literals
  # (e.g. ".../plans/process_evolution", ".../plans" as a default arg) slipped past them
  # and shipped private absolute paths in released hooks — hence the catch-all rule that
  # follows (HARNESS-SYNC-RECONCILE-2-a, 2026-08-07).
  # A failing sed is no longer silenced: a substitution that cannot run must surface here,
  # not ship a private path downstream.
  find "$STAGE/hooks" -name "*.py" | xargs sed -i \
    -e 's|"/media/ubuntu/data120g/ai-consulting-plans"|os.environ.get("CLAUDE_PROJECT_DIR", ".")|g' \
    -e 's|"/media/ubuntu/data120g"|os.environ.get("HARNESS_ROOT_DIR", ".")|g'
  # Catch-all: any remaining "/media/ubuntu/data120g/plans<sub-path>" literal → env-based fallback.
  # Keeps the string a valid Python expression (os.path.join) so the hook still parses.
  #
  # Order matters (recurrence guard, HARNESS-SYNC-RECONCILE-2-a Gate D):
  #   The bare-path form can appear as the *default argument* of an existing
  #   os.environ.get(...) call. Substituting it with another os.environ.get(...)
  #   produced nested `get("X", os.environ.get("X", "."))`. So collapse that case
  #   FIRST to a plain "." default, then handle the remaining standalone literals.
  find "$STAGE/hooks" -name "*.py" | xargs sed -i \
    -e 's|os\.environ\.get(\("[A-Z_]*"\), "/media/ubuntu/data120g/plans")|os.environ.get(\1, ".")|g' \
    -e 's|"/media/ubuntu/data120g/plans/\([A-Za-z0-9_/]*\)"|os.path.join(os.environ.get("HARNESS_PLANS_DIR", "."), "\1")|g' \
    -e 's|"/media/ubuntu/data120g/plans"|os.environ.get("HARNESS_PLANS_DIR", ".")|g'
  echo "      Done."
else
  echo "[WARN] Hooks source not found: $HOOKS_SRC — skipped."
fi

# 3. Report differences + private-path gate
echo "[3/3] Comparing the staged copy with this repo..."

report_area() {
  local name="$1"
  if [[ ! -d "$STAGE/$name" || ! -d "$DEST/$name" ]]; then
    return 0
  fi
  echo "  --- $name ---"
  diff -rq --strip-trailing-cr \
    -x "__pycache__" -x ".pytest_cache" -x "fixtures" \
    "$STAGE/$name" "$DEST/$name" 2>&1 \
    | sed -e "s|$STAGE/|staged/|g" -e "s|$DEST/||g" -e 's|^|         |' || true
}

report_area skills
report_area hooks

# Private-path scan. POSIX grep, not `git grep`: under Git Bash an argument starting with "/" is
# rewritten to a Windows path before it reaches git.exe, so `git grep '/media/...'` silently
# matches nothing. `git ls-files --cached --others --exclude-standard` covers tracked files plus
# new untracked ones, while leaving locally excluded files (session docs) out of the scan.
REPO_FILES=()
while IFS= read -r -d '' f; do
  REPO_FILES+=("$f")
done < <(cd "$DEST" && git ls-files -z --cached --others --exclude-standard)
if [[ ${#REPO_FILES[@]} -eq 0 ]]; then
  echo ""
  echo "[ERROR] No publishable files listed — is $DEST a git work tree?"
  echo "        Aborting instead of reporting an empty scan as clean."
  exit 1
fi

REPO_HITS="$( (cd "$DEST" && grep -nIsE "$LEAK_PATTERN" "${REPO_FILES[@]}" || true) \
  | grep -v '^sync-from-source\.sh:' || true )"
STAGED_HOOK_HITS=""
STAGED_SKILL_HITS=""
if [[ -d "$STAGE/hooks" ]]; then
  STAGED_HOOK_HITS="$(grep -rnIsE --exclude-dir="__pycache__" --exclude-dir=".pytest_cache" \
    "$LEAK_PATTERN" "$STAGE/hooks" || true)"
fi
if [[ -d "$STAGE/skills" ]]; then
  STAGED_SKILL_HITS="$(grep -rnIsE --exclude-dir="__pycache__" --exclude-dir=".pytest_cache" \
    "$LEAK_PATTERN" "$STAGE/skills" || true)"
fi

echo "  --- private paths ---"
if [[ -n "$STAGED_SKILL_HITS" ]]; then
  echo "  [WARN] staged skills carry private paths. Do NOT port these lines as they are:"
  echo "$STAGED_SKILL_HITS" | sed -e "s|$STAGE/|staged/|g" -e 's|^|         |'
fi
if [[ -n "$REPO_HITS" ]]; then
  echo "  [ERROR] this repo's publishable files carry private paths:"
  echo "$REPO_HITS" | sed -e 's|^|         |'
fi
if [[ -n "$STAGED_HOOK_HITS" ]]; then
  echo "  [ERROR] staged hooks carry private paths:"
  echo "$STAGED_HOOK_HITS" | sed -e "s|$STAGE/|staged/|g" -e 's|^|         |'
fi
if [[ -z "$STAGED_SKILL_HITS$REPO_HITS$STAGED_HOOK_HITS" ]]; then
  echo "         none."
fi

if [[ $APPLY_HOOKS -eq 1 ]]; then
  echo ""
  if [[ -n "$REPO_HITS$STAGED_HOOK_HITS" ]]; then
    echo "[ERROR] --apply-hooks refused: clear the private paths above first. Nothing was written."
    exit 1
  elif [[ ! -d "$STAGE/hooks" ]]; then
    echo "[WARN] --apply-hooks requested but no hooks were staged — nothing to apply."
  else
    cp -R "$STAGE/hooks/." "$DEST/hooks/"
    echo "[apply] Staged hooks copied into hooks/. Nothing was deleted — review any 'Only in' line above."
  fi
fi

echo ""
echo "=== Sync report complete ==="
echo "Staging kept for selective porting: $STAGE"
echo "  Skills: port by hand, e.g. diff -u \"$STAGE/skills/<file>\" \"$DEST/skills/<file>\""
echo "  Hooks : re-run with --apply-hooks to copy them in"
echo "  Delete the staging directory when done: rm -rf \"$STAGE\""
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Update plugin.json / .claude-plugin/marketplace.json if needed"
echo "  3. Follow RELEASE_POLICY.md (release procedure)"

if [[ -n "$REPO_HITS$STAGED_HOOK_HITS" ]]; then
  exit 1
fi
