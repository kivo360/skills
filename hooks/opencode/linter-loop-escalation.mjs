#!/usr/bin/env node

/**
 * Linter Loop Escalation Hook — Bulletproof Edition
 *
 * PostToolUse hook for oh-my-openagent that detects when an agent is stuck
 * in a linter/build error loop and injects escalating guidance with explicit
 * model-switch instructions.
 *
 * Monitors:
 *   - lsp_diagnostics (TypeScript, ESLint, Python, Go, Rust, etc.)
 *   - bash (build commands: tsc, eslint, cargo, pytest, make, etc.)
 *   - Edit (same-file repeated editing detection)
 *
 * Escalation Tiers:
 *   Tier 1 (2 errors):  Soft guidance — "try fundamentally different approach"
 *   Tier 2 (3 errors):  Firm redirect — explicit task() escalation
 *   Tier 3 (4 errors):  HARD STOP — switch models NOW with ultrawork/task
 *   Tier 4 (5+ errors): NUCLEAR — consult @oracle, then follow guidance exactly
 *
 * Advanced Features:
 *   - Language-agnostic content-hash fingerprinting (any linter format)
 *   - Error severity filtering (warnings ignored, errors only)
 *   - Configurable thresholds via environment variables
 *   - Cooldown after Tier 3/4 escalation (gives escalated model time)
 *   - Resolution summary when errors clear
 *   - Ping-pong loop detection (alternating between same errors)
 *   - Cross-session error solutions (learns from previous sessions)
 *
 * State stored in: /tmp/omo-linter-state/{session_id}.json
 * Solutions stored in: ~/.config/opencode/hooks/error-solutions.json
 * Auto-resets on: clean output, different error, 5min staleness
 */

import { createHash } from "node:crypto";
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
} from "node:fs";
import { join } from "node:path";
import { appendFileSync } from "node:fs";

// ── Config ──────────────────────────────────────────────────────────
// All thresholds can be overridden via environment variables
const STATE_DIR = "/tmp/omo-linter-state";
const DEBUG_LOG = join(STATE_DIR, "hook-debug.log");
const DEBUG = process.env.OMA_HOOK_DEBUG === "1";
const SOFT_THRESHOLD = parseInt(process.env.OMA_SOFT_THRESHOLD, 10) || 2;
const HARD_THRESHOLD = parseInt(process.env.OMA_HARD_THRESHOLD, 10) || 3;
const NUCLEAR_THRESHOLD = parseInt(process.env.OMA_NUCLEAR_THRESHOLD, 10) || 5;
const STALE_MS = (parseFloat(process.env.OMA_STALE_MINUTES) || 5) * 60 * 1000;
const MAX_HISTORY = 20;
const MAX_ATTEMPTS = 10; // Max fix attempts to store
const COOLDOWN_HARD_MS = (parseInt(process.env.OMA_COOLDOWN_MINUTES, 10) || 2) * 60 * 1000;
const COOLDOWN_NUCLEAR_MS = (parseInt(process.env.OMA_COOLDOWN_NUCLEAR_MINUTES, 10) || 3) * 60 * 1000;

// Ping-pong detection (alternating between errors)
const PINGPONG_THRESHOLD = parseInt(process.env.OMA_PINGPONG_THRESHOLD, 10) || 3;
const PINGPONG_WINDOW = parseInt(process.env.OMA_PINGPONG_WINDOW, 10) || 10;

// Cross-session solutions store
const SOLUTIONS_FILE = (process.env.HOME || "/tmp") + "/.config/opencode/hooks/error-solutions.json";
const MAX_SOLUTIONS = 100;

function debugLog(msg) {
  if (!DEBUG) return;
  try {
    mkdirSync(STATE_DIR, { recursive: true });
    appendFileSync(DEBUG_LOG, `[${new Date().toISOString()}] ${msg}\n`);
  } catch {}
}

