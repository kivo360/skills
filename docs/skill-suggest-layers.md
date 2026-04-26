# Layered skill suggestion architecture

Last updated: 2026-04-26

This is the live spec for `toolbelt skills suggest`. It documents the
five layers, their latency and accuracy characteristics, the decision
flow, and what's implemented vs what's deferred.

The pipeline is "spend the cheapest layer that's confident enough." A
hot path through Layer 0 + 0.5 returns in <10 ms; Layer 1 is opt-in
because it costs ~5 s cold or ~30–100 ms warm; Layers 2 and 3 only
ever run async (background jobs that *populate* the cache for the
next time a similar prompt arrives).

## Layer summary

| Layer | Mechanism | Latency | When it runs | Status |
|------:|-----------|--------:|--------------|:------:|
| 0    | Keyword match (token-based scoring) | <10 ms | always | ✅ shipped |
| 0.5  | Context rules (regex + tool/domain mentions) | <10 ms | always | ✅ shipped |
| 1    | Embeddings (fastembed `all-MiniLM-L6-v2`, 384 dim) stored in Chroma | <30 ms warm via Chroma / 5 s cold | `--deep` flag, or daemon up | 🟡 in-progress (Chroma swap) |
| 2    | Local GGUF LLM — `unsloth/Qwen3.5-0.8B-GGUF` (Q4_K_M, ~533 MB, 262 k ctx) via node-llama-cpp | 150–400 ms | async, when L1 ambiguous | 🟡 specced |
| 3    | Larger local GGUF LLM — `unsloth/Qwen3.5-2B-GGUF` (Q4_K_M, ~1.3 GB, 262 k ctx) | 600–1200 ms | async, when L2 inconclusive | 🟡 specced |

Memory layer (cross-cutting): every suggest call appends to
`~/.agents/suggest-memory.jsonl`. Layer 0's first job is to recall
identical prompts before doing any matching. ✅ shipped.

## Decision flow

```
┌─────────────────────────────────────────────────────────────┐
│ prompt arrives (UserPromptSubmit hook, opencode plugin,     │
│ or `toolbelt skills suggest "..."`)                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                ┌────────────────┐
                │ Memory recall  │  hash(prompt) seen recently?
                │  (free, <2 ms) │  return cached answer.
                └────────┬───────┘
                  miss   │
                         ▼
              ┌─────────────────────────┐
              │ Layer 0 — keyword match │   tokens × name/triggers/desc
              │   <10 ms                │   stop-words, weak-name-tokens,
              └────────────┬────────────┘   stemmer, negation detection
                           │
                           ▼
              ┌─────────────────────────┐
              │ Layer 0.5 — context rule│   regex + primary-token check
              │   boosts (cheap)        │   negation suppresses tainted
              └────────────┬────────────┘   rules (no boost on "not stripe")
                           │
                           ▼
              ┌─────────────────────────┐
              │ confidence ≥ uncertaintyThreshold (0.55)?
              └────────────┬────────────┘
                ┌──────────┴──────────┐
              yes                     no
                │                     │
                ▼                     ▼
       ┌─────────────────┐   ┌────────────────────────────┐
       │ return matches  │   │ Layer 1 — embeddings       │
       │ + memory append │   │   (only if --deep + cache  │
       └─────────────────┘   │    is fresh)               │
                             │   - embed prompt           │
                             │   - cosine vs all skills   │
                             │   - veto kw if cos < floor │
                             │   - blend kwConf 0.6 +     │
                             │     embConf 0.4            │
                             └─────────────┬──────────────┘
                                           │
                                           ▼
                              ┌──────────────────────────┐
                              │ confidence ≥ deep floor? │
                              └─────────────┬────────────┘
                                ┌───────────┴─────────────┐
                              yes                          no
                                │                          │
                                ▼                          ▼
                       ┌─────────────────┐    ┌──────────────────────────┐
                       │ return matches  │    │ schedule async Layer 2/3 │
                       │ + memory append │    │ (do NOT block hook)      │
                       └─────────────────┘    │ return: best-effort or — │
                                              └──────────────────────────┘
```

## Layer 0 — keyword matcher

