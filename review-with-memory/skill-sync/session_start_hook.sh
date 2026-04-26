#!/usr/bin/env bash
# SessionStart guard for sync_project.py — only fires when cwd looks like a
# real project AND we haven't already advised today.
#
# Wire into ~/.claude/settings.json under "hooks.SessionStart":
#   { "matcher": "", "hooks": [{
#       "type": "command",
#       "command": "bash /path/to/session_start_hook.sh",
#       "timeout": 10
#   }] }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$SCRIPT_DIR/sync_project.py"
CACHE_DIR="$HOME/.cache/review-with-memory/skill-sync"
THROTTLE_HOURS="${SKILL_SYNC_THROTTLE_HOURS:-24}"

mkdir -p "$CACHE_DIR"

# --- denylist: directories where skill-sync should never fire --------------
case "$PWD" in
  "$HOME"|"$HOME/"|"/"|"/tmp"|"/tmp/"|*/Downloads/*|*/Desktop/*|*/.Trash/*)
    exit 0 ;;
esac

# --- positive criteria (any one is enough) --------------------------------
is_project=0
[[ -d ".git" ]] && is_project=1
[[ -d ".code-review-graph" ]] && is_project=1
for manifest in package.json pyproject.toml Cargo.toml go.mod Gemfile build.gradle pom.xml deno.json; do
  [[ -f "$manifest" ]] && is_project=1
done
[[ $is_project -eq 0 ]] && exit 0

# --- throttle: don't repeat-advise within THROTTLE_HOURS ------------------
# Hash cwd so two repos with the same name don't collide.
key=$(printf '%s' "$PWD" | shasum | cut -c1-12)
stamp="$CACHE_DIR/$key.stamp"
if [[ -f "$stamp" ]]; then
  age_seconds=$(( $(date +%s) - $(stat -f %m "$stamp" 2>/dev/null || stat -c %Y "$stamp") ))
  if (( age_seconds < THROTTLE_HOURS * 3600 )); then
    exit 0
  fi
fi
touch "$stamp"

# --- run quietly: only print when there's something to act on -------------
exec "$SYNC" --quiet --top-n 5
