#!/bin/bash
# Build Docker image, push to Docker Hub, build sandbox images, and create Debian package.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"
DOCKERHUB_REPO="$(dockerhub_repo_default)"
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-host}"
SKIP_PUSH=0
SKIP_DEB=0
SKIP_SANDBOX=0
DEV_RUN=0

usage() {
  cat <<'EOF'
Usage: docker/build.sh [OPTIONS]

Build mcp-terminal Docker image, push to Docker Hub, optionally push sandbox images,
and build the Debian package.
Version is always read from pyproject.toml. Image tags: REPO:VERSION and REPO:latest.

Options:
  --skip-push       Build service image only; do not push to Docker Hub
  --skip-deb        Do not build the Debian package
  --skip-sandbox    Do not build/push sandbox worker images
  --dev-run         After build, run local dev container via docker/run.sh
  -h, --help        Show this help

Environment:
  MCP_TERMINAL_DOCKERHUB_REPO       Docker Hub repository (default: <docker-login-user>/mcp-terminal)
  MCP_TERMINAL_DOCKERHUB_USERNAME   Docker Hub username for non-interactive login
  MCP_TERMINAL_DOCKERHUB_TOKEN      Docker Hub access token (or password)
  MCP_TERMINAL_SANDBOX_REPO_USER       Docker Hub user for sandbox repos (default: same as service)
  MCP_TERMINAL_SANDBOX_IMAGE_*         Override full sandbox image refs (see sandbox_images.sh)
  DOCKER_BUILD_NETWORK              docker build network (default: host)
  MCP_TERMINAL_DOCKER_NO_CACHE=1    Pass --no-cache to docker build
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1; shift ;;
    --skip-deb) SKIP_DEB=1; shift ;;
    --skip-sandbox) SKIP_SANDBOX=1; shift ;;
    --dev-run) DEV_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "[ERROR] Unknown option: $1" >&2; usage >&2; exit 1 ;;
    *) echo "[ERROR] Unexpected argument: $1 (version is read from pyproject.toml)" >&2; usage >&2; exit 1 ;;
  esac
done

VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
if not m:
    raise SystemExit("Cannot read version from pyproject.toml")
print(m.group(1))
PY
)"

VERSION_TAG="${DOCKERHUB_REPO}:${VERSION}"
LATEST_TAG="${DOCKERHUB_REPO}:latest"

if [ ! -f "docker/Dockerfile" ]; then
  echo "[ERROR] Dockerfile not found in docker/"
  exit 1
fi

echo "[INFO] Building mcp-terminal Docker image"
echo "[INFO]   version tag: $VERSION_TAG"
echo "[INFO]   latest tag:  $LATEST_TAG"

DOCKER_BUILD_EXTRAS=(--network="$DOCKER_BUILD_NETWORK")
if [ "${MCP_TERMINAL_DOCKER_NO_CACHE:-}" = "1" ]; then
  DOCKER_BUILD_EXTRAS+=(--no-cache)
  echo "[INFO] MCP_TERMINAL_DOCKER_NO_CACHE=1: docker build --no-cache"
fi

BUILD_NET_ARGS=(--network="$DOCKER_BUILD_NETWORK")
DF="$PROJECT_ROOT/docker/Dockerfile"
CTX="$PROJECT_ROOT"
LEGACY_BUILD=(env DOCKER_BUILDKIT=0 docker build)

if docker buildx version >/dev/null 2>&1; then
  echo "[INFO] using: docker buildx build --load"
  if ! docker buildx build --load "${DOCKER_BUILD_EXTRAS[@]}" -t "$VERSION_TAG" -t "$LATEST_TAG" -f "$DF" "$CTX"; then
    echo "[INFO] buildx failed — retrying with DOCKER_BUILDKIT=0 docker build"
    "${LEGACY_BUILD[@]}" "${BUILD_NET_ARGS[@]}" -t "$VERSION_TAG" -t "$LATEST_TAG" -f "$DF" "$CTX"
  fi
else
  echo "[INFO] using: DOCKER_BUILDKIT=0 docker build"
  "${LEGACY_BUILD[@]}" "${BUILD_NET_ARGS[@]}" -t "$VERSION_TAG" -t "$LATEST_TAG" -f "$DF" "$CTX"
fi

echo "[SUCCESS] Service image built: $VERSION_TAG and $LATEST_TAG"

if [ "$SKIP_PUSH" -eq 0 ]; then
  if [ -n "${MCP_TERMINAL_DOCKERHUB_USERNAME:-}" ] && [ -n "${MCP_TERMINAL_DOCKERHUB_TOKEN:-}" ]; then
    echo "[INFO] Logging in to Docker Hub as ${MCP_TERMINAL_DOCKERHUB_USERNAME}"
    echo "$MCP_TERMINAL_DOCKERHUB_TOKEN" | docker login -u "$MCP_TERMINAL_DOCKERHUB_USERNAME" --password-stdin
  fi
  REPO_USER="${DOCKERHUB_REPO%%/*}"
  DOCKER_USER="$(dockerhub_logged_in_user)"
  if [ -z "$DOCKER_USER" ]; then
    echo "[ERROR] Not logged in to Docker Hub. Run: docker login -u <user>" >&2
    exit 1
  fi
  if [ "$REPO_USER" != "$DOCKER_USER" ]; then
    echo "[ERROR] Cannot push ${DOCKERHUB_REPO}: logged in as ${DOCKER_USER}." >&2
    echo "[ERROR] Use: export MCP_TERMINAL_DOCKERHUB_REPO=${DOCKER_USER}/mcp-terminal" >&2
    echo "[ERROR] Or: docker login -u ${REPO_USER}" >&2
    exit 1
  fi
  echo "[INFO] Pushing $VERSION_TAG"
  docker push "$VERSION_TAG"
  echo "[INFO] Pushing $LATEST_TAG"
  docker push "$LATEST_TAG"
  echo "[SUCCESS] Service images pushed to Docker Hub (${DOCKERHUB_REPO})"
else
  echo "[INFO] Skipping Docker Hub push (--skip-push)"
fi

if [ "$SKIP_SANDBOX" -eq 0 ]; then
  echo "[INFO] Building sandbox worker images"
  if [ "$SKIP_PUSH" -eq 0 ]; then
    bash "$SCRIPT_DIR/build-sandbox-images.sh" 0
  else
    bash "$SCRIPT_DIR/build-sandbox-images.sh" 1
  fi
else
  echo "[INFO] Skipping sandbox images (--skip-sandbox)"
fi

if [ "$SKIP_DEB" -eq 0 ]; then
  bash "$SCRIPT_DIR/build-deb.sh"
else
  echo "[INFO] Skipping Debian package build (--skip-deb)"
fi

if [ "$DEV_RUN" -eq 1 ]; then
  echo "[INFO] Starting local dev container"
  exec bash "$SCRIPT_DIR/run.sh" "$VERSION"
fi

echo "[DONE] build.sh finished (version=$VERSION)"
