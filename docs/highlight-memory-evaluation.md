# Hindsight memory evaluation

Last updated: 2026-04-26

Evaluation of [Hindsight](https://github.com/vectorize-io/hindsight) as the
memory backbone for `toolbelt skills suggest`. The filename inherits from
the original placeholder reference in `skill-suggest-layers.md:324`; the
document evaluates Hindsight specifically.

## TL;DR

Hindsight should not replace fastembed/Chroma, the keyword matcher, or
the local-LLM layers. Those tools fit the static-catalog matching shape
correctly and the existing FAST 92% / DEEP 96% useful scores are already
near the achievable ceiling for catalog-bound matching.

What Hindsight uniquely enables — and what no existing layer can — is
**project-specific signal** and **usage learning**. The recommended
integration is a new optional Layer 0.7 that fires only when L0+L0.5
confidence is below threshold, plus a retain hook on every suggest call.
Hot path latency is unchanged. The 4–8% of suggest calls that today
fall through to weak guesses gain a project-aware recall pass that
costs ~10–50 ms localhost.

A meaningful slice of the infrastructure is already in place from the
`review-with-memory` work pushed to `coding-toolbelt:main`:
per-project banks (`kh-::<repo>`) are populated by five retain streams
(chat, CRG queries, git commits, test failures, manual `/remember`),
mental models auto-refresh on hub nodes, and a Fireworks-backed
Hindsight server runs locally on `:8888`. The remaining work is the
suggester-side glue, gated behind a feature flag.

## Context

The skill suggester is a five-layer pipeline:

| Layer | Mechanism | Latency | Status |
|------:|-----------|--------:|:------:|
| 0    | Keyword match (~150 stopwords, weak-tokens, Porter stem, negation) | <10 ms | ✅ shipped |
| 0.5  | ~25 hand-written context rules | <10 ms | ✅ shipped |
| 1    | fastembed (`all-MiniLM-L6-v2`, 384 dim) → Chroma | <30 ms warm | 🟡 in progress |
| 2    | `Qwen3.5-0.8B-GGUF` async via node-llama-cpp | 150–400 ms | 🟡 specced |
| 3    | `Qwen3.5-2B-GGUF` async | 600–1200 ms | 🟡 specced |
| Memory | NDJSON exact-hash recall in `~/.agents/suggest-memory.jsonl` | <2 ms | ✅ shipped |

Eval scores against the 25-probe corpus:

| Mode | Useful | Misfire | TP | FN | FP | TN |
|------|-------:|--------:|---:|---:|---:|---:|
| FAST (kw + ctx)   | 92% | 4% | 19 | 0 | 1 | 4 |
| DEEP (+ embed)    | 96% | 4% | 20 | 0 | 1 | 4 |

This is high. Per-prompt catalog matching has limited remaining headroom
because the catalog is global and the prompts in the eval corpus are
project-agnostic.

## The framing question

Not "should Hindsight replace the memory layer." That framing under-sells
both the existing system (which is already very good) and Hindsight
(which is built for a different problem). The real question is:

> **Where does Hindsight do something the catalog-bound matcher
> fundamentally cannot?**

The matcher only sees: the prompt, the static catalog of 295 SKILL.md
entries, and a small NDJSON of recent prompts. It does not see *which
project the prompt came from*, *whether suggestions led anywhere*, or
*what work has actually happened in this codebase*. Those are the gaps.

## Tier 1: project-specific signal

The matcher returns the same suggestions for "fix the login flow"
regardless of which repo the prompt came from. But what `login flow`
*means* is project-specific:

- In `kh-::stripe-payments`: probably Stripe Identity + webhook signing
- In `kh-::coding-toolbelt`: probably OAuth flow in the toolbelt CLI
- In `kh-::xyz-frontend`: probably Better Auth on Next.js

Hindsight stores per-project banks tagged with `file:`, `module:`,
`node:`, `repo:`. Recalling against the current project's bank with the
prompt as the query produces a project-aware ranked memory set. Skills
whose triggers/description overlap with the dominant tags in that
recall result get a boost.

### Concrete: a "project boost" rule for Layer 0.5

The existing 25 hand-written rules are static. Add one synthetic rule
that's regenerated per project from bank data:

```ts
// pseudocode for Layer 0.5
const bankTags = await hindsight.recall(bankId, prompt, { budget: 'low' })
                                  .then(r => topTags(r.results, 20));

for (const tag of bankTags) {
  if (tag.startsWith('file:') || tag.startsWith('module:')) {
    for (const skill of skills) {
      if (skill.triggers.some(t => tag.includes(t))) {
        boost(skill.name, tagWeight(tag));   // proportional to tag count
      }
    }
  }
}
```

Effect: skills that are *associated with the files being worked on in
this project* get up-weighted. The current global L0.5 rules say "if
the prompt mentions `bun`, boost `bun-toolchain`." The new project
boost rule says "if 40% of recent memories in this bank touch
`cli/src/commands/skills/`, boost skills whose triggers include
`skills` or `suggester` or `cli`."

### Cost vs L0.5 baseline

L0.5 today: <10 ms (regex + dict lookup).
Project-boost: bank recall is 10–50 ms localhost. Too expensive for
every prompt.

Mitigation: cache the project's top tags daily (per-bank, in
`~/.cache/review-with-memory/project-tags-<repo>.json`). Refresh in
background. Rule lookup at suggest time stays at L0.5 latency. Tag
refresh runs async post-call.

