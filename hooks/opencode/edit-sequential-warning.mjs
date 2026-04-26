#!/usr/bin/env node

/**
 * Edit Sequential Warning — PostToolUse Hook
 *
 * Tracks sequential edit calls per file per session and warns when
 * 2+ edits are detected on the same schema file. Recommends batching
 * all changes into a single edit call to prevent LINE#ID corruption.
 *
 * This is a PostToolUse hook — it fires AFTER the Edit tool completes.
 * It cannot block (that's PreToolUse's job), but it injects guidance
 * context that the agent will see in its next turn.
 *
 * Targets: schema files only (same patterns as schema-write-guard.mjs)
 *
 * State: /tmp/omo-schema-guard/{session_id}.json (shared with schema-write-guard)
 *
 * Output: JSON to stdout with hookSpecificOutput.additionalContext
 *   - {} = no intervention
 *   - { hookSpecificOutput: { ... } } = inject warning message
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";

const STATE_DIR = "/tmp/omo-schema-guard";
const WARN_THRESHOLD = 2;
const ESCALATION_THRESHOLD = 4;
const STALE_MS = 10 * 60 * 1000; // 10 minutes

const SCHEMA_PATTERNS = [
  /\/schema\.ts$/,
  /\/schema\/[^/]+\.ts$/,
  /\/drizzle\/[^/]+\.ts$/,
  /\/migrations\/[^/]+\.sql$/,
];

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

function isSchemaFile(filePath) {
  if (!filePath) {
    return false;
  }
  return SCHEMA_PATTERNS.some((pattern) => pattern.test(filePath));
}

function ensureStateDir() {
  try {
    if (!existsSync(STATE_DIR)) {
      mkdirSync(STATE_DIR, { recursive: true });
    }
  } catch {
    // Non-fatal
  }
}

function getState(sessionId) {
  if (!sessionId) {
    return null;
  }
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  try {
    if (existsSync(stateFile)) {
      const state = JSON.parse(readFileSync(stateFile, "utf8"));
      if (state.lastTimestamp && Date.now() - state.lastTimestamp > STALE_MS) {
        return null;
      }
      return state;
    }
  } catch {
    // Corrupted
  }
  return null;
}

function saveState(sessionId, state) {
  if (!sessionId) {
    return;
  }
  ensureStateDir();
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const stateFile = join(STATE_DIR, `${safe}.json`);
  try {
    writeFileSync(stateFile, JSON.stringify(state, null, 2));
  } catch {
    // Non-fatal
  }
}

function buildWarning(filePath, editCount) {
  const fileName = basename(filePath);

  if (editCount >= ESCALATION_THRESHOLD) {
    return [
      `⛔ SEQUENTIAL EDIT ESCALATION — ${editCount} edits on ${fileName}`,
      "",
      "You have edited this schema file too many times sequentially.",
      "LINE#ID hashes are likely corrupted at this point.",
      "",
      "═══ IMMEDIATE ACTION REQUIRED ═══",
      "",
      `1. Restore the file: git checkout HEAD -- ${filePath}`,
      "2. Re-read the file to get fresh LINE#ID hashes",
      "3. Plan ALL remaining changes before issuing ONE edit call",
      "4. If stuck, consult Oracle:",
      `   task({ subagent_type: 'oracle', prompt: 'Need schema edit strategy for ${fileName}' })`,
      "",
      "DO NOT issue another edit on this file without restoring first.",
    ].join("\n");
  }

  return [
    `⚠️ SEQUENTIAL EDIT WARNING — ${editCount} edits on ${fileName}`,
    "",
    "Editing the same schema file multiple times risks LINE#ID hash corruption.",
    "Each edit shifts line numbers, invalidating cached hashes from prior reads.",
    "",
    "═══ RECOMMENDED APPROACH ═══",
    "",
    "Batch ALL remaining changes into a SINGLE edit call:",
    "  edits: [",
    '    { op: "replace", pos: "50#AB", end: "55#CD", lines: ["content A"] },',
    '    { op: "append", pos: "100#XY", lines: ["content B"] }',
    "  ]",
    "",
    "If hashes look wrong, restore first:",
    `  git checkout HEAD -- ${filePath}`,
  ].join("\n");
}

async function main() {
  const raw = await readStdin();

  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    // Fail open — no output
    console.log("{}");
    return;
  }

  const toolName = (input.tool_name || "").toLowerCase();

  // Only track Edit tool
  if (toolName !== "edit") {
    console.log("{}");
    return;
  }

  const sessionId = input.session_id;
  const toolInput = input.tool_input || {};
  const filePath = toolInput.filePath || toolInput.file_path || "";

  // Only track schema files
  if (!isSchemaFile(filePath)) {
    console.log("{}");
    return;
  }

  // ── Track edit count ──

  const state = getState(sessionId) || {
    violations: {},
    editCounts: {},
    lastTimestamp: 0,
  };

  const fileKey = filePath.replace(/\//g, "__");
  state.editCounts = state.editCounts || {};
  state.editCounts[fileKey] = (state.editCounts[fileKey] || 0) + 1;
  state.lastTimestamp = Date.now();
  saveState(sessionId, state);

  const editCount = state.editCounts[fileKey];

  // Below threshold — no intervention
  if (editCount < WARN_THRESHOLD) {
    console.log("{}");
    return;
  }

  // ── Inject warning ──

  const warning = buildWarning(filePath, editCount);

  console.log(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: warning,
      },
    })
  );
}

main().catch(() => {
  console.log("{}");
});