Implemented in `src/lib/matcher.ts`. Score breakdown:

| Match type | Points |
|-----------|-------:|
| Exact name match | 30 |
| Name token (non-weak) | 12 |
| Trigger token | 8 |
| Weak name token | 2 |
| Description token | 2 |

Confidence = score / 30, clamped to [0, 1].

Key components:
- ~150-entry stop-word set (grammar, generic verbs, fillers)
- ~50-entry "weak name tokens" set (best, practices, system, flow,
  flows, stream, queue, config, …) — name tokens in this set are
  treated as weak signals to avoid name-collision FPs
- Light Porter-style stemmer (handles -ing, -ed, doubled-consonant)
- Negation detection in a 5-word window after `not / never / no /
  without / skip / avoid / ignore`
- Synonym expansion (only oauth/2fa/pr/monorepo — keeping the set
  tight, broader synonyms cause skill-name flooding)
- Family-orchestrator boost (≥2 siblings → surface the umbrella)

## Layer 0.5 — context rules

Implemented in `src/lib/context-rules.ts`. ~25 hand-written rules,
each declares:

- `id` — namespaced (`tool:*`, `domain:*`, `path:*`, `ext:*`,
  `config:*`, `workflow:*`)
- `test(lower, raw)` — boolean predicate
- `boosts` — skill-name → additive points (typically 4–14)
- `primaryToken` — if this token is in the prompt's negated set,
  the rule does **not** fire

Boosts compose with keyword scores in the same scale, so a primary
tool match (e.g. `tool:bun`) at +14 alone clears the minScore=10 gate
without keyword anchoring.

Cross-layer negation: skills whose name or top triggers contain a
negated token are dropped from the final result, regardless of
whether they came in via keyword, context, or embedding.

## Layer 1 — embeddings (fastembed → Chroma)

Implemented in `src/lib/embeddings.ts`, `src/lib/chroma-store.ts`,
`src/commands/skills/embed.ts`, `src/commands/skills/serve.ts`.

- **Embedding model**: `Xenova/all-MiniLM-L6-v2` via the `fastembed` npm
  package (uses ONNX Runtime). 22 MB, 384 dim, ~4 ms/doc warm.
- **Vector store**: Chroma (`chromadb` npm @ ^3.4.x). Daemon spawns
  `bunx chroma run --path ~/.agents/chroma-data` as a child process,
  ensures a `skills` collection, upserts each (name, vector, {tier,
  description, mtime, source}) record. Cosine similarity is delegated
  to Chroma's HNSW index. Persists across daemon restarts.
- **Offline fallback**: `~/.agents/skill-embeddings.json` (~2.5 MB for
  294 skills), keyed by SKILL.md mtime. Used by `--fast` paths and
  any caller that can't reach the daemon. Same data, different store —
  the JSON is the source-of-truth dump; Chroma is the query index.
- **Calibration**:
  - cosine ≤ 0.45 → confidence 0 (treated as no match)
  - cosine ≥ 0.80 → confidence 1
  - linear interpolation between
- **Veto rule**: if keyword confidence > 0.6 but cosine < 0.45, the
  keyword score is downgraded to 0.55× rather than blended. Catches
  word-collision FPs (e.g. `kotlin-coroutines-flows` matching
  "subscription churn flows" via the "flows" token).
- **Embedding-only floor**: a match with no keyword anchor and no
  context boost needs cosine confidence ≥ 0.55 to make the cut.
  Empirically, MiniLM at 0.45–0.55 on short prompts is "vaguely
  related, not useful."

### Daemon (`toolbelt skills serve`)

Pre-loads the embedding model **and** spawns Chroma as a child process,
serving localhost-only HTTP on port 9988. Chroma listens on its own
default port (8000); the daemon proxies all queries through `/match`
so callers never talk to Chroma directly.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | model + skills loaded + chroma status + uptime |
| `POST /embed` | `{ text }` → `{ vector }` |
| `POST /embed-batch` | `{ texts }` → `{ vectors }` |
| `POST /match` | `{ prompt, deep, tiers, limit }` → HybridResult |
| `POST /reload` | re-read skills + re-sync chroma collection from JSON |

