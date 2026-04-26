---
description: Save a fact to long-term memory (Hindsight), tagged by current repo and cwd.
allowed-tools: Bash
---

The user wants to remember the following fact: **$ARGUMENTS**

Steps:

1. Determine the current repo name with `git rev-parse --show-toplevel` (basename) so the bank id is `kh-::<repo>`. If not in a git repo, use `kh-::scratch`.
2. Build a tag list: include `source:manual`, `repo:<name>`, and `cwd:<basename of pwd>`. If the user's text mentions specific file paths, also add `file:<path>` for each (max 5).
3. Call the bridge:

```bash
uv run --quiet /Users/kevinhill/Coding/Tooling/coding-toolbelt/review-with-memory/scripts/hindsight-bridge.py retain \
  --bank "<resolved-bank>" \
  --content "$ARGUMENTS" \
  --context "manual /remember slash command" \
  --tags "<comma-separated-tags>"
```

4. Confirm to the user in one short sentence: what was saved, to which bank, and how many tags. Don't paraphrase the content — they wrote it deliberately.

If the bridge command fails (Hindsight not running, network error, etc.), tell the user the failure mode in one sentence and suggest `bash ~/Coding/Tooling/coding-toolbelt/review-with-memory/scripts/start-hindsight.sh -d` if it looks like the server is down.
