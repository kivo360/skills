/**
 * Layered (hybrid) skill matcher.
 *
 * Layer 0  — keyword score from `matcher.ts`
 * Layer 0.5 — context-rule boosts (paths, tool mentions, domain hints)
 * Layer 1  — embedding cosine similarity (only when keyword is uncertain)
 *
 * Decision flow:
 *   1. tokenize → keyword scores
 *   2. apply context boosts (cheap, always on)
 *   3. compute confidence; if best < threshold AND embeddings are
 *      available AND deep mode is enabled, run embedding lookup and
 *      blend the two signals
 *   4. apply family-orchestrator boost (existing rule)
 *   5. sort, slice, return
 *
 * Embedding work is opt-in via `deep: true` because the model load
 * is ~500 ms warm / ~5 s cold and we never want that on the
 * UserPromptSubmit hot path.
 */

import type { SkillEntry, SkillsIndex, SuggestMatch } from "../types";
import { findMatches, matchScore, tokenize, detectNegatedTokens } from "./matcher";
import { applyContextRules, loadProjectBoosts } from "./context-rules";
import { FAMILY_ORCHESTRATORS } from "./synonyms";
import {
  loadEmbeddings,
  embedQuery,
  cosineSim,
  type EmbeddingsIndex,
} from "./embeddings";
import type { ChromaSkillStore } from "./chroma-store";

/**
 * A skill is "negation-tainted" when a prompt-negated token appears in
 * its name or its top triggers. We use this to drop semantic/embedding
 * matches that would otherwise sneak through (e.g. "I'm not using
 * stripe" matching stripe-best-practices on the trigger "checkout").
 */
function isNegationTainted(skill: SkillEntry, negated: Set<string>): boolean {
  if (negated.size === 0) return false;
  for (const t of tokenize(skill.name)) {
    if (negated.has(t)) return true;
  }
  for (const trig of skill.triggers.slice(0, 12)) {
    for (const t of tokenize(trig)) {
      if (negated.has(t)) return true;
    }
  }
  return false;
}

export interface HybridOpts {
  minScore?: number;
  minConfidence?: number;
  limit?: number;
  tiers?: Set<string>;
  requireNameOrTrigger?: boolean;
  /** Run embedding fallback when keyword confidence is low. */
  deep?: boolean;
  /** Pre-loaded embeddings (avoids re-reading the JSON file). */
  embeddings?: EmbeddingsIndex | null;
  /**
   * Connected Chroma store. When supplied AND `deep` is true, the
   * top-K cosine search uses Chroma's HNSW index instead of looping
   * over `embeddings`. The two paths produce equivalent confidence
   * scores — Chroma is just faster at scale.
   */
  chromaStore?: ChromaSkillStore;
  /** Cosine similarity below this is treated as no match. */
  embeddingFloor?: number;
  /** Cosine similarity above this is treated as full confidence. */
  embeddingCeiling?: number;
  /** Best keyword confidence below this triggers Layer 1. */
  uncertaintyThreshold?: number;
  /** Weight for keyword vs embedding in blend (kw share). */
  keywordWeight?: number;
  /** Top-K to fetch from the embedding source (default 20). */
  embeddingTopK?: number;
}

export interface HybridResult {
  matches: SuggestMatch[];
  layers: { keyword: boolean; context: boolean; embedding: boolean };
  stats: {
    kwBest: number;
    contextBoosts: number;
    embBest: number;
    embSource: "chroma" | "json" | "none";
    triggered: "keyword" | "context" | "embedding";
  };
}

/**
 * Convert a fused score (keyword points + context boost) into a 0..1
 * confidence. The keyword scale is 0..30 (exact name); context boosts
 * are usually 4..10. We cap at 36 so context boosts never saturate the
 * scale on their own without keyword grounding.
 */
function fusedConfidence(rawScore: number): number {
  return Math.min(1, rawScore / 30);
}

/**
 * Calibrate cosine similarity into a 0..1 confidence, treating
 * everything below `floor` as zero and everything above `ceiling` as
 * full. all-MiniLM-L6-v2 short-text similarity rarely exceeds 0.85,
 * and irrelevant pairs sit around 0.25–0.35, so the default window
 * (0.35..0.80) reflects what "useful" looks like in practice.
 */
function embeddingConfidence(cos: number, floor: number, ceiling: number): number {
  if (cos <= floor) return 0;
  if (cos >= ceiling) return 1;
  return (cos - floor) / (ceiling - floor);
}

