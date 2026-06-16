#!/bin/bash
# Build and optionally push MCP Terminal sandbox worker images (Docker Hub by default).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"
# shellcheck source=sandbox_images.sh
source "$SCRIPT_DIR/sandbox_images.sh"

SKIP_PUSH="${1:-0}"

ensure_dockerhub_push() {
  if [ "$SKIP_PUSH" = "1" ]; then
    return 0
  fi
  if [ -n "${MCP_TERMINAL_DOCKERHUB_USERNAME:-}" ] && [ -n "${MCP_TERMINAL_DOCKERHUB_TOKEN:-}" ]; then
    echo "[INFO] Logging in to Docker Hub as ${MCP_TERMINAL_DOCKERHUB_USERNAME}"
    echo "$MCP_TERMINAL_DOCKERHUB_TOKEN" | docker login -u "$MCP_TERMINAL_DOCKERHUB_USERNAME" --password-stdin
  fi
  local user repo_user
  user="$(dockerhub_logged_in_user)"
  repo_user="$(sandbox_repo_user)"
  if [ -z "$user" ]; then
    echo "[ERROR] Not logged in to Docker Hub. Run: docker login -u <user>" >&2
    exit 1
  fi
  if [ "$repo_user" != "$user" ]; then
    echo "[ERROR] Cannot push sandbox images for user ${repo_user}: logged in as ${user}." >&2
    echo "[ERROR] Use: export MCP_TERMINAL_SANDBOX_REPO_USER=${user}" >&2
    exit 1
  fi
}

build_one() {
  local dir="$1"
  local tag="$2"
  echo "[INFO] docker build -t ${tag} ${dir}"
  docker build -t "${tag}" "${dir}"
  if [ "$SKIP_PUSH" = "1" ]; then
    return 0
  fi
  echo "[INFO] docker push ${tag}"
  docker push "$tag"
}

ensure_dockerhub_push

PYTHON_DEV="$(sandbox_image_python_dev)"
NODE_DEV="$(sandbox_image_node_dev)"
BASE_TOOLS="$(sandbox_image_base_tools)"

build_one "${PROJECT_ROOT}/docker/python-dev" "$PYTHON_DEV"
build_one "${PROJECT_ROOT}/docker/node-dev" "$NODE_DEV"
build_one "${PROJECT_ROOT}/docker/base-tools" "$BASE_TOOLS"

echo "[SUCCESS] Sandbox images built (push=$([ "$SKIP_PUSH" = "1" ] && echo no || echo yes))"
echo "[INFO]   ${PYTHON_DEV}"
echo "[INFO]   ${NODE_DEV}"
echo "[INFO]   ${BASE_TOOLS}"