### What this gains

The eval corpus today is project-agnostic so it can't directly score
this. A *new* corpus is needed: same 25 prompts, but evaluated against
3–5 different project banks, with expected results that differ per
project. Hindsight should improve the per-project eval; it should not
change the global eval.

## Tier 2: usage learning

The current memory is hash-recall — a cache, not learning. Hindsight
retain after each suggest call lets you record:

- prompt → suggestions returned
- which suggestion the user actually installed/used (slash-command path
  makes this trivial; `/remember` and `/recall` already retain to the
  same bank)
- explicit dismissals (would need a lightweight UX hook — e.g. a
  `toolbelt skills dismiss <name>` command that retains
  `negative-feedback:dismissed`)

Recall + reflect can then power a **co-occurrence reranker**:

> In project P, when a prompt with shape Q arrives, skill X has been
> installed-after-suggestion 12 times and skill Y zero times. Boost X.

This is lossy in the first weeks (no signal yet) and compounding over
months. The slope of improvement is the value, not the day-1 score.

### Schema for usage retains

```json
{
  "content": "User asked: <prompt>. Suggested: [skillA, skillB, skillC]. Installed: skillA.",
  "context": "skill-suggest-call",
  "tags": [
    "repo:<name>",
    "source:suggester",
    "prompt-hash:<sha8>",
    "outcome:installed:skillA",
    "suggested:skillA",
    "suggested:skillB",
    "suggested:skillC"
  ],
  "metadata": {
    "prompt_hash": "...",
    "kwConf": 0.41,
    "embConf": 0.58,
    "layer": "L1"
  }
}
```

Recall over `tags=["repo:X", "source:suggester", "outcome:installed:*"]`
yields the project's positive history. Reflect over the same yields a
synthesis of "what works in this project."

## Tier 3: semantic prompt recall

Today's memory is exact-hash. Hindsight's bank-side embeddings + cross-
encoder rerank handle paraphrases natively. "Help me bump the version"
and "I need to ship a release" hash differently but recall the same
memories.

This raises cache hit rate from ~exact-match to ~semantic-match. The
practical effect: more L2/L3 cache hits, fewer cold-path executions.

This is the smallest of the three tiers — it's a quality-of-life win,
not a fundamental capability change.

## What Hindsight should NOT replace

| Current layer | Why Hindsight is wrong for it |
|---------------|-------------------------------|
| L0 keyword matcher | Hindsight has no concept of skill triggers/names; the matcher's stemmer + weak-token + negation logic is bespoke and tuned. Don't replace. |
| L1 Chroma + fastembed | The catalog is static and small (294 skills, ~75k tokens total). Chroma's HNSW is correct here. Hindsight's strength is *learning*, which a static catalog doesn't need. |
| L2/L3 local GGUF | These exist specifically to keep things no-cloud and deterministic. Hindsight goes through the configured LLM provider (currently Fireworks/Kimi). Wrong tool. |