export async function findMatchesHybrid(
  index: SkillsIndex,
  query: string,
  opts: HybridOpts = {}
): Promise<HybridResult> {
  const minScore = opts.minScore ?? 8;
  const minConf = opts.minConfidence ?? 0.4;
  const limit = opts.limit ?? 10;
  const requireNameOrTrigger = opts.requireNameOrTrigger ?? true;
  const uncertaintyThreshold = opts.uncertaintyThreshold ?? 0.55;
  const kwWeight = opts.keywordWeight ?? 0.6;
  // Floor raised from 0.35 to 0.45: short-text MiniLM cosine sits in
  // the 0.30–0.45 band for "vaguely related" pairs; treating those as
  // matches surfaces noise on no-signal prompts ("today is a nice day"
  // matched a design skill at cos 0.41). 0.45 is the empirical knee.
  const embFloor = opts.embeddingFloor ?? 0.45;
  const embCeiling = opts.embeddingCeiling ?? 0.8;

  // ── Layer 0 — keyword matcher ───────────────────────────────────
  const kwTokens = tokenize(query, { withSynonyms: true });
  const negated = detectNegatedTokens(query);

  const validNames = new Set(Object.keys(index.skills));
  // Phase 2 / Tier 1: project-aware boost from the current repo's
  // Hindsight bank. Returns empty when the env flag is off or no
  // cache exists, so the hot path is unchanged in that case.
  const projectBoosts = loadProjectBoosts(index.skills);
  const { boosts: contextBoosts, reasons: contextReasons } = applyContextRules(
    query,
    validNames,
    negated,
    projectBoosts
  );

  // Build the fused score table directly so context boosts compose
  // with keyword scores and feed family-orchestrator detection.
  const fused = new Map<
    string,
    { score: number; matched: Set<string>; hasNameOrTrigger: boolean }
  >();

  for (const [name, skill] of Object.entries(index.skills)) {
    if (opts.tiers && !opts.tiers.has(skill.tier)) continue;
    const { score, matched, hasNameOrTrigger } = matchScore(
      skill,
      kwTokens,
      negated
    );
    let total = score;
    const mset = new Set(matched);
    const boost = contextBoosts[name];
    if (boost) {
      total += boost;
      mset.add(`<context>`);
    }
    if (total < minScore) continue;
    // require either keyword anchor OR a context-rule reason
    if (requireNameOrTrigger && !hasNameOrTrigger && !boost) continue;
    fused.set(name, { score: total, matched: mset, hasNameOrTrigger: hasNameOrTrigger || !!boost });
  }

  let kwBest = 0;
  for (const v of fused.values()) {
    const c = fusedConfidence(v.score);
    if (c > kwBest) kwBest = c;
  }

  // ── Layer 1 — embedding fallback ────────────────────────────────
  // In `deep` mode we always embed: even when keyword confidence is
  // high we want the cosine signal to act as a veto on word-collision
  // false positives (e.g. "subscription churn flows" anchoring on
  // kotlin-coroutines-flows via the "flows" token). When keyword is
  // weak, embeddings supply the signal directly.
  //
  // Source priority: Chroma (HNSW, scale-friendly) → JSON (linear
  // cosine, 295-skill scale fine). Both produce the same cos values
  // so the downstream blend math is identical.
  let embBest = 0;
  let embRan = false;
  let embSource: "chroma" | "json" | "none" = "none";
  let embTopByName = new Map<string, number>();
  if (opts.deep) {
    const queryVec = await embedQuery(query);
    const topK = opts.embeddingTopK ?? 20;

    if (opts.chromaStore) {
      try {
        const tiersArr = opts.tiers ? [...opts.tiers] : undefined;
        const hits = await opts.chromaStore.query(queryVec, topK, { tiers: tiersArr });
        for (const hit of hits) {
          const skill = index.skills[hit.name];
          if (!skill) continue;
          embTopByName.set(hit.name, hit.cosine);
          if (hit.cosine < embFloor) continue;
          const conf = embeddingConfidence(hit.cosine, embFloor, embCeiling);
          if (conf > embBest) embBest = conf;
        }
        embRan = true;
        embSource = "chroma";
      } catch {
        // Chroma RPC failed mid-query — fall through to JSON below.
      }
    }

    if (!embRan) {
      const emb = opts.embeddings ?? (await loadEmbeddings());
      if (emb) {
        embRan = true;
        embSource = "json";
        for (const [name, sv] of Object.entries(emb.skills)) {
          const skill = index.skills[name];
          if (!skill) continue;
          if (opts.tiers && !opts.tiers.has(skill.tier)) continue;
          const cos = cosineSim(queryVec, sv.vector);
          embTopByName.set(name, cos);
          if (cos < embFloor) continue;
          const conf = embeddingConfidence(cos, embFloor, embCeiling);
          if (conf > embBest) embBest = conf;
        }
      }
    }
  }
  // Reference uncertaintyThreshold to avoid an unused-variable lint
  // error; the value is still informative for callers via stats.
  void uncertaintyThreshold;

  // ── Combine ────────────────────────────────────────────────────
  const allNames = new Set<string>([...fused.keys(), ...embTopByName.keys()]);
  const out: SuggestMatch[] = [];

  for (const name of allNames) {
    const skill = index.skills[name];
    if (!skill) continue;
    // Cross-layer negation: drop skills whose name/triggers intersect
    // negated tokens. Keyword matcher already enforces this on its own
    // pass, but embeddings and context rules can both pull a tainted
    // skill back in via semantic similarity or unrelated boosts.
    if (isNegationTainted(skill, negated)) continue;

    const kwEntry = fused.get(name);
    const kwConf = kwEntry ? fusedConfidence(kwEntry.score) : 0;
    const cos = embTopByName.get(name) ?? 0;
    const embConf = embRan ? embeddingConfidence(cos, embFloor, embCeiling) : 0;

    let confidence: number;
    let matched: string[];

    if (embRan && (kwConf > 0 || embConf > 0)) {
      // Veto rule: if keyword is high but embedding strongly disagrees
      // (cos < embFloor, i.e. not even semantically near), downgrade
      // the keyword confidence rather than blending. Keeps name-token
      // collisions from dominating a clearly off-topic prompt.
      if (kwConf > 0.6 && cos < embFloor) {
        confidence = kwConf * 0.55;
        matched = [
          ...(kwEntry ? [...kwEntry.matched] : []),
          `<emb-veto:${cos.toFixed(2)}>`,
        ];
      } else {
        confidence = kwWeight * kwConf + (1 - kwWeight) * embConf;
        matched = [
          ...(kwEntry ? [...kwEntry.matched] : []),
          ...(embConf > 0 ? [`<emb:${cos.toFixed(2)}>`] : []),
        ];
      }
    } else {
      confidence = kwConf;
      matched = kwEntry ? [...kwEntry.matched] : [];
    }

    // Embedding-only matches (no kw, no context) need to clear a
    // higher bar to protect against semantic noise — a tepid cosine
    // (0.45–0.55) on a vague prompt is exactly the FP shape we want
    // to reject.
    const embeddingOnly = !kwEntry && !contextBoosts[name];
    const effectiveFloor = embeddingOnly ? Math.max(minConf, 0.55) : minConf;
    if (confidence < effectiveFloor) continue;

    out.push({
      name,
      tier: skill.tier,
      description: skill.description,
      confidence: Math.min(1, confidence),
      matched,
      installedPath: skill.installedPath,
    });
  }

  applyFamilyOrchestratorBoostInline(out, index, opts.tiers);
  out.sort((a, b) => b.confidence - a.confidence || a.name.localeCompare(b.name));

  const triggered: HybridResult["stats"]["triggered"] =
    embRan && embBest > kwBest
      ? "embedding"
      : Object.keys(contextBoosts).length > 0 && kwBest > 0
        ? "context"
        : "keyword";

  return {
    matches: out.slice(0, limit),
    layers: {
      keyword: true,
      context: contextReasons.length > 0,
      embedding: embRan,
    },
    stats: {
      kwBest,
      contextBoosts: Object.keys(contextBoosts).length,
      embBest,
      embSource,
      triggered,
    },
  };
}

