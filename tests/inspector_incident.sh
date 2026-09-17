#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ARGS=$(cat tests/fixtures/inspector_incident.json)
npx -y @modelcontextprotocol/inspector --cli -- \
  --config plugin/mcp.json \
  --server jevsor \
  --method tools/call \
  --tool-name evaluate \
  --cwd . \
  --connect-timeout 30000 \
  --format json \
  --tool-args-json "$ARGS"