## Proposed architecture

```
prompt
  │
  ├─► L0 (kw)                         <10ms   always
  ├─► L0.5 (rules + project-boost)    <10ms   always (project tags cached)
  │
  ├─► confidence ≥ 0.55? ─────────────────► return matches + RETAIN
  │
  │       no
  │       ▼
  ├─► L0.7 Hindsight                  10–50ms  if --deep or daemon up
  │     ├─ semantic prompt recall against bank
  │     └─ usage-history co-occurrence rerank
  │
  ├─► L1 (Chroma)                     <30ms   if --deep
  ├─► L2/L3 (local LLM)               async   if L1 ambiguous
  │
  └─► after-call: client.retain({prompt, suggestions, project, ts, tags})
```

Two new things, both optional:

1. **L0.7** — fires only when L0+L0.5 confidence is below the existing
   uncertainty threshold (0.55). Hot path is unchanged for the 92% of
   FAST prompts that already clear the threshold.
2. **Retain hook** — fires on every suggest call (any layer). Async,
   detached, never blocks the synchronous return.

### Daemon vs CLI placement

The bank lookup happens daemon-side. The daemon (`toolbelt skills
serve`) already manages Chroma; adding an HTTP client to Hindsight
on `:8888` is one fetch call. CLI callers stay stateless.

This couples the daemon to Hindsight uptime. Mitigation: same fail-open
pattern as Chroma — if Hindsight is unreachable, the daemon falls
through to L0+L0.5+L1 only and reports `hindsight: down` in `/health`.

### Retain shape

Retain happens regardless of which layer answered:

```ts
await fetch(`${HINDSIGHT_URL}/retain`, {
  method: 'POST',
  body: JSON.stringify({
    bank_id: `${prefix}-::${repo}`,
    content: `Suggester(${layer}): "${prompt}" → ${matches.map(m => m.name).join(', ')}`,
    context: 'skill-suggest-call',
    tags: [
      `repo:${repo}`,
      'source:suggester',
      `layer:${layer}`,
      `kw:${conf.kw.toFixed(2)}`,
      ...matches.map(m => `suggested:${m.name}`)
    ],
    document_id: `suggest-${promptHash}-${Date.now()}`
  })
});
```

Retain is fire-and-forget — the suggester does not await. If the call
fails, the suggester logs and moves on. No user-visible failure mode.

## Latency budget

| Call shape | Today | With Hindsight |
|------------|------:|---------------:|
| FAST hot path (conf ≥ 0.55, ~92% of prompts) | <10 ms | <10 ms (unchanged) |
| FAST cold (conf < 0.55) | <10 ms | <60 ms (Hindsight recall) |
| DEEP hot path | <30 ms | <30 ms (unchanged) |
| DEEP cold | <30 ms | <80 ms |
| Retain after-call | — | 0 ms (async, detached) |

The hot path stays in budget because Hindsight is gated on confidence.
The 4–8% cold-path budget grows by 30–50 ms; this is the cohort where
the existing system has weak guesses anyway, so the latency is well
spent.

## Cost

Hindsight retain calls Fireworks/Kimi for fact extraction. At observed
rates from this session:

- ~2.7k input tokens + ~0.3k output tokens per retain
- Fireworks Kimi pricing (current): ~$0.00X per call
- Estimated 200 suggest calls/day → ~$0.X / day per developer

Recall is free (no LLM). Reflect is opt-in.

Compared to today's cost (zero), this is a real change. But the
Hindsight server is already running for the conversation/CRG/git
streams. Marginal cost is just the additional retains.

## Risks and mitigations

### R1: Catalog drift (skill renamed/removed → stale recalls)

A retain that mentions skill `foo-bar` will keep returning that name
even after the skill is removed.

Mitigation: on `toolbelt skills reindex`, delete memories tagged with
`suggested:<name>` for any name no longer in the index. Two-line cron
or post-reindex hook.

