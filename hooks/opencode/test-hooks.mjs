#!/usr/bin/env node

/**
 * Test Suite for Linter Loop Escalation Hook System
 * 
 * Tests both:
 *   - linter-loop-escalation.mjs (PostToolUse)
 *   - edit-block-on-escalation.mjs (PreToolUse)
 * 
 * Run: node test-hooks.mjs
 */

import { spawn } from "node:child_process";
import { existsSync, unlinkSync, writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { dirname } from "node:path";

const HOOKS_DIR = dirname(new URL(import.meta.url).pathname);
const LINTER_HOOK = join(HOOKS_DIR, "linter-loop-escalation.mjs");
const BLOCK_HOOK = join(HOOKS_DIR, "edit-block-on-escalation.mjs");
const STATE_DIR = "/tmp/omo-linter-state";
const SOLUTIONS_FILE = process.env.HOME + "/.config/opencode/hooks/error-solutions.json";

// ── Test Framework ──────────────────────────────────────────────────

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;

function pass(name) {
  totalTests++;
  passedTests++;
  console.log(`  \x1b[32m✓\x1b[0m ${name}`);
}

function fail(name, reason) {
  totalTests++;
  failedTests++;
  console.log(`  \x1b[31m✗\x1b[0m ${name}`);
  console.log(`      Reason: ${reason}`);
}

function section(name) {
  console.log(`\n${name}`);
  console.log("─".repeat(60));
}

// ── Test Helpers ──────────────────────────────────────────────────

function cleanState(sessionId) {
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  try {
    if (existsSync(stateFile)) unlinkSync(stateFile);
  } catch {}
}

function runHook(hookPath, input, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const child = spawn("node", [hookPath], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let killed = false;

    const timer = setTimeout(() => {
      killed = true;
      child.kill();
    }, timeoutMs);

    child.stdout.on("data", (d) => { stdout += d.toString(); });
    child.stderr.on("data", (d) => { stderr += d.toString(); });

    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: code });
    });

    child.on("error", () => {
      clearTimeout(timer);
      resolve({ stdout: "", stderr: "Process error", exitCode: -1 });
    });

    child.stdin.write(JSON.stringify(input));
    child.stdin.end();
  });
}

async function runPostToolUse(input) {
  return runHook(LINTER_HOOK, input);
}

async function runPreToolUse(input) {
  return runHook(BLOCK_HOOK, input);
}

function assertContains(str, substr, msg) {
  if (!str || !str.includes(substr)) {
    throw new Error(`${msg}: expected "${str}" to contain "${substr}"`);
  }
}

function assertNotContains(str, substr, msg) {
  if (str && str.includes(substr)) {
    throw new Error(`${msg}: expected "${str}" NOT to contain "${substr}"`);
  }
}

