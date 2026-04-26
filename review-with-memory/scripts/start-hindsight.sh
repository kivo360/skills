#!/usr/bin/env bash
# Start the local Hindsight server with credentials sourced from ../.env.
#
# Reads HINDSIGHT_API_LLM_* from .env (which is gitignored). Never embeds
# credentials in this script or in SKILL.md.
#
# Usage:
#   bash scripts/start-hindsight.sh         # foreground
#   bash scripts/start-hindsight.sh -d      # detached
#
# Stop:
#   docker stop $(docker ps -qf ancestor=ghcr.io/vectorize-io/hindsight:latest)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE — copy .env.example and fill in your Fireworks key" >&2
  exit 1
fi

DETACH=""
[[ "${1:-}" == "-d" || "${1:-}" == "--detach" ]] && DETACH="-d"

exec docker run --rm $DETACH ${DETACH:+--name hindsight} -p 8888:8888 -p 9999:9999 \
  --env-file "$ENV_FILE" \
  -v "$HOME/.hindsight-docker:/home/hindsight/.pg0" \
  ghcr.io/vectorize-io/hindsight:latest