### R2: Privacy boundary shift

Today's NDJSON memory stays local. Hindsight retains send content to
the configured LLM provider for fact extraction. The Fireworks endpoint
sees prompts + skill names, but never source code (the content is just
the prompt + suggestions metadata).

Mitigation: explicit setting `HINDSIGHT_SUGGESTER_RETAIN=false` in
`~/.hindsight/claude-code.json` to opt out of the suggester retain
stream while keeping conversation/CRG retains. Independent toggle.

### R3: Dependency on Hindsight uptime

If the Docker container is down, the daemon should fail open to the
existing pipeline. Already specced. Need to verify under intermittent
network conditions (e.g. macOS sleep/wake).

### R4: Bias toward popular skills (rich-get-richer)

Co-occurrence reranking will boost skills that have been installed
frequently. Skills that *should* be suggested but rarely are will stay
suppressed.

Mitigation: cap the usage-learning boost (e.g. max +3 from history),
floor it on rarely-used-but-relevant skills via Tier 1 project signal.

### R5: Bank size growth

If every suggest call retains, banks grow indefinitely. With 200
suggest calls/day per developer × N developers, banks can hit gigabytes
of extracted facts in months.

Mitigation: Hindsight has document_id upsert semantics. Use
`document_id=suggest-<prompt_hash>` so repeated identical prompts
upsert rather than append. Add a quarterly prune job that drops
suggester memories older than 90 days unless they have a `useful`
outcome tag.

## Migration plan

Phased rollout, behind a feature flag (`HINDSIGHT_SUGGESTER_ENABLED`,
default off):

### Phase 0 — Already done

- Hindsight server running on `:8888` with Fireworks/Kimi
- Per-project banks populated from chat/CRG/git/test/manual streams
- Mental models on hub nodes auto-refreshing
- Bridge scripts (retain/recall/reflect) available

### Phase 1 — Retain on every suggest call (1 week to bake)

- Add `client.retain` after-call in `suggest.ts`, fire-and-forget
- Tag with prompt-hash, repo, suggestions, layer, scores
- Default off; opt in via env flag for early users
- Goal: get retain volume up so Tier 1 has something to recall against

### Phase 2 — Project-boost rule in L0.5 (2–3 weeks)

- Add daily background job: per-project tag aggregation,
  cache to `~/.cache/review-with-memory/project-tags-<repo>.json`
- Add new context rule that reads cached tags and applies boosts
- Run new "per-project eval corpus" alongside existing 25-probe corpus
- Rollout: opt-in via `--project-aware` flag, then default on

### Phase 3 — L0.7 Hindsight recall slot (4 weeks)

- Daemon: add `POST /match` path that calls `client.recall` when
  `kwConf < 0.55`, blends with kw scores using same calibration as L1
- Veto pattern: if Hindsight returns nothing, defer to L1 unchanged
- Run extended eval; expect FAST cold-path improvement specifically

### Phase 4 — Usage-learning reranker (8 weeks)

- Add `toolbelt skills install` hook that retains `outcome:installed:X`
- Add `toolbelt skills dismiss X` command for explicit negative
- Implement co-occurrence rerank in daemon `/match` post-process
- Soft-launch with capped boost; raise cap as data accrues

Each phase is independent and reversible by toggling the env flag. No
phase requires committing to the next.

## Eval methodology

The current 25-probe corpus measures global catalog matching. To eval
Hindsight, two new corpus shapes:

### Project-aware corpus (new)

Same prompts, multiple expected answers depending on project. Example:

```json
{
  "id": "P12",
  "prompt": "fix the login flow",
  "per_project_expected": {
    "kh-::stripe-payments": ["stripe-best-practices", "two-factor-authentication-best-practices"],
    "kh-::coding-toolbelt": ["create-auth-skill"],
    "kh-::xyz-frontend": ["better-auth-setup", "frontend-patterns"]
  }
}
```

Score by per-project hit rate. Hindsight should make this number go up
without dragging the global score down.