/**
 * Mirror of the matcher's family-orchestrator promotion: when the
 * result set already contains 2+ siblings of a family, also surface
 * the orchestrator at boosted confidence.
 */
function applyFamilyOrchestratorBoostInline(
  matches: SuggestMatch[],
  index: SkillsIndex,
  tiers?: Set<string>
): void {
  const familyHits = new Map<string, number>();
  for (const m of matches) {
    for (const prefix of Object.keys(FAMILY_ORCHESTRATORS)) {
      if (m.name === FAMILY_ORCHESTRATORS[prefix]) continue;
      if (m.name === prefix || m.name.startsWith(prefix + "-")) {
        familyHits.set(prefix, (familyHits.get(prefix) ?? 0) + 1);
        break;
      }
    }
  }
  for (const [prefix, count] of familyHits) {
    if (count < 2) continue;
    const orchestrator = FAMILY_ORCHESTRATORS[prefix];
    if (matches.some((m) => m.name === orchestrator)) continue;
    const skill = index.skills[orchestrator];
    if (!skill) continue;
    if (tiers && !tiers.has(skill.tier)) continue;
    matches.push({
      name: orchestrator,
      tier: skill.tier,
      description: skill.description,
      confidence: Math.min(0.85, 0.5 + count * 0.1),
      matched: [`<${prefix}-family>`],
      installedPath: skill.installedPath,
    });
  }
}

/**
 * Convenience wrapper that mirrors the existing `findMatches` shape
 * for places that just want "best matches, hybrid pipeline".
 */
export async function findMatchesLayered(
  index: SkillsIndex,
  query: string,
  opts: HybridOpts = {}
): Promise<SuggestMatch[]> {
  const r = await findMatchesHybrid(index, query, opts);
  return r.matches;
}

// Re-export the original keyword matcher so callers can pick a tier.
export { findMatches };