// ── Build/Lint Command Detection ────────────────────────────────────
// Commands that produce lint/build output worth monitoring
const BUILD_LINT_PATTERNS = [
  // JavaScript/TypeScript
  /\b(?:tsc|eslint|prettier|biome|oxlint)\b/,
  /\bnpm\s+run\s+(?:build|lint|check|typecheck|test)\b/,
  /\byarn\s+(?:build|lint|check|typecheck|test)\b/,
  /\bpnpm\s+(?:build|lint|check|typecheck|test|exec)\b/,
  /\bbunx?\s+(?:tsc|eslint|biome|oxlint)\b/,
  /\bnpx\s+(?:tsc|eslint|biome|oxlint)\b/,
  // Python
  /\b(?:mypy|ruff|flake8|pylint|pyright|pytest|python\s+-m\s+(?:pytest|mypy|ruff))\b/,
  // Rust
  /\b(?:cargo\s+(?:build|check|clippy|test)|rustc)\b/,
  // Go
  /\b(?:go\s+(?:build|vet|test)|golangci-lint)\b/,
  // C/C++
  /\b(?:gcc|g\+\+|clang|clang\+\+|make|cmake|ninja)\b/,
  // Java/Kotlin
  /\b(?:gradle|mvn|javac|kotlinc)\b/,
  // Ruby
  /\b(?:rubocop|ruby\s+-c)\b/,
  // Swift
  /\b(?:swiftc|swift\s+build|xcodebuild)\b/,
  // General
  /\b(?:make|cmake)\b/,
];

// ── Error Code Patterns (for DISPLAY only, not fingerprinting) ──────
// Extract specific error codes for inclusion in escalation messages.
// These do NOT affect fingerprinting — the content hash is the fingerprint.
// Adding new patterns here just improves human-readable messages.
const ERROR_CODE_PATTERNS = [
  /error (TS\d+)/g, // TypeScript: TS2345
  /error\[(E\d+)\]/g, // Rust: E0308
  /\[([\w-]+)\]\s*$/gm, // mypy/pylint: [return-value], [assignment]
  /((?:@[\w-]+\/)?[\w-]+\/[\w-]+)\s*$/gm, // ESLint: @typescript-eslint/no-explicit-any
  /\b(reportMissing\w+|reportGeneral\w+|reportOptional\w+)/g, // pyright
  /\b([A-Z]\d{3,4})\b/g, // ruff/flake8: E501, W291, F401
  /\b((?:Syntax|Type|Name|Import|Attribute|Value|Indentation|Tab)Error)/g, // Python exceptions
  /\b(undefined|cannot use|declared and not used):/g, // Go
];

// ── Helpers ─────────────────────────────────────────────────────────

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

/**
 * Strip ANSI color/escape codes from output.
 */
