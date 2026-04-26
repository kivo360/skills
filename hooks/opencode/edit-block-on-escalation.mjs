#!/usr/bin/env node

/**
 * Edit Block on Escalation — PreToolUse Hook
 *
 * PreToolUse hook that BLOCKS editing on files that have triggered Tier 3+ escalation.
 * This provides TRUE enforcement — the agent cannot keep editing the same failing file.
 *
 * How it works:
 *   - Fires BEFORE the Edit tool executes
 *   - Reads linter state from /tmp/omo-linter-state/{session_id}.json
 *   - If consecutiveMatches >= HARD_THRESHOLD AND file matches lastFile:
 *       - Exit with code 2 (BLOCK)
 *       - Write blocking message to stderr
 *   - Otherwise, exit 0 (ALLOW)
 *
 * Block lifts when:
 *   - Different error appears (progress made)
 *   - Clean output detected (error resolved)
 *   - Cooldown expires
 *   - Different file is being edited
 *
 * Exit codes:
 *   0 = ALLOW (tool proceeds)
 *   2 = BLOCK (stderr message shown to agent, tool does NOT execute)
 *
 * Environment variables (same as linter-loop-escalation.mjs):
 *   OMA_HARD_THRESHOLD (default: 3)
 *   OMA_STALE_MINUTES (default: 5)
 *   OMA_COOLDOWN_MINUTES (default: 2)
 *   OMA_COOLDOWN_NUCLEAR_MINUTES (default: 3)
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const STATE_DIR = "/tmp/omo-linter-state";
const HARD_THRESHOLD = parseInt(process.env.OMA_HARD_THRESHOLD, 10) || 3;
const STALE_MS = (parseFloat(process.env.OMA_STALE_MINUTES) || 5) * 60 * 1000;
const COOLDOWN_HARD_MS = (parseInt(process.env.OMA_COOLDOWN_MINUTES, 10) || 2) * 60 * 1000;
const COOLDOWN_NUCLEAR_MS = (parseInt(process.env.OMA_COOLDOWN_NUCLEAR_MINUTES, 10) || 3) * 60 * 1000;

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => {
      resolve(data);
    });
  });
}

function getState(sessionId) {
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  try {
    if (existsSync(stateFile)) {
      return JSON.parse(readFileSync(stateFile, "utf8"));
    }
  } catch {
    // Corrupted or missing
  }
  return null;
}

async function main() {
  const raw = await readStdin();

  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0); // Fail open — allow on parse error
  }

  const toolName = (input.tool_name || "").toLowerCase();

  // Only block Edit tool
  if (toolName !== "edit") {
    process.exit(0);
  }

  const sessionId = input.session_id;
  const toolInput = input.tool_input || {};
  const filePath = toolInput.filePath;

  // No file specified — allow
  if (!filePath) {
    process.exit(0);
  }

  const state = getState(sessionId);

  // No state — allow
  if (!state) {
    process.exit(0);
  }

  const now = Date.now();

  // ── Check if state is stale (too old) — allow ──
  if (state.lastTimestamp > 0 && now - state.lastTimestamp > STALE_MS) {
    process.exit(0);
  }

  // ── Check cooldown — if in cooldown period, block ──
  if (state.lastEscalationTier >= 3 && state.lastEscalationTime > 0) {
    const cooldownMs = state.lastEscalationTier >= 4 ? COOLDOWN_NUCLEAR_MS : COOLDOWN_HARD_MS;
    if (now - state.lastEscalationTime < cooldownMs) {
      const remaining = Math.round((cooldownMs - (now - state.lastEscalationTime)) / 1000);
      process.stderr.write(
        `⛔ EDIT BLOCKED — In Cooldown Period\n` +
        `You are in a ${state.lastEscalationTier >= 4 ? "NUCLEAR" : "HARD STOP"} escalation cooldown.\n` +
        `${remaining}s remaining before you can edit again.\n` +
        `\n` +
        `To proceed:\n` +
        `1. Wait for cooldown to expire\n` +
        `2. Or type: ultrawork\n` +
        `3. Or: task({ category: 'ultrabrain', prompt: 'Debug: [error] in ${state.lastFile || filePath}' })\n`
      );
      process.exit(2);
    }
  }

  // ── Check consecutive matches threshold ──
  if (state.consecutiveMatches < HARD_THRESHOLD) {
    process.exit(0);
  }

  // ── Check if the file matches the erroring file ──
  const lastFile = state.lastFile || "";
  const sameFile = lastFile === filePath || lastFile.endsWith(filePath) || filePath.endsWith(lastFile);

  if (!sameFile) {
    // Different file being edited — allow
    process.exit(0);
  }

  // ── BLOCK the edit ──
  const errorCode = state.history && state.history.length > 0
    ? state.history[state.history.length - 1].sample[0] || "unknown"
    : "unknown";

  process.stderr.write(
    `⛔ EDIT BLOCKED — Escalation Required\n` +
    `\n` +
    `You have failed ${state.consecutiveMatches} times on this file.\n` +
    `File: ${state.lastFile || filePath}\n` +
    `Last error: ${errorCode}\n` +
    `\n` +
    `You CANNOT edit this file again until you escalate.\n` +
    `\n` +
    `=== TO UNBLOCK ===\n` +
    `1. Type: ultrawork\n` +
    `   (switches to a more powerful model)\n` +
    `2. Or: task({ category: 'ultrabrain', prompt: 'Failed ${state.consecutiveMatches}x on [${errorCode}] in ${state.lastFile || filePath}. Tried: ${(state.attempts || []).slice(-3).map(a => a.summary).join(", ")}. Need fresh approach.' })\n` +
    `3. Or: task({ category: 'unspecified-high', prompt: 'Debug: [${errorCode}] in ${state.lastFile || filePath}' })\n` +
    `4. Or: ask @oracle for guidance\n` +
    `\n` +
    `After escalation, the block will lift automatically when a different model works on this file.\n`
  );

  process.exit(2);
}

main().catch(() => {
  process.exit(0); // Fail open on errors
});
