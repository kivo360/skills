#!/usr/bin/env bash
# Local end-to-end test for the Hindsight side of review-with-memory.
#
# What it does:
#   1. Health-check the local Hindsight server (localhost:8888).
#   2. Run derive-tags.py on a synthetic file list and validate JSON shape.
#   3. Retain a uniquely-tagged synthetic finding into bank `review-with-memory-test`.
#   4. Recall it back using the same tags + a paraphrased query.
#   5. Assert the recall contains a token from the retained content.
#
# What it does NOT do:
#   - Exercise code-review-graph. That integration runs through the harness's
#     MCP tools at review time, not through this script.
#
# Prereqs:
#   - Hindsight container running (see SKILL.md "Prerequisites").
#   - `uv` and `jq` on PATH.
#
# Usage:
#   bash scripts/test-local.sh
#
# Cleanup:
#   The test bank is `review-with-memory-test`. To clear it, stop the container
#   and delete $HOME/.hindsight-docker (your Hindsight pgdata volume), or use a
#   different bank id by setting HINDSIGHT_TEST_BANK before running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE="$SCRIPT_DIR/hindsight-bridge.py"
DERIVE="$SCRIPT_DIR/derive-tags.py"
BANK="${HINDSIGHT_TEST_BANK:-review-with-memory-test}"
NONCE="$(date +%s)-$RANDOM"
MARKER="rwm-marker-$NONCE"

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
step()   { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing dependency: $1"; exit 2; }
}

require uv
require jq

step "1. Health check"
HEALTH_JSON="$(uv run --quiet "$BRIDGE" health)"
echo "$HEALTH_JSON"
if [[ "$(echo "$HEALTH_JSON" | jq -r '.ok')" != "true" ]]; then
  red "Hindsight is not reachable at ${HINDSIGHT_BASE_URL:-http://localhost:8888}."
  red "Start the container per SKILL.md, then re-run."
  exit 1
fi
green "OK"

step "2. derive-tags shape"
TAGS_JSON="$(printf 'src/auth/session.ts\napi/handlers/login.go\n' | uv run --quiet "$DERIVE")"
echo "$TAGS_JSON"
echo "$TAGS_JSON" | jq -e '.tags | length > 0' >/dev/null
echo "$TAGS_JSON" | jq -e '.modules | index("src")' >/dev/null
echo "$TAGS_JSON" | jq -e '.modules | index("api")' >/dev/null
green "OK"

step "3. Retain synthetic finding (bank=$BANK)"
CONTENT="Code review test marker $MARKER. Regex-based session token validation in src/auth/session.ts skipped unicode normalization, allowing lookalike-character bypass. Caught at review time."
RETAIN_JSON="$(uv run --quiet "$BRIDGE" retain \
  --bank "$BANK" \
  --content "$CONTENT" \
  --context "review-with-memory test-local.sh" \
  --tags "module:src,file:src/auth/session.ts,test-marker:$MARKER")"
echo "$RETAIN_JSON" | jq '.'
[[ "$(echo "$RETAIN_JSON" | jq -r '.ok')" == "true" ]] || { red "retain failed"; exit 1; }
green "OK"

step "4. Recall by tags"
RECALL_JSON="$(uv run --quiet "$BRIDGE" recall \
  --bank "$BANK" \
  --query "what failure modes have we seen in session token validation" \
  --tags "module:src,test-marker:$MARKER" \
  --tags-match any_strict \
  --budget low \
  --max-tokens 1024)"
echo "$RECALL_JSON" | jq '.response' | head -60
[[ "$(echo "$RECALL_JSON" | jq -r '.ok')" == "true" ]] || { red "recall failed"; exit 1; }

step "5. Assert recall contains marker or relevant content"
HAYSTACK="$(echo "$RECALL_JSON" | jq -c '.response')"
if echo "$HAYSTACK" | grep -qi "$MARKER"; then
  green "Found exact marker in recall results"
elif echo "$HAYSTACK" | grep -qiE "(unicode|normaliz|session token|lookalike)"; then
  yellow "Marker not found verbatim, but topical terms present (Hindsight extracted facts rather than echoing)."
  green "OK (topical recall)"
else
  red "Recall did not surface the retained finding. Raw response below:"
  echo "$RECALL_JSON" | jq '.'
  exit 1
fi

step "Done"
green "All checks passed. Test bank: $BANK"
echo "To clean up, stop Hindsight and remove \$HOME/.hindsight-docker, or use a fresh"
echo "HINDSIGHT_TEST_BANK on the next run."
