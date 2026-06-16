#!/usr/bin/env bash
# Build MCP Terminal sandbox images (local only). For push, use docker/build-sandbox-images.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "${ROOT}/docker/build-sandbox-images.sh" 1
