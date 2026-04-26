#!/usr/bin/env bash
# PreToolUse hook for Bash: detects Python/uv/pip usage and reminds Claude
# to load the uv-package-manager skill if not already loaded.
#
# Triggers on:
#   - python, python3 commands
#   - uv subcommands (add, pip, tool, run, venv, init, sync, lock)
#   - pip commands (legacy — should redirect to uv)
#   - requirements.txt references
#   - .py file execution
#
# Outputs JSON with decision:"block" to inject the reminder, or exits silently.

set -uo pipefail

input=$(cat)

command -v jq >/dev/null 2>&1 || exit 0

# Extract the bash command from the tool input
tool_input=$(echo "$input" | jq -r '.tool_input.command // empty')
[[ -z "$tool_input" ]] && exit 0

# Check if this is a Python-related command
is_python=false

# Direct python/uv/pip invocations
if echo "$tool_input" | grep -E '(^|\s)(python[0-9.]*|uv|pip[0-9.]*|pipx|conda|poetry)\s' >/dev/null 2>&1; then
  is_python=true
fi

# Running .py files
if echo "$tool_input" | grep -E '\.py\b' >/dev/null 2>&1; then
  is_python=true
fi

# Installing packages
if echo "$tool_input" | grep -E '(install|add|remove)\s+\S' >/dev/null 2>&1; then
  # Only if it's in a Python context (uv, pip, etc) — already caught above
  if echo "$tool_input" | grep -E '(^|\s)(uv|pip|pipx|conda|poetry)\s' >/dev/null 2>&1; then
    is_python=true
  fi
fi

[[ "$is_python" == "false" ]] && exit 0

# Check if the skill was already mentioned in recent context — avoid duplicate reminders
# We can't perfectly check this, but we use a temp file to debounce (5 min cooldown)
cooldown_file="/tmp/claude-python-skill-reminder"
if [[ -f "$cooldown_file" ]]; then
  last_reminder=$(stat -f %m "$cooldown_file" 2>/dev/null || stat -c %Y "$cooldown_file" 2>/dev/null || echo 0)
  now=$(date +%s)
  # 300 second = 5 minute cooldown
  if (( now - last_reminder < 300 )); then
    exit 0
  fi
fi

# Write cooldown marker
touch "$cooldown_file"

# Build the reminder
reminder=$(cat <<'EOF'
🐍 Python activity detected — load the uv-package-manager skill.

Run: /skill uv-package-manager

Decision tree summary:
- CLI tool globally  → uv tool install <pkg>
- Project dependency → uv add <pkg>
- One-off script     → uv run --with <pkg> python script.py
- Reusable script    → PEP 723 inline metadata (# /// script / dependencies = [...] / ///)
- Global importable  → dedicated venv at ~/.global-python
- Legacy venv        → uv pip install <pkg>
- Try before install → uvx <pkg>

NEVER use pip, pipx, poetry, or conda. uv handles everything.
EOF
)

jq -nc --arg reason "$reminder" '{decision: "block", reason: $reason}'