function stripAnsi(str) {
  // eslint-disable-next-line no-control-regex
  return str.replace(/\x1B\[[0-9;]*[mK]/g, "");
}

/**
 * Normalize a single line for content-hash fingerprinting.
 * Strips file paths, line numbers, decorators, and whitespace.
 */
function normalizeLine(line) {
  return line
    // Strip "at <location>" suffixes first (before path strip)
    .replace(/\s+at\s+\S+/g, "")
    // Strip unix file paths: /foo/bar/file.ts:10:5 or ./foo/bar/file.ts:10
    .replace(/[\w./\\-]+\.\w+:\d+(?::\d+)?/g, "")
    // Strip windows file paths: C:\foo\bar\file.ts(10,5)
    .replace(/[A-Za-z]:\\[\w\\]+\.\w+\(\d+,\d+\)/g, "")
    // Strip bare line:col numbers: 10:5 or (10,5)
    .replace(/(?:^|\s)\d+:\d+(?::\d+)?/g, "")
    .replace(/(?:^|\s)\(\d+,\d+\)/g, "")
    // Strip trailing "at" if left alone after location stripping
    .replace(/\s+at\s*$/g, "")
    // Strip arrow decorators: -->, ^^, ~~, ^^^
    .replace(/^\s*(?:-->|\^\^|~~|~~~)\s*/gm, "")
    // Strip repeated dashes/equals under headers
    .replace(/^\s*[-=]{3,}\s*$/gm, "")
    // Normalize whitespace
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Extract error codes for DISPLAY in escalation messages.
 * Does NOT affect fingerprinting — only makes messages more readable.
 */
function extractErrorCodesForDisplay(output) {
  const codes = new Set();
  for (const pattern of ERROR_CODE_PATTERNS) {
    pattern.lastIndex = 0;
    let m;
    while ((m = pattern.exec(output)) !== null) {
      if (m[1] && m[1].length > 1) codes.add(m[1]);
    }
  }
  return codes;
}

/**
 * Check if output contains error-like content (language-agnostic).
 * Used as a fallback when no specific error codes are found.
 */
function hasErrorContent(output) {
  return output.match(/error|Error|ERROR|FAIL|failed|warning|SyntaxError|TypeError/i);
}

/**
 * Check if a line is WARNING-only (no error content).
 * Lines containing "error" are always kept.
 * Lines that are ONLY warnings (no error) are filtered out.
 */
function isWarningOnlyLine(line) {
  const lower = line.toLowerCase();
  // If it contains "error" anywhere, it's not warning-only
  if (/\berror\b/i.test(line)) return false;
  // If it matches warning-only patterns
  if (/^warning\b/i.test(lower)) return true;
  if (/\bwarning:\s*/i.test(lower)) return true;
  if (/\bwarn\b/i.test(lower) && !/\berror\b/i.test(lower)) return true;
  if (/\[warning\]/i.test(lower)) return true;
  return false;
}

/**
 * Extract a fingerprint from tool output representing the "shape" of errors.
 *
 * LANGUAGE-AGNOSTIC content-hash approach:
 *   1. Strip ANSI colors
 *   2. Strip ALL file paths (unix, windows, relative, absolute)
 *   3. Strip ALL line:col numbers
 *   4. Strip timestamps and dates
 *   5. Remove blank lines
 *   6. Remove decorator lines (───, ===, ---, ^^^, ~~~)
 *   7. Sort remaining lines (so error ORDER doesn't matter)
 *   8. Hash the result
 *
 * Error codes are extracted for DISPLAY in escalation messages only.
 * The hash IS the fingerprint — same errors from different files/lines = same fingerprint.
 *
 * Returns null if output appears clean.
 */
function extractErrorFingerprint(toolName, output) {
  if (!output || typeof output !== "string") return null;

  // ── Obvious clean checks ──
  if (toolName === "lspdiagnostics" || toolName === "lsp_diagnostics") {
    if (output.includes("No diagnostics found") || output.trim() === "") {
      return null;
    }
  }

  // ── Strip ANSI colors ──
  const clean = stripAnsi(output);

  // ── Extract error codes for DISPLAY (not fingerprinting) ──
  const displayCodes = extractErrorCodesForDisplay(clean);
  const displaySample = displayCodes.size > 0
    ? [...displayCodes].sort().slice(0, 5)
    : [];

  // ── Content-hash fingerprinting (language-agnostic) ──
  const lines = clean.split("\n")
    .map(normalizeLine)
    .filter(line => line.length > 0)                    // Remove blank lines
    .filter(line => !line.match(/^[-=]{3,}$/))           // Remove decorator lines
    .filter(line => !line.match(/^\s*$/))               // Remove whitespace-only lines
    .filter(line => !isWarningOnlyLine(line))           // Filter out warning-only lines
    .sort();                                             // Sort so order doesn't matter

  // ── Warning-only check — if only warnings, treat as "ignored" not clean ──
  // This means warnings don't trigger escalation AND don't reset the counter
  if (lines.length === 0) {
    return { fingerprint: "__WARNING_ONLY__", errorCount: 0, sample: [] };
  }

  // ── Keyword check — if no display codes, check for error content ──
  if (displayCodes.size === 0 && !hasErrorContent(clean)) {
    return null; // No error codes AND no error keywords → clean
  }

  const content = lines.join("|");
  const fingerprint = createHash("md5").update(content).digest("hex").substring(0, 16);

  return {
    fingerprint,
    errorCount: lines.length,
    sample: displaySample.length > 0 ? displaySample : lines.slice(0, 3),
  };
}

/**
 * Check if a bash command is a build/lint command worth monitoring.
 * Fast-path: use known patterns. Fallback: check for error exit code + error output.
 */
function isBuildOrLintCommand(command, toolResponse) {
  if (!command || typeof command !== "string") return false;

  // Fast-path: known build/lint patterns
  if (BUILD_LINT_PATTERNS.some((p) => p.test(command))) {
    return true;
  }

  // Fallback: unknown command but failed with error output
  // This catches custom/undocumented linters without explicit patterns
  const exitCode = toolResponse?.exitCode;
  const output = toolResponse?.output || "";
  if (exitCode !== 0 && exitCode !== undefined && hasErrorContent(output)) {
    return true;
  }

  return false;
}

/**
 * Summarize an edit attempt for inclusion in escalation messages.
 * Returns a brief one-line description of what was changed.
 */
function summarizeEdit(toolInput) {
  const { filePath, oldString, newString } = toolInput;
  const file = filePath ? filePath.split("/").pop() : "unknown";

  // If we have the actual diff content, summarize it
  if (oldString && newString) {
    const oldLines = (oldString || "").split("\n").length;
    const newLines = (newString || "").split("\n").length;
    const diff = newLines - oldLines;
    const diffStr = diff === 0 ? "same length" : `${diff > 0 ? "+" : ""}${diff} lines`;
    // Detect what kind of change
    if ((oldString || "").includes("import ") && (newString || "").includes("import ")) {
      return `import change in ${file}`;
    }
    if ((oldString || "").includes("function ") || (newString || "").includes("function ")) {
      return `function change in ${file} (${diffStr})`;
    }
    if ((oldString || "").includes("type ") || (newString || "").includes("type ")) {
      return `type change in ${file}`;
    }
    return `edit in ${file} (${diffStr})`;
  }

  return `edit in ${file}`;
}

/**
 * Summarize a bash command attempt for inclusion in escalation messages.
 */
function summarizeBash(toolInput) {
  const { command } = toolInput;
  if (!command) return "bash command";
  // Truncate long commands
  const truncated = command.length > 60 ? command.substring(0, 57) + "..." : command;
  return `\`${truncated}\``;
}

// ── State Management ────────────────────────────────────────────────

function getState(sessionId) {
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  try {
    if (existsSync(stateFile)) {
      return JSON.parse(readFileSync(stateFile, "utf8"));
    }
  } catch {
    // Corrupted state file, start fresh
  }
  return {
    consecutiveMatches: 0,
    lastFingerprint: null,
    lastTimestamp: 0,
    history: [],
    attempts: [],      // What fixes were tried
    lastFile: null,    // Last file edited
    fileEditCount: {}, // Track edits per file
    lastEscalationTier: 0,    // Highest tier that was escalated (for cooldown)
    lastEscalationTime: 0,    // When the last escalation happened
    fingerprintWindow: [],     // Rolling window of last N fingerprints for ping-pong detection
  };
}

// ── Cross-Session Solutions Store ──────────────────────────────────

/**
 * Load solutions from disk (read once at startup).
 * Returns {} if file doesn't exist or is corrupted.
 */
let solutionsCache = null;
function loadSolutions() {
  if (solutionsCache !== null) return solutionsCache;
  try {
    if (existsSync(SOLUTIONS_FILE)) {
      solutionsCache = JSON.parse(readFileSync(SOLUTIONS_FILE, "utf8"));
    } else {
      solutionsCache = {};
    }
  } catch {
    solutionsCache = {};
  }
  return solutionsCache;
}

/**
 * Save solutions to disk.
 */
function saveSolutions(solutions) {
  try {
    mkdirSync(join(SOLUTIONS_FILE, ".."), { recursive: true });
    writeFileSync(SOLUTIONS_FILE, JSON.stringify(solutions, null, 2));
  } catch {
    // Fail silently
  }
}

/**
 * Record a resolved error solution.
 */
function recordSolution(fingerprint, displayCodes, fixSummary, attemptCount) {
  const solutions = loadSolutions();
  const existing = solutions[fingerprint];
  const now = new Date().toISOString();

  if (existing) {
    existing.lastSeen = now;
    existing.lastFix = fixSummary;
    existing.successCount = (existing.successCount || 0) + 1;
    existing.avgAttempts = ((existing.avgAttempts || attemptCount) * existing.successCount + attemptCount) / (existing.successCount + 1);
  } else {
    solutions[fingerprint] = {
      displayCodes: displayCodes,
      lastFix: fixSummary,
      successCount: 1,
      avgAttempts: attemptCount,
      lastSeen: now,
    };
  }

  // LRU eviction — keep only most recent MAX_SOLUTIONS
  if (Object.keys(solutions).length > MAX_SOLUTIONS) {
    const sorted = Object.entries(solutions)
      .sort(([, a], [, b]) => new Date(b.lastSeen) - new Date(a.lastSeen))
      .slice(0, MAX_SOLUTIONS);
    solutionsCache = Object.fromEntries(sorted);
  } else {
    solutionsCache = solutions;
  }

  saveSolutions(solutionsCache);
}

/**
 * Get solution hint for an error fingerprint.
 */
function getSolutionHint(fingerprint) {
  const solutions = loadSolutions();
  const sol = solutions[fingerprint];
  if (!sol) return null;
  return {
    lastFix: sol.lastFix,
    avgAttempts: sol.avgAttempts,
    successCount: sol.successCount,
  };
}

function saveState(sessionId, state) {
  mkdirSync(STATE_DIR, { recursive: true });
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  writeFileSync(stateFile, JSON.stringify(state, null, 2));
}

// ── Attempt Tracking ─────────────────────────────────────────────────

/**
 * Record a fix attempt from Edit or Bash tool.
 */
function recordAttempt(state, toolName, toolInput) {
  const attempt = {
    tool: toolName,
    ts: Date.now(),
  };

  if (toolName === "edit" || toolName === "Edit") {
    attempt.summary = summarizeEdit(toolInput);
    attempt.file = toolInput.filePath || null;
  } else if (toolName === "bash" || toolName === "Bash") {
    attempt.summary = summarizeBash(toolInput);
    attempt.command = toolInput.command || null;
  }

  state.attempts.push(attempt);

  // Track file-level edits
  if (toolInput.filePath) {
    const count = (state.fileEditCount[toolInput.filePath] || 0) + 1;
    state.fileEditCount[toolInput.filePath] = count;
    state.lastFile = toolInput.filePath;
  }

  // Trim attempts
  if (state.attempts.length > MAX_ATTEMPTS) {
    state.attempts = state.attempts.slice(-MAX_ATTEMPTS);
  }
}

/**
 * Get the most recent N attempts as a summary string.
 */
function getAttemptSummary(state, count = 5) {
  const recent = state.attempts.slice(-count);
  if (recent.length === 0) return "No previous attempts recorded.";
  return recent.map((a, i) => `  ${i + 1}. ${a.summary}`).join("\n");
}

/**
 * Get files that have been repeatedly edited (potential hot-spot).
 */
function getHotspotFiles(state) {
  return Object.entries(state.fileEditCount || {})
    .filter(([, count]) => count >= 2)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3)
    .map(([file, count]) => `${file} (${count} edits)`);
}

// ── Message Generation ───────────────────────────────────────────────

/**
 * Generate a tiered escalation message.
 * @param {number} tier - Escalation tier (1-4)
 * @param {object} state - Current state
 * @param {object} result - Fingerprint result
 * @param {object|null} solutionHint - Optional solution hint from cross-session learning
 */
function generateEscalationMessage(tier, state, result, solutionHint = null) {
  const attempts = getAttemptSummary(state);
  const hotspots = getHotspotFiles(state);
  const hotspotNote = hotspots.length > 0
    ? `\n⚠️  Repeatedly edited files: ${hotspots.join(", ")}`
    : "";

  const baseInfo = [
    `Error: ${result.sample.join(" | ")}`,
    `Consecutive identical errors: ${state.consecutiveMatches}`,
  ].join("\n");

  if (tier === 4) {
    // NUCLEAR — 5+ errors
    return {
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: [
          `🔥 NUCLEAR ESCALATION (${state.consecutiveMatches} consecutive identical errors)`,
          `You are stuck in a loop. Stop all attempts NOW.`,
          ``,
          `ERROR: ${result.sample.join(" | ")}`,
          hotspotNote,
          ``,
          `=== WHAT TO DO ===`,
          `Consult @oracle IMMEDIATELY. Ask:`,
          `"I am stuck on [error] after ${state.consecutiveMatches} attempts. What am I fundamentally misunderstanding?`,
          `"What is the root cause and the correct approach?"`,
          ``,
          `Then follow Oracle's guidance EXACTLY. Do NOT deviate.`,
          ``,
          `=== PREVIOUS ATTEMPTS ===`,
          attempts,
        ].join("\n"),
      },
    };
  }

  if (tier === 3) {
    // HARD STOP — 4 errors
    return {
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: [
          `🚨 HARD STOP — MODEL SWITCH REQUIRED (${state.consecutiveMatches} consecutive identical errors)`,
          `You have failed ${state.consecutiveMatches} times. The current model cannot resolve this.`,
          ``,
          `ERROR: ${result.sample.join(" | ")}`,
          hotspotNote,
          ``,
          `=== EXPLICIT INSTRUCTIONS ===`,
          `1. Do NOT attempt another fix with the current model`,
          `2. Switch to a more powerful model NOW using one of:`,
          `   • Type: ultrawork`,
          `   • Or: task({ category: 'ultrabrain', prompt: 'Failed ${state.consecutiveMatches}x on [${result.sample[0]}]. Tried: ${state.attempts.slice(-3).map(a => a.summary).join(", ")}. Need fresh approach.' })`,
          `   • Or: task({ category: 'unspecified-high', prompt: 'Debug: [${result.sample.join(", ")}] - ${state.consecutiveMatches} failed attempts' })`,
          ``,
          `3. Provide the new model with:`,
          `   • File: ${state.lastFile || 'unknown'}`,
          `   • Error: ${result.sample.join(" | ")}`,
          `   • Previous attempts: ${state.attempts.slice(-3).map(a => a.summary).join(", ")}`,
          ``,
          `=== PREVIOUS ATTEMPTS ===`,
          attempts,
        ].join("\n"),
      },
    };
  }

  if (tier === 2) {
    // Firm redirect — 3 errors
    return {
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: [
          `⛔ STOP — ESCALATE NOW (${state.consecutiveMatches} consecutive identical errors)`,
          `Your fix attempts are not working. You are stuck.`,
          ``,
          `ERROR: ${result.sample.join(" | ")}`,
          hotspotNote,
          ``,
          `=== REQUIRED ACTIONS ===`,
          `1. STOP attempting to fix this error`,
          `2. Report to orchestrator using EXACTLY one of:`,
          `   • Type: task({ category: 'unspecified-high', prompt: 'Debug: [${result.sample.join(", ")}] File: ${state.lastFile || 'unknown'}' })`,
          `   • Or type: ultrawork`,
          `3. Include in your report:`,
          `   • File: ${state.lastFile || 'unknown'}`,
          `   • Error code: ${result.sample[0]}`,
          `   • What you tried (see below)`,
          `   • Why each attempt likely failed`,
          ``,
          `=== PREVIOUS ATTEMPTS ===`,
          attempts,
        ].join("\n"),
      },
    };
  }

  // Tier 1 — soft guidance (2 errors)
  const hintLine = solutionHint
    ? `\n💡 This error has been seen before. Previously resolved by: ${solutionHint.lastFix}\n   Average attempts to resolve: ${solutionHint.avgAttempts.toFixed(1)}`
    : "";

  return {
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: [
        `🔄 REPEATED ERROR — TRY DIFFERENT APPROACH (attempt ${state.consecutiveMatches}/${HARD_THRESHOLD})`,
        `Your previous fix did not resolve this error.${hintLine}`,
        ``,
        `ERROR: ${result.sample.join(" | ")}`,
        hotspotNote,
        ``,
        `=== BEFORE TRYING AGAIN ===`,
        `1. Re-read the FULL error message carefully`,
        `2. Try a FUNDAMENTALLY different approach — not a variation of the same fix`,
        `3. Consider: Is there a type/import/dependency issue?`,
        `4. If unsure, STOP and escalate rather than guessing`,
        ``,
        `=== PREVIOUS ATTEMPTS ===`,
        attempts,
      ].join("\n"),
    },
  };
}

