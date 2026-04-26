#!/usr/bin/env bash
# Install / uninstall the git-bridge hooks into a target repo.
#
# Installs:
#   <repo>/.git/hooks/post-commit  →  retain_commit.py HEAD --quiet
#   <repo>/.git/hooks/pre-commit   →  advise_staged.py --silent-on-empty
#
# Existing hooks are renamed with a timestamp suffix, never overwritten.
#
# Usage:
#   bash install_hooks.sh --repo <path>            # install
#   bash install_hooks.sh --repo <path> --uninstall
#   bash install_hooks.sh --repo <path> --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RETAIN="$SCRIPT_DIR/retain_commit.py"
ADVISE="$SCRIPT_DIR/advise_staged.py"

REPO=""
UNINSTALL=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$REPO" ]]; then
  echo "missing --repo <path>" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
HOOKS_DIR="$REPO/.git/hooks"
[[ -d "$HOOKS_DIR" ]] || { echo "not a git repo: $REPO" >&2; exit 2; }

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY-RUN: $*"
  else
    eval "$@"
  fi
}

backup_existing() {
  local hook="$1"
  if [[ -e "$hook" && ! -L "$hook" ]]; then
    local backup="$hook.bak.$(date +%s)"
    echo "  backing up existing $(basename "$hook") → $(basename "$backup")"
    run mv "$hook" "$backup"
  elif [[ -L "$hook" ]]; then
    echo "  removing existing symlink $(basename "$hook")"
    run rm "$hook"
  fi
}

write_hook() {
  local name="$1"
  local body="$2"
  local hook="$HOOKS_DIR/$name"
  backup_existing "$hook"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY-RUN: would write $hook with:"
    echo "$body" | sed 's/^/    /'
  else
    printf '%s\n' "$body" > "$hook"
    chmod +x "$hook"
  fi
}

if [[ $UNINSTALL -eq 1 ]]; then
  echo "uninstalling git-bridge hooks from $REPO"
  for h in pre-commit post-commit; do
    if [[ -e "$HOOKS_DIR/$h" ]] && grep -q 'review-with-memory/git-bridge' "$HOOKS_DIR/$h" 2>/dev/null; then
      echo "  removing $h"
      run rm "$HOOKS_DIR/$h"
      latest_backup="$(ls -t "$HOOKS_DIR/$h".bak.* 2>/dev/null | head -1 || true)"
      if [[ -n "$latest_backup" ]]; then
        echo "  restoring $h from $(basename "$latest_backup")"
        run mv "$latest_backup" "$HOOKS_DIR/$h"
      fi
    else
      echo "  $h: not a git-bridge hook (skipping)"
    fi
  done
  exit 0
fi

echo "installing git-bridge hooks into $REPO"
write_hook "post-commit" "#!/usr/bin/env bash
# review-with-memory/git-bridge: auto-retain every commit to Hindsight
exec '$RETAIN' --quiet >/dev/null 2>&1 &"

write_hook "pre-commit" "#!/usr/bin/env bash
# review-with-memory/git-bridge: advisory recall on staged files
exec '$ADVISE' --silent-on-empty"

if [[ $DRY_RUN -eq 0 ]]; then
  echo
  echo "installed."
  echo "  $HOOKS_DIR/post-commit  → $RETAIN"
  echo "  $HOOKS_DIR/pre-commit   → $ADVISE"
fi
