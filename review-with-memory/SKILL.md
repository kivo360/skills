---
name: review-with-memory
description: Memory-aware code review. Combines code-review-graph blast-radius (MCP) with Hindsight long-term memory (local) so review feedback compounds across PRs. Recalls past lessons for the impacted modules before reviewing, then retains new findings tagged by file/module so the next review benefits. Use when reviewing a PR or diff and you want recurring-bug patterns and prior reviewer feedback surfaced as context. Triggers on "review with memory", "memory-aware review", "review and remember", "review with hindsight". Requires Hindsight server on localhost:8888 and code-review-graph installed.
---

# review-with-memory

Wraps a code review with two contextual layers:

1. **code-review-graph (structural, fresh)** — blast radius of the diff: every caller, dependent, and test that could be impacted.
2. **Hindsight (historical, persistent)** — past review findings, recurring failure modes, and module-specific lessons retained from prior reviews.

The skill is the orchestration script. Two helper scripts in `scripts/` do the Hindsight side; code-review-graph is invoked through its existing MCP tools.

## When to use

- Reviewing a PR, branch diff, or staged changes.
- The codebase has accumulated review history in Hindsight (or you're starting that history now).
- You want the review to factor in *what we learned last time* this area changed, not just what the diff says.

Do **not** use for:
- First-pass triage of a brand-new repo with no review history (no memory to recall yet — use plain `/review` instead, then start retaining).
- Quick syntax/style checks (heavyweight for that).

## Prerequisites

- Hindsight running locally. Use the launcher (it reads `.env`, no creds in shell history):
  ```bash
  cp .env.example .env             # one-time
  # edit .env with your LLM provider/model/key
  bash scripts/start-hindsight.sh -d
  ```
  `.env` is gitignored; `.env.example` is committed. The container's LLM config
  is consumed via `--env-file`, so secrets never appear in `ps` output or shell
  history.
- `code-review-graph` installed and graph built: `code-review-graph install && code-review-graph build`.
- `uv` on PATH (for the bridge script's PEP 723 deps).

Environment knobs (override defaults):
- `HINDSIGHT_API_LLM_PROVIDER` / `HINDSIGHT_API_LLM_BASE_URL` / `HINDSIGHT_API_LLM_MODEL` / `HINDSIGHT_API_LLM_API_KEY` — Hindsight's internal LLM. Any OpenAI-compatible endpoint works (Fireworks, Groq, vLLM, LM Studio, etc.).
- `HINDSIGHT_BASE_URL` — bridge → server, default `http://localhost:8888`
- `HINDSIGHT_BANK_ID` — default derived from repo name (basename of `git rev-parse --show-toplevel`)

## Orchestration

The harness (Claude Code, Cursor, etc.) executes these steps in order. Treat each numbered step as a separate action.

### 1. Health-check the bridge

```bash
uv run "$SKILL_DIR/scripts/hindsight-bridge.py" health
```

If this fails, stop and tell the user to start the Hindsight container. Do not fall back to a no-memory review — the user invoked this skill specifically for memory-aware behavior.

### 2. Determine the diff scope

Default: `git diff --name-only origin/main...HEAD` (or `main` if no `origin/main`).
If the user gave a base ref, use that. If working tree is dirty, include unstaged changes via `git diff --name-only HEAD`.

### 3. Compute blast radius via code-review-graph

Use code-review-graph's MCP tools (already registered if the user ran `code-review-graph install`). The exact tool names vary by version; common ones:
- `review_changes` / `review_delta` / `review_pr` — give it the changed files, get back the blast-radius set + risk hints.
- `explore_codebase` — fall back if review tools aren't available.

Capture:
- `affected_files`: full set including blast radius (changed + their dependents + tests).
- `risk_hints`: anything code-review-graph flags as high-fanout, hub, or untested.

### 4. Derive tags from affected files

```bash
echo "<one-file-per-line>" | uv run "$SKILL_DIR/scripts/derive-tags.py"
```

Returns JSON: `{"tags": ["repo:<name>", "module:<top-dir>", ...], "modules": [...], "files": [...]}`.

These tags are **identity scopes** (which subsystem) — not classifications. Don't add tags like `severity:high` or `type:bug`.

### 5. Recall past lessons from Hindsight

```bash
uv run "$SKILL_DIR/scripts/hindsight-bridge.py" recall \
  --bank "$HINDSIGHT_BANK_ID" \
  --query "<one-line summary of the diff>" \
  --tags "module:auth,module:api" \
  --tags-match any_strict \
  --budget mid
```

`any_strict` excludes untagged memories — for module-scoped retrieval that's what you want. If you also want repo-wide context, do a second recall with `--tags-match any` and the broader `repo:<name>` tag.

### 6. Compose the review prompt

Combine:
- The diff itself.
- Blast-radius file list + risk hints (from step 3).
- Recalled memories formatted as "Prior context for `module:X`:" sections.

Then perform the review as you normally would.

### 7. Retain findings

For each non-trivial finding from the review, retain a memory **scoped by the file/module it applies to**, not by severity or topic.

```bash
uv run "$SKILL_DIR/scripts/hindsight-bridge.py" retain \
  --bank "$HINDSIGHT_BANK_ID" \
  --content "Regex-based session token validation in src/auth/session.ts skipped unicode normalization, allowing lookalike-character bypass. Reviewer caught on diff at L42." \
  --context "code review finding" \
  --tags "module:auth,file:src/auth/session.ts,repo:foo"
```

Rules for what to retain:
- **Retain the lesson, not the diff.** "X validation pattern misses Y class of input" — not "we added Z lines."
- **One memory per finding.** Keep them atomic so recall ranks them well.
- **Tag with file path + module + repo.** Triple-tag so future recalls hit at any granularity.
- **Skip trivia.** Don't retain "renamed variable" or "fixed typo" — those don't compound.

Do **not** call `reflect` here — it's an agentic loop, too expensive for the per-review path. Reserve it for an offline batch ("synthesize a mental model of failure modes in `module:auth` from all retained memories").

## Mental models (advanced)

For high-traffic modules, define a mental model in Hindsight that auto-synthesizes patterns from retained findings. The `hindsight-architect` skill (from vectorize-io/hindsight-skills) can design this. Once defined, fetch it directly in step 5 alongside `recall` — don't trigger it via `reflect`.

## Local testing

```bash
bash scripts/test-local.sh
```

This exercises the Hindsight side end-to-end (health → retain → recall round-trip with a synthetic finding) using a throwaway bank `review-with-memory-test`. It does **not** require `code-review-graph` to be installed — that integration is exercised through the harness's MCP tools, not the test harness.