**Lifecycle:** SIGTERM → daemon stops Chroma child → unlinks pid file →
exits. If Chroma fails to start (port conflict, missing binary), the
daemon keeps running with the JSON-cosine fallback and reports
`chroma: down` in `/health`.

The CLI's `suggest` command pings the daemon with an 80 ms timeout.
On timeout/refused, it falls through to in-process matching, which
runs Layer 0 + 0.5 only unless `--deep` is set explicitly. Hooks pass
`--fast` to skip the daemon entirely; latency stays sub-10 ms.

## Layer 2 — local GGUF LLM (specced, deferred)

**Goal**: resolve cases where embedding similarity is bunched (top-3
matches all within 0.05 cosine of each other), without any network
call.

**Model**: [`unsloth/Qwen3.5-0.8B-GGUF`](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF)
at **Q4_K_M (~533 MB)**. 800 M params, 24 layers, 1024 hidden dim,
**262 k native context** — enough to fit the entire skill catalog
(~295 × ~250 tokens ≈ 75 k) in a single prompt with room to spare.
Vision-language capable but we only use the text head.

**Runtime**: `node-llama-cpp` (Bun-compatible, prebuilt binaries for
darwin-arm64 + linux-x64). Model cached at
`~/.agents/llm-cache/Qwen3.5-0.8B-Q4_K_M.gguf`. Lazy-loaded on first
use; held in memory inside the daemon process.

**Prompt template** (~200 token budget):
```
You are a skill router. Given a user request and a shortlist of
candidate skills, return the single most relevant skill name, or
"none" if nothing fits.

Request: {prompt}

Candidates:
- {name1}: {1-line desc}
- {name2}: {1-line desc}
…

Answer with just the skill name or "none".
```

**Triggering conditions** (any one):
1. Embedding top-3 within 0.05 cosine of each other
2. Best embedding score in 0.45–0.60 band (uncertain)
3. Memory shows the same prompt has been suggested ≥2 different
   skills in the last 30 days (disagreement)

**Async-only**: this layer never blocks the synchronous suggest
call. It runs in a detached subprocess, writes its decision to
`~/.agents/suggest-cache.json` keyed by prompt hash. The next time
a similar prompt arrives, Layer 0's memory recall finds it instantly.

## Layer 3 — larger local GGUF LLM (specced, deferred)

**Goal**: ≤2% of suggest calls — only when L2 (0.8B) returned "none"
or low confidence AND the prompt is novel (no near-duplicate in memory
within the last 30 days). No cloud calls; everything stays local.

**Model**: [`unsloth/Qwen3.5-2B-GGUF`](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF)
at **Q4_K_M (~1.3 GB)**. 2 B params, 24 layers, 2048 hidden dim,
**262 k native context**. Stronger reasoning + better catalog-wide
synthesis when the small model is uncertain. Vision-language capable
but we only use the text head.

**Runtime**: same `node-llama-cpp` host as L2. Model cached at
`~/.agents/llm-cache/Qwen3.5-2B-Q4_K_M.gguf`. Lazy-loaded on first
trigger; held in memory inside the daemon for 30 minutes after last
use, then evicted (~1.3 GB resident otherwise).

**Trigger gate**:
1. L2 returned `none` or top confidence < 0.6
2. No identical-hash recall in last 30 days
3. Daemon has been up ≥ 60 s (avoids stampede on startup)
4. Per-day soft cap: 200 calls (logged, not enforced — purely advisory)

**Prompt** (~5–10 KB depending on catalog):
```
You are a skill router. Given the user request and the full skill
catalog, pick up to 3 skills that genuinely apply. Prefer "none" over
weak guesses.

Request: {prompt}
Recent context (last 5 prompts): {recent}

Skills:
{name1}: {1-line description}
{name2}: {1-line description}
…

Respond as JSON:
{"picks": [{"name": "x", "confidence": 0.0–1.0, "reason": "..."}]}
```

**Same async-write pattern**: result lands in `suggest-cache.json`,
recalled by Layer 0 next time. The synchronous suggest call never
waits on this layer.

## Memory layer

Implemented in `src/lib/suggest-memory.ts`.