### Usage-learning corpus (synthetic, longitudinal)

Run identical sessions against a clean Hindsight bank, retain
`outcome:installed:<X>` for known-correct answers. After N sessions,
re-run the eval — measure whether the suggester now returns X first
for prompts where it previously returned X-or-Y.

Pass condition: after 50 simulated installs of skill X for prompts of
shape Q, X should rank ≥1 position higher than baseline for new
prompts of shape Q.

### Latency budget verification

P50 / P95 / P99 latency on the existing corpus, before and after
Hindsight enablement, broken down by which layer answered. Expected:

- P50 unchanged (hot path bypasses Hindsight)
- P95 +30–50 ms (cold path now hits Hindsight)
- P99 unchanged or improved (L2/L3 fallthrough rate should drop)

### Cost dashboard

Per-day Fireworks token spend on retain calls, plotted alongside
suggest-call volume. Alert if cost-per-call spikes (might indicate
content explosion or prompt regression).

## Tier 4 (speculative — only consider after Phases 1–4 work)

These are downstream extensions enabled by the same infrastructure but
out of scope for the initial integration:

- **Skill biographies as mental models.** For each skill in the index,
  define a Hindsight Mental Model with `source_query="scenarios that
  call for this skill, common pitfalls, frequently confused with X"`.
  Auto-refreshes from bank usage. Skill descriptions become living.
- **Cross-skill bundles.** Hindsight learns "users who installed X
  also installed Y." Suggester ranks bundles, not just individuals.
- **Negative learning.** Track explicit dismissals; dampen suggestion
  weight on dismissed skills per-user.
- **Reflection-driven gap detection.** Weekly reflect on each project
  bank with `query="what kinds of work has happened that no skill
  helped with?"`. Outputs feed into `skill-sync`'s gap detection.
- **Project onboarding.** When `cd`'ing into a new project (with
  `.git` + manifest), pre-warm by querying Hindsight for skills used
  in semantically-similar projects.

## Recommendation

Proceed with Phase 1 (retain hook only, default off). Cost is near-zero
for both effort and runtime. After 1–2 weeks of retain volume across
active projects, evaluate whether Phase 2 (project-boost) shows lift on
a project-aware corpus.

Do not commit to Phases 3–4 until Phase 2 proves the project-signal
hypothesis. If project-boost doesn't move the needle, the rest is
unlikely to either.

The most-valuable single experiment: a per-project eval corpus.
Without it, there's no way to measure whether Hindsight is doing its
intended job, because the global corpus is project-agnostic by
construction.

## Open questions

1. **Retain UX**: should retains be visible to the user
   (`[hindsight] retained suggester call`) or fully invisible? Lean
   invisible until users complain about the silence.
2. **Per-user vs per-machine bank ID**: today the prefix is hardcoded
   `kh`. For multi-user dev environments, prefix should include
   `$USER` or a config-driven identity.
3. **Synchronous fallback for retain**: if Hindsight is briefly down,
   should the suggester buffer retains and replay later? Marginal
   value, real complexity. Default: drop on the floor.
4. **Cross-repo recall**: should "fix the login flow" in a fresh repo
   recall from sibling repos with similar structure? Probably yes,
   gated on opt-in. CRG's `cross_repo_search_tool` is the natural
   companion.
5. **Tag taxonomy enforcement**: as more retain streams come online,
   tags will diverge across streams (some use `file:`, some use
   `path:`, some use `node:`). Need a canonical tag schema and a
   linter that flags drift.

## References

- [`skill-suggest-layers.md`](./skill-suggest-layers.md) — main spec
- [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight)
- [LongMemEval benchmark](https://arxiv.org/abs/2410.10813) — Hindsight's reported SOTA
- `~/Coding/Tooling/coding-toolbelt/review-with-memory/` — local glue,
  Hindsight server, bridges, slash commands; pushed to
  [github.com/kivo360/coding-toolbelt](https://github.com/kivo360/coding-toolbelt)
- `~/.hindsight/claude-code.json` — Hindsight Claude Code plugin config
  (bank prefix, dynamic bank ID, debug mode)
