#!/usr/bin/env bash
# Install /remember and /recall slash commands into ~/.claude/commands/.
# Symlinks rather than copies so edits in this repo propagate immediately.
#
# Usage:
#   bash install.sh             # install
#   bash install.sh --uninstall # remove the symlinks (only if they point here)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.claude/commands"
mkdir -p "$TARGET_DIR"

UNINSTALL=0
[[ "${1:-}" == "--uninstall" ]] && UNINSTALL=1

for name in remember recall; do
  src="$SCRIPT_DIR/$name.md"
  dst="$TARGET_DIR/$name.md"
  if [[ $UNINSTALL -eq 1 ]]; then
    if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
      rm "$dst"
      echo "removed $dst"
    else
      echo "skip $dst (not our symlink)"
    fi
    continue
  fi
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    bk="$dst.bak.$(date +%s)"
    echo "  backing up existing $dst → $bk"
    mv "$dst" "$bk"
  fi
  ln -sfn "$src" "$dst"
  echo "installed $dst → $src"
done

if [[ $UNINSTALL -eq 0 ]]; then
  echo
  echo "Restart Claude Code, then try:  /remember <fact>   or   /recall <topic>"
fi
