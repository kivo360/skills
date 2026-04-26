# oh-my-openagent Hooks

This directory contains hooks for the oh-my-openagent system that detect and enforce linter/build error loop escalation.

## How Hooks Work

oh-my-openagent uses a **hook system** that intercepts tool calls and can inject context back to the agent or modify behavior. The hooks are configured in `~/.claude/settings.json`.

### Hook Types

#### PostToolUse Hook
Fires AFTER a tool executes. Can inject context messages to guide the agent.

```
Agent calls tool (e.g., lsp_diagnostics)
    ↓
Tool executes, returns output
    ↓
PostToolUse hook fires with: { session_id, tool_name, tool_input, tool_response }
    ↓
Hook outputs JSON to stdout:
    - {} = no intervention
    - { hookSpecificOutput: { hookEventName, additionalContext } } = inject message to agent
```

#### PreToolUse Hook (Blocking)
Fires BEFORE a tool executes. Can BLOCK the tool from running.

```
Agent calls tool (e.g., Edit)
    ↓
PreToolUse hook fires with: { session_id, tool_name, tool_input }
    ↓
Hook exits:
    - Exit 0 = ALLOW (tool proceeds)
    - Exit 2 = BLOCK (stderr message shown to agent, tool does NOT execute)
```

### Hook Output Format

**PostToolUse** — inject message:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "This message will be shown to the agent"
  }
}
```

**PreToolUse** — block with message:
```javascript
process.stderr.write("⛔ EDIT BLOCKED — message here\n");
process.exit(2); // BLOCK
```

### Registration Format

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit",
        "hooks": [{ "type": "command", "command": "node /path/to/hook.mjs" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "LspDiagnostics",
        "hooks": [{ "type": "command", "command": "node /path/to/hook.mjs" }]
      }
    ]
  }
}
```

---

## Hooks in This Directory

### 1. linter-loop-escalation.mjs (PostToolUse)

Detects when an agent is stuck in a linter/build error loop and injects escalating guidance with explicit model-switch instructions.

**Monitors:**
| Tool | Purpose |
|------|---------|
| `LspDiagnostics` | TypeScript, ESLint, Python, Go, Rust, etc. errors |
| `Bash` | Build/lint commands: `tsc`, `eslint`, `cargo`, `pytest`, `make`, etc. |
| `Edit` | Tracks which files are being edited (for hot-spot detection) |

**Escalation Tiers:**

| Tier | Errors | Message |
|------|--------|---------|
| 1 | 2 | Soft guidance — "try fundamentally different approach" |
| 2 | 3 | Firm redirect — explicit `task()` escalation |
| 3 | 4 | HARD STOP — switch models NOW with `ultrawork` or `task({ category: 'ultrabrain' })` |
| 4 | 5+ | NUCLEAR — consult `@oracle`, then follow guidance exactly |

**Advanced Features:**

1. **Language-Agnostic Fingerprinting** — content-hash approach works with any linter
2. **Severity Filtering** — warnings ignored, only errors trigger escalation
3. **Ping-Pong Detection** — detects when agent alternates between same errors (e.g., fix A breaks B, fix B breaks A)
4. **Cross-Session Learning** — remembers how errors were resolved in previous sessions
5. **Cooldown** — after Tier 3/4, gives escalated model time to work
6. **Resolution Summary** — tells agent when errors finally clear

### 2. edit-block-on-escalation.mjs (PreToolUse)

**TRUE enforcement** — blocks the agent from editing files that have triggered Tier 3+ escalation.

**How it works:**
- Fires BEFORE Edit tool executes
- Reads linter state from `/tmp/omo-linter-state/{session_id}.json`
- If `consecutiveMatches >= HARD_THRESHOLD` AND file matches `lastFile`:
  - Exit with code 2 (BLOCK)
  - Shows agent a blocking message with escalation instructions
- Block lifts when:
  - Different error appears (progress made)
  - Clean output detected
  - Cooldown expires
  - Different file is being edited

---

## Configuration

All thresholds can be overridden via environment variables:

| Variable | Default | Description |
|----------|--------|-------------|
| `OMA_SOFT_THRESHOLD` | 2 | Tier 1 trigger |
| `OMA_HARD_THRESHOLD` | 3 | Tier 2/3 trigger |
| `OMA_NUCLEAR_THRESHOLD` | 5 | Tier 4 trigger |
| `OMA_STALE_MINUTES` | 5 | Reset after N minutes of inactivity |
| `OMA_COOLDOWN_MINUTES` | 2 | Cooldown after Tier 3 |
| `OMA_COOLDOWN_NUCLEAR_MINUTES` | 3 | Cooldown after Tier 4 |
| `OMA_PINGPONG_THRESHOLD` | 3 | Ping-pong loop detection |
| `OMA_PINGPONG_WINDOW` | 10 | Fingerprint window for ping-pong |

---

## State & Solutions

**Session State:** `/tmp/omo-linter-state/{session_id}.json`
- Resets on: clean output, different error, 5+ min staleness
- Preserves: attempt history, fingerprints for ping-pong detection

**Cross-Session Solutions:** `~/.config/opencode/hooks/error-solutions.json`
- Records: fingerprint → { fix that worked, avg attempts, success count }
- Limit: 100 entries (LRU eviction)
- Read once at startup, written only on resolution

---

## Debug Mode

Enable debug logging:

```bash
OMA_HOOK_DEBUG=1 node /Users/kevinhill/.config/opencode/hooks/linter-loop-escalation.mjs < /dev/null
```

Debug output goes to `/tmp/omo-linter-state/hook-debug.log`.

---

## Available Escalation Paths

When hooks tell you to escalate, use one of:

```javascript
// Switch to more powerful model (recommended for tier 3+)
task({ category: 'ultrabrain', prompt: 'Failed on [error]. Tried: [attempts]. Need fresh approach.' })

// Escalate to Claude Opus
task({ category: 'unspecified-high', prompt: 'Debug: [error details]' })

// Switch model mid-session
ultrawork
```

### Available Categories

| Category | Model | Use Case |
|----------|-------|----------|
| `quick` | Fast cheap model | Simple tasks |
| `unspecified-low` | Claude Haiku | Minor issues |
| `unspecified-high` | Claude Opus 4.6 | Complex debugging |
| `ultrabrain` | GPT-5.4 xhigh | Deep reasoning, truly stuck |
| `deep` | Deep research | Architectural issues |
| `visual-engineering` | Vision-capable | UI/layout issues |

### Available Agents

| Agent | Purpose |
|-------|---------|
| `@oracle` | Architecture consultant, root cause analysis |
| `@librarian` | Documentation search |
| `@explore` | Codebase exploration |
