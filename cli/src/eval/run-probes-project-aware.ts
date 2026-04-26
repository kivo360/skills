#!/usr/bin/env bun
/**
 * Eval harness for the project-aware probe corpus.
 *
 * For each probe, runs the suggester twice — once with the project-boost
 * rule disabled (baseline), once enabled — and reports whether any of
 * the expected skills for the active bank appear in the top-3 results.
 *
 * Currently exercises a single bank at a time (the env's current repo).
 * Multi-bank eval requires multiple populated Hindsight banks; until
 * then, run from inside each project to score that bank.
 *
 * Usage:
 *   HINDSIGHT_PROJECT_BOOST_ENABLED=0 bun src/eval/run-probes-project-aware.ts
 *   HINDSIGHT_PROJECT_BOOST_ENABLED=1 bun src/eval/run-probes-project-aware.ts
 *   bun src/eval/run-probes-project-aware.ts --ab     # runs both, prints diff
 *   bun src/eval/run-probes-project-aware.ts --json
 *
 * Pass condition (per spec in docs/highlight-memory-evaluation.md):
 *   With boost ON, mean per-bank hit rate >= 0.7 AND no bank's hit rate
 *   regresses below the boost-OFF baseline.
 */

import { readIndex } from "../lib/index-store";
import { findMatchesHybrid } from "../lib/hybrid-matcher";
import { _resetProjectBoostsCacheForTest } from "../lib/context-rules";
import { execFileSync } from "node:child_process";
import { basename } from "node:path";
import probesFile from "./probes-project-aware.json" with { type: "json" };

interface ProbeJson {
  id: string;
  prompt: string;
  expected_per_bank: Record<string, string[]>;
  rationale?: string;
}

const probes = (probesFile as { probes: ProbeJson[] }).probes;
const ab = process.argv.includes("--ab");
const wantJson = process.argv.includes("--json");

function currentBank(): string {
  const prefix = process.env.HINDSIGHT_BANK_PREFIX || "kh";
  try {
    const root = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
    return `${prefix}-::${basename(root)}`;
  } catch {
    return `${prefix}-::scratch`;
  }
}

const index = await readIndex();
if (!index) {
  console.error("No skills index. Run `toolbelt skills reindex` first.");
  process.exit(1);
}

const bank = currentBank();
console.error(`bank: ${bank}`);

interface ProbeOutcome {
  id: string;
  prompt: string;
  expected: string[];
  top: { name: string; conf: number }[];
  hit: boolean;
  hitName: string | null;
}

async function runProbe(probe: ProbeJson, boostOn: boolean): Promise<ProbeOutcome> {
  if (boostOn) {
    process.env.HINDSIGHT_PROJECT_BOOST_ENABLED = "1";
  } else {
    delete process.env.HINDSIGHT_PROJECT_BOOST_ENABLED;
  }
  _resetProjectBoostsCacheForTest();

  const expected: string[] =
    probe.expected_per_bank[bank] ??
    probe.expected_per_bank["__any__"] ??
    [];

  const result = await findMatchesHybrid(index!, probe.prompt, {
    minScore: 8,
    minConfidence: 0.3, // slightly relaxed for project-boost-only matches
    limit: 3,
    requireNameOrTrigger: true,
    deep: false,
  });

  const top = result.matches
    .slice(0, 3)
    .map((m) => ({ name: m.name, conf: m.confidence }));
  const hitName = expected.find((exp) => top.some((t) => t.name === exp)) ?? null;
  return { id: probe.id, prompt: probe.prompt, expected, top, hit: !!hitName, hitName };
}

async function runAll(boostOn: boolean): Promise<ProbeOutcome[]> {
  const results: ProbeOutcome[] = [];
  for (const p of probes) {
    results.push(await runProbe(p, boostOn));
  }
  return results;
}

function summarize(label: string, outcomes: ProbeOutcome[]): { hits: number; total: number; rate: number } {
  const total = outcomes.length;
  const hits = outcomes.filter((o) => o.hit).length;
  const rate = total > 0 ? hits / total : 0;
  if (!wantJson) {
    console.log(`\n${label}  ${hits}/${total} hits  (${(rate * 100).toFixed(0)}%)`);
    for (const o of outcomes) {
      const mark = o.hit ? "✅" : o.expected.length === 0 ? "·" : "❌";
      const got = o.top.map((t) => `${t.name}(${(t.conf * 100).toFixed(0)})`).join(", ") || "(none)";
      const exp = o.expected.length > 0 ? `expected: [${o.expected.join(", ")}]` : "no expected for this bank";
      console.log(`  ${mark} ${o.id}  "${o.prompt}"`);
      console.log(`     got: ${got}`);
      console.log(`     ${exp}`);
    }
  }
  return { hits, total, rate };
}

if (ab) {
  console.error("running A/B (baseline → with-boost)");
  const baseline = await runAll(false);
  const withBoost = await runAll(true);

  const baseSum = summarize("BASELINE (boost OFF)", baseline);
  const boostSum = summarize("WITH PROJECT BOOST (ON)", withBoost);

  console.log(
    `\nDelta: ${(baseSum.rate * 100).toFixed(0)}% → ${(boostSum.rate * 100).toFixed(0)}% (${boostSum.hits - baseSum.hits >= 0 ? "+" : ""}${boostSum.hits - baseSum.hits} probes)`
  );
  if (wantJson) {
    console.log(JSON.stringify({ bank, baseline: baseSum, with_boost: boostSum }, null, 2));
  }
} else {
  const boostOn = process.env.HINDSIGHT_PROJECT_BOOST_ENABLED === "1";
  const outcomes = await runAll(boostOn);
  const sum = summarize(boostOn ? "WITH BOOST" : "BASELINE", outcomes);
  if (wantJson) {
    console.log(JSON.stringify({ bank, boost_on: boostOn, ...sum, outcomes }, null, 2));
  }
}
