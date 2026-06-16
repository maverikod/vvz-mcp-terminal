#!/bin/bash
# Pull sandbox worker images listed in sandbox-images-spec.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -e

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="${LIB_DIR}/sandbox-images-spec"

if [ ! -f "$SPEC" ]; then
  echo "[WARN] sandbox-images-spec missing: $SPEC" >&2
  exit 0
fi

# shellcheck source=/dev/null
. "$SPEC"

pull_one() {
  local ref="$1"
  [ -n "$ref" ] || return 0
  echo "[INFO] Pulling sandbox image ${ref} ..."
  if ! docker pull "$ref"; then
    echo "[ERROR] docker pull failed for ${ref}" >&2
    return 1
  fi
}

ensure_docker_ready() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker CLI not found (install docker.io or docker-ce)" >&2
    return 1
  fi
  if ! systemctl is-active --quiet docker 2>/dev/null; then
    echo "[INFO] Starting docker.service ..."
    systemctl start docker
  fi
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] Docker daemon is not ready" >&2
  return 1
}

ensure_docker_ready
pull_one "${SANDBOX_IMAGE_python_dev_3_12:-}"
pull_one "${SANDBOX_IMAGE_node_dev_20:-}"
pull_one "${SANDBOX_IMAGE_base_tools:-}"
echo "[SUCCESS] Sandbox images ready"
