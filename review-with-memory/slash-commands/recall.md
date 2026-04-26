---
description: Query long-term memory (Hindsight) for facts relevant to the given topic, scoped to the current repo's bank.
allowed-tools: Bash
---

The user is asking: **$ARGUMENTS**

Steps:

1. Determine the bank: basename of `git rev-parse --show-toplevel`, prefixed with `kh-::`. Fallback to `kh-::scratch`.
2. Run the bridge with a low budget (this is an interactive lookup, latency matters):

```bash
uv run --quiet /Users/kevinhill/Coding/Tooling/coding-toolbelt/review-with-memory/scripts/hindsight-bridge.py recall \
  --bank "<resolved-bank>" \
  --query "$ARGUMENTS" \
  --budget low \
  --max-tokens 1024
```

3. Parse the JSON output's `response.results[]` array.
4. Present results compactly:
   - One line per memory: a `★`, then the text (trim/wrap to ~120 chars), then `(type, date)` in dim tone if your terminal supports it.
   - If `results` is empty, say so plainly — don't fabricate.
   - If the response is large, summarize: "5 memories found, top 3 below."
5. Don't add commentary, analysis, or "let me know if you want more" — just the list. The user will follow up if they want more.

If the bridge fails, report the failure mode in one sentence.