// ── Main ────────────────────────────────────────────────────────────

async function main() {
    const raw = await readStdin();

  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.stdout.write("{}");
    return;
  }

  const sessionId = input.session_id;
  const rawToolName = input.tool_name || "";
  const toolName = rawToolName.toLowerCase(); // Normalize: LspDiagnostics → lspdiagnostics
  const toolOutput = input.tool_response?.output || "";
  const toolInput = input.tool_input || {};

  // ── Gate: only monitor relevant tools ──
  // For Edit tool, we track attempts but don't block on it
  const isEditTool = toolName === "edit";
  const isBashTool = toolName === "bash";
  const isLspTool = toolName === "lspdiagnostics" || toolName === "lsp_diagnostics";

  // Record Edit attempts for tracking (regardless of errors)
  if (isEditTool && toolInput.filePath) {
    const state = getState(sessionId);
    recordAttempt(state, "Edit", toolInput);
    saveState(sessionId, state);
    debugLog(`  → Edit recorded: ${summarizeEdit(toolInput)}`);
  }

  if (isBashTool) {
    if (!isBuildOrLintCommand(toolInput.command, input.tool_response)) {
      process.stdout.write("{}");
      return;
    }
    // Record build/lint command attempts
    const state = getState(sessionId);
    recordAttempt(state, "Bash", toolInput);
    saveState(sessionId, state);
  } else if (!isLspTool) {
    // Not a tool we monitor for errors
    process.stdout.write("{}");
    return;
  }

  // ── Extract error fingerprint ──
  debugLog(`INVOKED tool=${toolName} session=${sessionId} output_len=${toolOutput.length}`);
  const result = extractErrorFingerprint(toolName, toolOutput);
  const state = getState(sessionId);
  const now = Date.now();

  // ── Warning-only output — ignore, don't escalate, don't reset counter ──
  if (result !== null && result.fingerprint === "__WARNING_ONLY__") {
    debugLog(`  → WARNING ONLY (ignored)`);
    process.stdout.write("{}");
    return;
  }

  // ── Clean output → reset consecutive count but KEEP attempts ──
  if (result === null) {
    debugLog(`  → CLEAN (no errors detected)`);

    // ── Resolution summary — when errors clear after consecutive failures ──
    if (state.consecutiveMatches >= 2) {
      const lastAttempt = state.attempts.length > 0
        ? state.attempts[state.attempts.length - 1].summary
        : "unknown";

      // Record solution for cross-session learning
      if (state.lastFingerprint) {
        const prevHist = state.history.find(h => h.fingerprint === state.lastFingerprint);
        const displayCodes = prevHist ? prevHist.sample : [];
        recordSolution(state.lastFingerprint, displayCodes, lastAttempt, state.consecutiveMatches);
      }

      const summaryMsg = {
        hookSpecificOutput: {
          hookEventName: "PostToolUse",
          additionalContext: `✅ Error resolved after ${state.consecutiveMatches} attempts. Last successful action: ${lastAttempt}`,
        },
      };
      // Reset state
      state.consecutiveMatches = 0;
      state.lastFingerprint = null;
      state.lastTimestamp = now;
      state.lastEscalationTier = 0;
      state.lastEscalationTime = 0;
      state.fingerprintWindow = [];
      saveState(sessionId, state);
      process.stdout.write(JSON.stringify(summaryMsg));
      return;
    }

    if (state.consecutiveMatches > 0) {
      state.consecutiveMatches = 0;
      state.lastFingerprint = null;
      state.lastTimestamp = now;
      saveState(sessionId, state);
    }
    process.stdout.write("{}");
    return;
  }

  // ── Stale state (>5 min since last error) → reset ──
  if (state.lastTimestamp > 0 && now - state.lastTimestamp > STALE_MS) {
    state.consecutiveMatches = 0;
    state.lastFingerprint = null;
    state.history = [];
    state.lastEscalationTier = 0;
    state.lastEscalationTime = 0;
    // Keep attempts for context but reset the loop counter
  }

  // ── Same fingerprint → stuck (increment) ──
  // ── Different fingerprint → making progress (reset to 1) ──
  if (state.lastFingerprint === result.fingerprint) {
    state.consecutiveMatches++;
  } else {
    state.consecutiveMatches = 1;
    // New error — reset cooldown so new error can escalate properly
    state.lastEscalationTier = 0;
    state.lastEscalationTime = 0;
  }

  state.lastFingerprint = result.fingerprint;
  state.lastTimestamp = now;
  state.history.push({
    tool: toolName,
    fingerprint: result.fingerprint,
    errorCount: result.errorCount,
    sample: result.sample,
    ts: now,
  });

  // Trim history
  if (state.history.length > MAX_HISTORY) {
    state.history = state.history.slice(-MAX_HISTORY);
  }

  // ── Fingerprint window for ping-pong detection ──
  if (!state.fingerprintWindow) state.fingerprintWindow = [];
  state.fingerprintWindow.push(result.fingerprint);
  if (state.fingerprintWindow.length > PINGPONG_WINDOW) {
    state.fingerprintWindow = state.fingerprintWindow.slice(-PINGPONG_WINDOW);
  }

  // Count occurrences of current fingerprint in window
  const fpCount = state.fingerprintWindow.filter(f => f === result.fingerprint).length;
  const isPingPong = fpCount >= PINGPONG_THRESHOLD;

  saveState(sessionId, state);
  debugLog(`  → fp=${result.fingerprint} count=${state.consecutiveMatches} codes=${result.sample.join(",")} pingpong=${isPingPong}`);

  // ── Determine response ──
  let response = {};
  let escalatedTier = 0;

  // ── Cooldown check — after Tier 3/4, give escalated model time to work ──
  if (state.lastEscalationTier >= 3 && state.lastEscalationTime > 0) {
    const cooldownMs = state.lastEscalationTier >= 4 ? COOLDOWN_NUCLEAR_MS : COOLDOWN_HARD_MS;
    if (now - state.lastEscalationTime < cooldownMs) {
      debugLog(`  → COOLDOWN (tier=${state.lastEscalationTier}, ${Math.round((cooldownMs - (now - state.lastEscalationTime)) / 1000)}s remaining)`);
      saveState(sessionId, state);
      process.stdout.write("{}");
      return;
    }
  }

  // ── Ping-pong detection — alternating between same errors ──
  if (isPingPong) {
    // Get unique fingerprints in window to show what's oscillating
    const uniqueFps = [...new Set(state.fingerprintWindow)];
    const fpSamples = uniqueFps.map(fp => {
      const histEntry = state.history.find(h => h.fingerprint === fp);
      return histEntry ? histEntry.sample[0] || fp : fp;
    }).slice(0, 4);

    escalatedTier = 2; // Same as Tier 2
    response = {
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: [
          `🏓 PING-PONG LOOP DETECTED — You keep alternating between the same errors`,
          `Error [${fpSamples.join(", ")}] has appeared ${fpCount} times in your last ${state.fingerprintWindow.length} attempts.`,
          `You are NOT making progress — you are oscillating.`,
          ``,
          `=== REQUIRED ACTIONS ===`,
          `1. STOP attempting to fix this error`,
          `2. You are in a loop — switching approaches repeatedly without progress`,
          `3. Escalate using ONE of:`,
          `   • Type: task({ category: 'ultrabrain', prompt: 'Ping-pong loop on [${fpSamples.join(", ")}]. Tried: ${state.attempts.slice(-3).map(a => a.summary).join(", ")}. Need fresh approach.' })`,
          `   • Or type: ultrawork`,
          `   • Or: task({ category: 'unspecified-high', prompt: 'Debug: ping-pong on [${fpSamples.join(", ")}]' })`,
          ``,
          `=== PREVIOUS ATTEMPTS ===`,
          getAttemptSummary(state),
        ].join("\n"),
      },
    };
  }

  if (state.consecutiveMatches >= NUCLEAR_THRESHOLD) {
    // Tier 4: NUCLEAR — 5+ errors
    escalatedTier = 4;
    response = generateEscalationMessage(4, state, result);
  } else if (state.consecutiveMatches >= HARD_THRESHOLD) {
    // Tier 2 & 3 combined for HARD_THRESHOLD=3
    if (state.consecutiveMatches >= 4) {
      // Tier 3: HARD STOP — 4 errors
      escalatedTier = 3;
      response = generateEscalationMessage(3, state, result);
    } else {
      // Tier 2: Firm redirect — 3 errors
      escalatedTier = 2;
      response = generateEscalationMessage(2, state, result);
    }
  } else if (state.consecutiveMatches >= SOFT_THRESHOLD) {
    // Tier 1: Soft guidance — 2 errors
    escalatedTier = 1;
    // Check for cross-session solution hint
    const solutionHint = getSolutionHint(result.fingerprint);
    response = generateEscalationMessage(1, state, result, solutionHint);
  }

  // Track escalation tier for cooldown
  if (escalatedTier > 0) {
    state.lastEscalationTier = escalatedTier;
    state.lastEscalationTime = now;
    saveState(sessionId, state);
  }

  process.stdout.write(JSON.stringify(response));
}

main().catch(() => {
  process.stdout.write("{}");
});
