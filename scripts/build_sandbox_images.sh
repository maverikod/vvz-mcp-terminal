#!/usr/bin/env bash
# Build and tag MCP Terminal sandbox images (local or push to ghcr.io/mcp-terminal).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

build_one() {
  local dir="$1"
  local tag="$2"
  echo "==> docker build -t ${tag} ${dir}"
  docker build -t "${tag}" "${dir}"
}

build_one "${ROOT}/docker/python-dev" "ghcr.io/mcp-terminal/python-dev:3.12"
build_one "${ROOT}/docker/node-dev" "ghcr.io/mcp-terminal/node-dev:20"
build_one "${ROOT}/docker/base-tools" "ghcr.io/mcp-terminal/base-tools:latest"

echo "Done. Re-create terminal sessions so new containers pick up rebuilt images."