- **Format**: NDJSON at `~/.agents/suggest-memory.jsonl`, one record
  per call: `{ ts, hash, preview, layer, suggestions: [{name, conf}] }`
- **Hash**: SHA-1 of normalized lowercased + whitespace-collapsed
  prompt, first 16 chars
- **Recall**: walk file backwards, return newest matching hash within
  30 days
- **Anti-spam**: when the same skill has been suggested in 2 of the
  last 5 records and current confidence is < 0.7, drop it from the
  output (filtered in `suggest.ts`)
- **Rotation**: when file > 2 MB, drop oldest half on next append
- **Privacy**: no payload data, just preview (first 120 chars)

### Candidate replacement: Hindsight

Hindsight ([vectorize-io/hindsight](https://github.com/vectorize-io/hindsight),
MIT, ~10.8k stars) is an "agent memory system that learns" — it
wraps embeddings, structured biomimetic memory (World facts /
Experiences / Mental Models), and reflection passes behind a small
`retain` / `recall` / `reflect` API. It currently holds the
LongMemEval SOTA.

It would replace **only the memory layer** above — not fastembed
(Hindsight uses its own embeddings under the hood, but on its own
server) and not Chroma necessarily (the catalog is static and small;
Hindsight's strength is *learning*, which the catalog doesn't need).

What it could give us:
- Semantic recall for similar past prompts (we currently only
  hash-match exact prompts)
- Usage learning — which skills did the user actually use after we
  suggested them? Hindsight can fold that into retrieval ranking
- Per-project / per-user banks via metadata filters

What it costs:
- Docker dependency (Postgres-backed API on :8888, UI on :9999)
  OR Python embedded mode — neither is a Bun drop-in
- LLM API key (OpenAI / Anthropic / etc.) for retain + reflect
  passes; ongoing token cost
- One more long-running process to manage (we already manage Chroma)
- Network round-trip on every suggest call (~10–50 ms localhost)

Status: 🟡 evaluation pending. See
[`highlight-memory-evaluation.md`](./highlight-memory-evaluation.md)
once a delegated session writes it (filename inherited from earlier
naming — the doc evaluates Hindsight specifically).

## Eval corpus

`src/eval/probes.json` — 25 hand-written probes covering:

| Category | Count |
|----------|------:|
| TP-positive (single expected) | 11 |
| TP-multi (multi expected) | 6 |
| TP-domain (semantic) | 3 |
| TP-tool-mention | 3 |
| TN-no-match | 3 |
| TN-too-vague | 1 |
| TN-negation | 1 |
| Veto test | 1 |

Run via:
```bash
bun src/eval/run-probes.ts          # FAST (no embeddings)
bun src/eval/run-probes.ts --deep   # DEEP (with embeddings)
```

### Current scores

| Mode | Useful | Misfire | TP | TP-weak | FN | FP | TN |
|------|-------:|--------:|---:|--------:|---:|---:|---:|
| FAST (kw + ctx) | 92% | 4% | 19 | 1 | 0 | 1 | 4 |
| DEEP (+ emb) | 96% | 4% | 20 | 0 | 0 | 1 | 4 |

For comparison, V12 (keyword-only, 35 probes from prior session):
49% useful, 17% misfire, 12 TP, 0 FN, 4 FP, 2 WS.

## Open work / followups

- Layer 1: swap JSON cosine loop for Chroma `query()` (in progress)
- Layer 2: implement using `unsloth/Qwen3.5-0.8B-GGUF` Q4_K_M via
  node-llama-cpp; lazy-load inside the daemon
- Layer 3: implement using `unsloth/Qwen3.5-2B-GGUF` Q4_K_M same host
- Async background scheduler so L2/L3 run detached and populate the
  cache without blocking the synchronous suggest call
- Semantic recall in memory (embed past prompts and query Chroma's
  `prompts` collection, not just exact-hash match)
- Telemetry: per-layer hit/miss/latency to
  `~/.agents/telemetry/suggest.ndjson` for offline tuning
- Larger eval corpus (50+ probes covering more edge cases, including
  the L2/L3 ambiguity bands)
- Plugin/Hook share the same daemon — currently both fall back to
  in-process matching when daemon is down
