#!/usr/bin/env bash
# Stop hook: scan the just-completed turn for high-signal memory triggers.
# Silent unless one fires. When it does, output JSON that re-wakes Claude
# (decision: "block") with a reason instructing it to write a memory entry.
#
# Triggers:
#   1. User used durable-instruction language ("from now on", "always", ...)
#   2. User strongly confirmed a non-obvious approach ("yes exactly", ...)
#   3. Recent doc writes (docs/*.md modified within last 30 min)
#   4. User corrected approach (pushback language)
#
# Tunable via per-project trigger files (future): the script reads
# $cwd/.claude/memory-triggers.txt for additional patterns if it exists.

set -uo pipefail

# Read stdin JSON from Claude Code
input=$(cat)

# Bail if jq isn't available — fail open, never break the harness
command -v jq >/dev/null 2>&1 || exit 0

# Avoid recursion: Stop hooks can fire as a result of decision:"block",
# and stop_hook_active=true on the second entry signals re-entry.
if [[ "$(echo "$input" | jq -r '.stop_hook_active // false')" == "true" ]]; then
  exit 0
fi

transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

[[ -z "$transcript_path" || ! -f "$transcript_path" ]] && exit 0
[[ -z "$cwd" ]] && cwd="$PWD"

# Pull the last user message and last assistant message from the JSONL
# transcript. Each line is a turn record; we use jq to extract content.
last_user=$(
  jq -r 'select(.type == "user") | .message.content // empty | if type == "string" then . else (map(select(.type == "text") | .text) | join("\n")) end' \
    "$transcript_path" 2>/dev/null | tail -1
)
last_assistant=$(
  jq -r 'select(.type == "assistant") | .message.content // empty | if type == "string" then . else (map(select(.type == "text") | .text) | join("\n")) end' \
    "$transcript_path" 2>/dev/null | tail -1
)

# If we can't read the transcript, fail open
[[ -z "$last_user$last_assistant" ]] && exit 0

# Encode cwd to project memory dir name. Claude Code replaces every
# non-alphanumeric (and non-hyphen) char with "-", so "_" and "." also
# convert. Example: /Users/foo/omoi_os -> -Users-foo-omoi-os.
encoded_cwd=$(echo "$cwd" | sed 's/[^a-zA-Z0-9-]/-/g')
memory_dir="$HOME/.claude/projects/${encoded_cwd}/memory"

triggers=()

# 1. Durable-instruction language
#    word boundaries via regex \b not portable in BSD grep, use spaces/punctuation
if echo "$last_user" | grep -iE '(from now on|always |never |stop doing|remember (this|that|to)|keep doing that|don.?t (do|use)|each time|whenever)' >/dev/null 2>&1; then
  triggers+=("durable_instruction")
fi

# 2. Strong confirmation of non-obvious approach
if echo "$last_user" | grep -iE '(yes,? exactly|yes,? perfect|spot on|exactly right|that.?s the (right|correct) (call|approach|move)|good call|perfect,? keep)' >/dev/null 2>&1; then
  triggers+=("strong_confirmation")
fi

# 3. Doc writes in the current turn — scope to Write/Edit/MultiEdit/NotebookEdit
#    tool_use entries on docs/*.md files since the last user message.
#    Avoids false positives from stale mtime in prior turns.
docs_written=$(
  jq -sr '
    (map(.type) | to_entries | map(select(.value == "user")) | last | .key // -1) as $u
    | .[$u + 1:]
    | map(select(.type == "assistant" and (.message.content | type == "array")))
    | [.[] | .message.content[]]
    | map(select(.type == "tool_use"))
    | map(select(.name == "Write" or .name == "Edit" or .name == "MultiEdit" or .name == "NotebookEdit"))
    | map(.input.file_path // "")
    | map(select(. != "" and endswith(".md") and test("(^|/)docs/")))
    | .[]
  ' "$transcript_path" 2>/dev/null
)
[[ -n "$docs_written" ]] && triggers+=("recent_doc_write")

# 4. Correction / pushback language
if echo "$last_user" | grep -iE '(no,? (do |that.?s |don.?t)|wrong|that.?s not|actually,?|fix (the|those|these) errors? before|you should probably)' >/dev/null 2>&1; then
  triggers+=("user_correction")
fi

# Per-project additional patterns (optional)
if [[ -f "$cwd/.claude/memory-triggers.txt" ]]; then
  while IFS= read -r pat; do
    [[ -z "$pat" || "$pat" == \#* ]] && continue
    if echo "$last_user" | grep -iE "$pat" >/dev/null 2>&1; then
      triggers+=("project:$pat")
    fi
  done < "$cwd/.claude/memory-triggers.txt"
fi

# Silent if no triggers fired
[[ "${#triggers[@]}" -eq 0 ]] && exit 0

# Compose the reminder, naming the specific triggers so Claude knows what to look at
trigger_list=$(IFS=, ; echo "${triggers[*]}")
reminder=$(cat <<EOF
Memory-write trigger fired: ${trigger_list}

The just-completed turn contains content worth remembering across sessions.
Consider writing one focused memory entry to: ${memory_dir}/

Memory types (pick one):
- feedback : how to work with the user (most common for durable_instruction, strong_confirmation, user_correction)
- project  : project-specific state, decisions, blockers (most common for recent_doc_write — mirror the why-it-matters)
- user     : user role/preferences/knowledge details
- reference: external system pointers

Format: see existing files in ${memory_dir}/ for the frontmatter shape.
After writing, update ${memory_dir}/MEMORY.md to add a one-line index entry.

Skip silently if nothing new was learned this turn (false positive — the
trigger fired on a phrase that was incidental). Do NOT write speculative or
duplicate memory.
EOF
)

# Block-and-wake: tell Claude to continue with this reason as the prompt
jq -nc --arg reason "$reminder" '{decision: "block", reason: $reason}'