function assertEquals(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg}: expected ${expected}, got ${actual}`);
  }
}

function parseJson(str) {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
}

// ── PostToolUse Tests ─────────────────────────────────────────────

async function testPostToolUse() {
  section("PostToolUse Hook Tests (linter-loop-escalation.mjs)");

  // C1: Clean output → returns {}
  {
    const result = await runPostToolUse({
      session_id: "test-c1",
      tool_name: "lsp_diagnostics",
      tool_input: {},
      tool_response: { output: "No diagnostics found" }
    });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("C1: Clean lsp_diagnostics returns {}");
    } else {
      fail("C1: Clean lsp_diagnostics returns {}", `Got: ${result.stdout}`);
    }
    cleanState("test-c1");
  }

  // C2: Single error → returns {}
  {
    cleanState("test-c2");
    const result = await runPostToolUse({
      session_id: "test-c2",
      tool_name: "lsp_diagnostics",
      tool_input: {},
      tool_response: { output: "error TS2345: Argument type error" }
    });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("C2: Single error returns {} (below threshold)");
    } else {
      fail("C2: Single error returns {}", `Got: ${result.stdout.substring(0, 100)}`);
    }
    cleanState("test-c2");
  }

  // C3: 2 identical errors → Tier 1 soft guidance
  {
    cleanState("test-c3");
    const errOutput = "error TS2345: Argument type error";
    await runPostToolUse({ session_id: "test-c3", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const result = await runPostToolUse({ session_id: "test-c3", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext.includes("REPEATED ERROR")) {
      pass("C3: 2 identical errors → Tier 1 soft guidance");
    } else {
      fail("C3: 2 identical errors → Tier 1", `Got: ${result.stdout.substring(0, 150)}`);
    }
    cleanState("test-c3");
  }

  // C4: 3 identical errors → Tier 2 firm redirect
  {
    cleanState("test-c4");
    const errOutput = "error TS2345: Argument type error";
    await runPostToolUse({ session_id: "test-c4", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    await runPostToolUse({ session_id: "test-c4", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const result = await runPostToolUse({ session_id: "test-c4", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput && 
        parsed.hookSpecificOutput.additionalContext.includes("STOP") &&
        parsed.hookSpecificOutput.additionalContext.includes("task(")) {
      pass("C4: 3 identical errors → Tier 2 firm redirect");
    } else {
      fail("C4: 3 identical errors → Tier 2", `Got: ${result.stdout.substring(0, 150)}`);
    }
    cleanState("test-c4");
  }

  // C5: 4 identical errors → Tier 3 HARD STOP
  {
    cleanState("test-c5");
    const errOutput = "error TS2345: Argument type error";
    for (let i = 0; i < 3; i++) {
      await runPostToolUse({ session_id: "test-c5", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    }
    const result = await runPostToolUse({ session_id: "test-c5", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput && 
        (parsed.hookSpecificOutput.additionalContext.includes("HARD STOP") ||
         parsed.hookSpecificOutput.additionalContext.includes("ultrawork") ||
         parsed.hookSpecificOutput.additionalContext.includes("ultrabrain"))) {
      pass("C5: 4 identical errors → Tier 3 HARD STOP");
    } else {
      fail("C5: 4 identical errors → Tier 3", `Got: ${result.stdout.substring(0, 200)}`);
    }
    cleanState("test-c5");
  }

  // C6: 5+ identical errors → cooldown blocks Tier 4 (correct behavior)
  // After Tier 3 (4 errors), cooldown prevents escalation on 5th error
  {
    cleanState("test-c6");
    const errOutput = "error TS2345: Argument type error";
    for (let i = 0; i < 4; i++) {
      await runPostToolUse({ session_id: "test-c6", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    }
    const result = await runPostToolUse({ session_id: "test-c6", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    // After Tier 3, cooldown is active - should return {} (not Tier 4)
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("C6: After Tier 3, cooldown blocks subsequent escalation (correct)");
    } else {
      fail("C6: After Tier 3, cooldown blocks subsequent escalation", `Got: ${result.stdout.substring(0, 200)}`);
    }
    cleanState("test-c6");
  }

  // C7: Warning-only output → returns {}
  {
    cleanState("test-c7");
    const result = await runPostToolUse({
      session_id: "test-c7",
      tool_name: "lsp_diagnostics",
      tool_input: {},
      tool_response: { output: "warning: unused variable `x` at src/main.rs:10" }
    });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("C7: Warning-only returns {} (filtered)");
    } else {
      fail("C7: Warning-only returns {}", `Got: ${result.stdout.substring(0, 100)}`);
    }
    cleanState("test-c7");
  }

  // C8: Mixed errors+warnings → returns response (errors not filtered)
  {
    cleanState("test-c8");
    const mixedOutput = "warning: unused variable\nerror TS2345: Argument type error";
    await runPostToolUse({ session_id: "test-c8", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: mixedOutput } });
    const result = await runPostToolUse({ session_id: "test-c8", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: mixedOutput } });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput) {
      pass("C8: Mixed errors+warnings → errors not filtered");
    } else {
      fail("C8: Mixed errors+warnings → errors not filtered", `Got: ${result.stdout}`);
    }
    cleanState("test-c8");
  }

  // C9: Unknown linter with non-zero exit → detected via fallback
  // First call detects it (count=1), second call triggers Tier 1
  {
    cleanState("test-c9");
    await runPostToolUse({
      session_id: "test-c9",
      tool_name: "Bash",
      tool_input: { command: "custom-linter --check" },
      tool_response: { output: "ERROR: Something went wrong at /path/file.txt:42", exitCode: 1 }
    });
    const result = await runPostToolUse({
      session_id: "test-c9",
      tool_name: "Bash",
      tool_input: { command: "custom-linter --check" },
      tool_response: { output: "ERROR: Something went wrong at /path/file.txt:42", exitCode: 1 }
    });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput) {
      pass("C9: Unknown linter with non-zero exit detected");
    } else {
      fail("C9: Unknown linter with non-zero exit detected", `Got: ${result.stdout}`);
    }
    cleanState("test-c9");
  }

  // C10: Different error codes → counter resets
  {
    cleanState("test-c10");
    await runPostToolUse({ session_id: "test-c10", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: "error TS2345: Argument type error" } });
    const result = await runPostToolUse({ session_id: "test-c10", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: "error TS9999: Different error" } });
    const parsed = parseJson(result.stdout);
    // Different error should NOT trigger escalation (counter reset to 1)
    if (parsed && Object.keys(parsed).length === 0) {
      pass("C10: Different error codes → counter resets");
    } else {
      fail("C10: Different error codes → counter resets", `Got: ${result.stdout.substring(0, 100)}`);
    }
    cleanState("test-c10");
  }

  // C11: Resolution after errors → shows resolved summary
  {
    cleanState("test-c11");
    const errOutput = "error TS2345: Argument type error";
    await runPostToolUse({ session_id: "test-c11", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    await runPostToolUse({ session_id: "test-c11", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errOutput } });
    const result = await runPostToolUse({ session_id: "test-c11", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: "No diagnostics found" } });
    if (result.stdout.includes("resolved") || result.stdout.includes("✅")) {
      pass("C11: Resolution after errors → shows resolved summary");
    } else {
      fail("C11: Resolution after errors → shows resolved summary", `Got: ${result.stdout.substring(0, 100)}`);
    }
    cleanState("test-c11");
  }

  // C12: Ping-pong detection → alternating errors detected
  {
    cleanState("test-c12");
    const errA = "error TS2345: Argument type error";
    const errB = "error TS9999: Different error";
    await runPostToolUse({ session_id: "test-c12", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errA } });
    await runPostToolUse({ session_id: "test-c12", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errB } });
    await runPostToolUse({ session_id: "test-c12", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errA } });
    await runPostToolUse({ session_id: "test-c12", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errB } });
    const result = await runPostToolUse({ session_id: "test-c12", tool_name: "lsp_diagnostics", tool_input: {}, tool_response: { output: errA } });
    const parsed = parseJson(result.stdout);
    if (parsed && parsed.hookSpecificOutput && 
        (parsed.hookSpecificOutput.additionalContext.includes("PING-PONG") ||
         parsed.hookSpecificOutput.additionalContext.includes("oscillat"))) {
      pass("C12: Ping-pong detection → alternating errors detected");
    } else {
      fail("C12: Ping-pong detection → alternating errors detected", `Got: ${result.stdout.substring(0, 200)}`);
    }
    cleanState("test-c12");
  }

  // R1: Empty input → returns {} without crashing
  {
    const result = await runPostToolUse({});
    if (result.exitCode === 0) {
      pass("R1: Empty input returns {} without crashing");
    } else {
      fail("R1: Empty input returns {}", `Exit code: ${result.exitCode}`);
    }
  }

  // R2: Malformed JSON → returns {} without crashing
  {
    const child = spawn("node", [LINTER_HOOK], { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    child.stdout.on("data", (d) => { stdout += d.toString(); });
    child.on("close", (code) => {
      if (code === 0) {
        pass("R2: Malformed JSON returns {} without crashing");
      } else {
        fail("R2: Malformed JSON returns {}", `Exit code: ${code}`);
      }
    });
    child.stdin.write("not valid json {");
    child.stdin.end();
    await new Promise(r => setTimeout(r, 100));
  }

  // R3: Missing session_id → returns {}
  {
    const result = await runPostToolUse({ tool_name: "lsp_diagnostics", tool_response: { output: "error TS2345" } });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("R3: Missing session_id returns {}");
    } else {
      fail("R3: Missing session_id returns {}", `Got: ${result.stdout}`);
    }
    cleanState("test-r3");
  }

  // R4: Non-monitored tool → returns {}
  {
    const result = await runPostToolUse({ session_id: "test-r4", tool_name: "Read", tool_input: {}, tool_response: { output: "some content" } });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("R4: Non-monitored tool (Read) returns {}");
    } else {
      fail("R4: Non-monitored tool returns {}", `Got: ${result.stdout}`);
    }
    cleanState("test-r4");
  }

  // R5: Bash command that's NOT build/lint → returns {}
  {
    cleanState("test-r5");
    const result = await runPostToolUse({ session_id: "test-r5", tool_name: "Bash", tool_input: { command: "echo hello" }, tool_response: { output: "hello" } });
    const parsed = parseJson(result.stdout);
    if (parsed && Object.keys(parsed).length === 0) {
      pass("R5: Non-build Bash command returns {}");
    } else {
      fail("R5: Non-build Bash command returns {}", `Got: ${result.stdout}`);
    }
    cleanState("test-r5");
  }
}

// ── PreToolUse Tests ──────────────────────────────────────────────

async function testPreToolUse() {
  section("PreToolUse Hook Tests (edit-block-on-escalation.mjs)");

  // Helper to write a state file
  function writeState(sessionId, state) {
    const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
    const stateFile = join(STATE_DIR, `${safe}.json`);
    writeFileSync(stateFile, JSON.stringify(state));
  }

  // P1: No state file → exit 0 (ALLOW)
  {
    cleanState("test-p1");
    const result = await runPreToolUse({ session_id: "test-p1", tool_name: "Edit", tool_input: { filePath: "/foo/bar.ts" } });
    assertEquals(result.exitCode, 0, "P1: No state → ALLOW");
    pass("P1: No state file → exit 0 (ALLOW)");
  }

  // P2: State with low consecutiveMatches → exit 0 (ALLOW)
  {
    cleanState("test-p2");
    writeState("test-p2", {
      consecutiveMatches: 2,
      lastFingerprint: "abc123",
      lastTimestamp: Date.now(),
      lastFile: "/foo/bar.ts",
      lastEscalationTier: 1,
      lastEscalationTime: Date.now(),
    });
    const result = await runPreToolUse({ session_id: "test-p2", tool_name: "Edit", tool_input: { filePath: "/foo/bar.ts" } });
    assertEquals(result.exitCode, 0, "P2: Low consecutiveMatches → ALLOW");
    pass("P2: State with low consecutiveMatches → exit 0 (ALLOW)");
    cleanState("test-p2");
  }

  // P3: State with high consecutiveMatches + matching file → exit 2 (BLOCK)
  {
    cleanState("test-p3");
    writeState("test-p3", {
      consecutiveMatches: 3,
      lastFingerprint: "abc123",
      lastTimestamp: Date.now(),
      lastFile: "/foo/bar.ts",
      history: [{ fingerprint: "abc123", sample: ["TS2345"] }],
      lastEscalationTier: 2,
      lastEscalationTime: Date.now(),
    });
    const result = await runPreToolUse({ session_id: "test-p3", tool_name: "Edit", tool_input: { filePath: "/foo/bar.ts" } });
    assertEquals(result.exitCode, 2, "P3: High consecutiveMatches + same file → BLOCK");
    pass("P3: State with high consecutiveMatches + matching file → exit 2 (BLOCK)");
    cleanState("test-p3");
  }

  // P4: State with high consecutiveMatches + DIFFERENT file → exit 0 (ALLOW)
  {
    cleanState("test-p4");
    writeState("test-p4", {
      consecutiveMatches: 3,
      lastFingerprint: "abc123",
      lastTimestamp: Date.now(),
      lastFile: "/foo/bar.ts",
      lastEscalationTier: 2,
      lastEscalationTime: Date.now(),
    });
    const result = await runPreToolUse({ session_id: "test-p4", tool_name: "Edit", tool_input: { filePath: "/different/file.ts" } });
    assertEquals(result.exitCode, 0, "P4: High consecutiveMatches + different file → ALLOW");
    pass("P4: State with high consecutiveMatches + DIFFERENT file → exit 0 (ALLOW)");
    cleanState("test-p4");
  }

  // P5: Stale state (>5 min old) → exit 0 (ALLOW)
  {
    cleanState("test-p5");
    writeState("test-p5", {
      consecutiveMatches: 3,
      lastFingerprint: "abc123",
      lastTimestamp: Date.now() - (6 * 60 * 1000), // 6 minutes ago
      lastFile: "/foo/bar.ts",
      lastEscalationTier: 2,
      lastEscalationTime: Date.now() - (6 * 60 * 1000),
    });
    const result = await runPreToolUse({ session_id: "test-p5", tool_name: "Edit", tool_input: { filePath: "/foo/bar.ts" } });
    assertEquals(result.exitCode, 0, "P5: Stale state → ALLOW");
    pass("P5: Stale state (>5 min old) → exit 0 (ALLOW)");
    cleanState("test-p5");
  }

  // PR1: Empty input → exit 0 without crashing
  {
    const result = await runPreToolUse({});
    assertEquals(result.exitCode, 0, "PR1: Empty input → ALLOW");
    pass("PR1: Empty input → exit 0 without crashing");
  }

  // PR2: Missing session_id → exit 0 without crashing
  {
    const result = await runPreToolUse({ tool_name: "Edit", tool_input: { filePath: "/foo/bar.ts" } });
    assertEquals(result.exitCode, 0, "PR2: Missing session_id → ALLOW");
    pass("PR2: Missing session_id → exit 0 without crashing");
  }
}

// ── Main ─────────────────────────────────────────────────────────

async function main() {
  console.log("\n═══════════════════════════════════════════════════════════");
  console.log("   Linter Loop Escalation Hook System - Test Suite");
  console.log("═══════════════════════════════════════════════════════════");

  // Ensure state directory exists
  try { mkdirSync(STATE_DIR, { recursive: true }); } catch {}

  // Clean up any stale state from previous runs
  try {
    const { readdirSync, unlinkSync } = await import("node:fs");
    for (const f of readdirSync(STATE_DIR)) {
      if (f.endsWith(".json")) {
        try { unlinkSync(join(STATE_DIR, f)); } catch {}
      }
    }
  } catch {}

  await testPostToolUse();
  await testPreToolUse();

  // Clean up solutions file if it was created
  try {
    if (existsSync(SOLUTIONS_FILE)) {
      unlinkSync(SOLUTIONS_FILE);
    }
  } catch {}

  // Final cleanup of all test state
  try {
    const { readdirSync, unlinkSync } = await import("node:fs");
    for (const f of readdirSync(STATE_DIR)) {
      if (f.endsWith(".json")) {
        try { unlinkSync(join(STATE_DIR, f)); } catch {}
      }
    }
  } catch {}

  // Summary
  section("Test Summary");
  const pct = totalTests > 0 ? Math.round((passedTests / totalTests) * 100) : 0;
  console.log(`  Total:  ${totalTests}`);
  console.log(`  \x1b[32mPassed: ${passedTests}\x1b[0m`);
  console.log(`  \x1b[31mFailed: ${failedTests}\x1b[0m`);
  console.log(`  \x1b[1mPass@1: ${pct}%\x1b[0m`);
  console.log("═══════════════════════════════════════════════════════════\n");

  process.exit(failedTests > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error("Test suite error:", e);
  process.exit(1);
});
