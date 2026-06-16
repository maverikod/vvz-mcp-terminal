#!/bin/bash
# Local dev container with project bind mounts (no .deb required).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"

TAG="${1:-}"
if [ -z "$TAG" ]; then
  TAG="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
print(m.group(1) if m else "0.1.0")
PY
)"
fi

DOCKERHUB_REPO="$(dockerhub_repo_default)"
IMAGE="${DOCKERHUB_REPO}:${TAG}"
CONTAINER="${MCP_TERMINAL_DEV_CONTAINER:-mcp-terminal-dev}"
PORT="${MCP_TERMINAL_DEV_PORT:-3011}"
CONFIG="${MCP_TERMINAL_DEV_CONFIG:-${PROJECT_ROOT}/configs/term_server.json}"

mkdir -p "${PROJECT_ROOT}/logs" "${PROJECT_ROOT}/configs" "${PROJECT_ROOT}/mtls_certificates"

if [ ! -f "$CONFIG" ]; then
  echo "[WARN] Config missing: $CONFIG — create with termgr create-config" >&2
fi

docker rm -f "$CONTAINER" 2>/dev/null || true

docker run -d --name "$CONTAINER" \
  -p "${PORT}:3011" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "${PROJECT_ROOT}/configs/term_server.json:/etc/mcp-terminal/term_server.json:ro" \
  -v "${PROJECT_ROOT}/logs:/var/log/mcp-terminal" \
  -v "${PROJECT_ROOT}:/var/mcp-terminal" \
  -v "${PROJECT_ROOT}/mtls_certificates:/etc/mcp-terminal/mtls_certificates:ro" \
  -v "${PROJECT_ROOT}:${PROJECT_ROOT}" \
  -e MCP_TERMINAL_SKIP_VENV_REEXEC=1 \
  -e MCP_TERMINAL_CONFIG_DIR=/etc/mcp-terminal \
  -e MCP_TERMINAL_LOG_DIR=/var/log/mcp-terminal \
  -e MCP_TERMINAL_DATA_DIR=/var/mcp-terminal \
  "$IMAGE"

echo "[SUCCESS] Dev container $CONTAINER started (image=$IMAGE, port=$PORT)"
echo "  logs: docker logs -f $CONTAINER"
