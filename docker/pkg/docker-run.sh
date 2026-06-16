#!/bin/bash
# Production Docker run helper for mcp-terminal-docker Debian package.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -e

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f /etc/default/mcp-terminal ] && . /etc/default/mcp-terminal
# shellcheck source=/dev/null
[ -f "${LIB_DIR}/image-spec" ] && . "${LIB_DIR}/image-spec"

MCP_TERMINAL_USER="${MCP_TERMINAL_USER:-mcp-terminal}"
MCP_TERMINAL_GROUP="${MCP_TERMINAL_GROUP:-mcp-terminal}"
CONTAINER_NAME="${MCP_TERMINAL_CONTAINER:-mcp-terminal}"
PORT="${MCP_TERMINAL_PORT:-3011}"
CONFIG_DIR="${MCP_TERMINAL_CONFIG_DIR:-/etc/mcp-terminal}"
CONFIG_FILE="${MCP_TERMINAL_CONFIG_FILE:-term_server.json}"
LOG_DIR="${MCP_TERMINAL_LOG_DIR:-/var/log/mcp-terminal}"
DATA_DIR="${MCP_TERMINAL_DATA_DIR:-/var/mcp-terminal}"
MTLS_DIR="${MCP_TERMINAL_MTLS_DIR:-/etc/mcp-terminal/mtls_certificates}"
NETWORK="${MCP_TERMINAL_NETWORK:-}"
EXTRA_BINDS="${MCP_TERMINAL_EXTRA_BINDS:-}"
IMAGE_SPEC="${LIB_DIR}/image-spec"
PULL_SANDBOX="${MCP_TERMINAL_PULL_SANDBOX_ON_RECREATE:-1}"

if [ -f "$IMAGE_SPEC" ]; then
  # shellcheck source=/dev/null
  . "$IMAGE_SPEC"
fi
IMAGE_NAME="$(printf '%s:%s' "${DOCKERHUB_REPO:-mcp-terminal}" "${IMAGE_TAG:-latest}")"

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

ensure_host_owner() {
  # shellcheck source=ensure-host-user.sh
  . "${LIB_DIR}/ensure-host-user.sh"
  ensure_mcp_terminal_host_user
}

pull_image_from_spec() {
  if [ ! -f "$IMAGE_SPEC" ]; then
    echo "[ERROR] image-spec missing: $IMAGE_SPEC" >&2
    return 1
  fi
  # shellcheck source=/dev/null
  . "$IMAGE_SPEC"
  if [ -z "${DOCKERHUB_REPO:-}" ] || [ -z "${IMAGE_TAG:-}" ]; then
    echo "[ERROR] DOCKERHUB_REPO/IMAGE_TAG not set in $IMAGE_SPEC" >&2
    return 1
  fi
  IMAGE_NAME="$(printf '%s:%s' "$DOCKERHUB_REPO" "$IMAGE_TAG")"
  ensure_docker_ready
  echo "[INFO] Pulling ${IMAGE_NAME} ..."
  if ! docker pull "$IMAGE_NAME"; then
    echo "[ERROR] docker pull failed for ${IMAGE_NAME}" >&2
    echo "[ERROR] If the repository is private, run: docker login" >&2
    return 1
  fi
}

pull_sandbox_if_requested() {
  if [ "$PULL_SANDBOX" != "1" ]; then
    return 0
  fi
  if [ -x "${LIB_DIR}/pull-sandbox-images.sh" ]; then
    "${LIB_DIR}/pull-sandbox-images.sh"
  fi
}

docker_ensure_network() {
  local net="$1"
  [ -n "$net" ] || return 0
  if docker network inspect "$net" >/dev/null 2>&1; then
    return 0
  fi
  echo "[INFO] Creating Docker network ${net}"
  docker network create "$net"
}

extra_bind_args() {
  local -a args=()
  local spec
  for spec in $EXTRA_BINDS; do
    [ -n "$spec" ] || continue
    args+=(-v "$spec")
  done
  if [ "${#args[@]}" -gt 0 ]; then
    printf '%s\n' "${args[@]}"
  fi
}

container_create() {
  local -a docker_opts bind_extra

  ensure_host_owner
  mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$DATA_DIR" "$MTLS_DIR"
  chown -R "${MCP_TERMINAL_USER}:${MCP_TERMINAL_GROUP}" "$LOG_DIR" "$DATA_DIR" 2>/dev/null || true
  chmod 755 "$LOG_DIR" "$DATA_DIR" 2>/dev/null || true

  if [ ! -f "${CONFIG_DIR}/${CONFIG_FILE}" ]; then
    echo "[ERROR] Config not found: ${CONFIG_DIR}/${CONFIG_FILE}" >&2
    exit 1
  fi

  docker_ensure_network "$NETWORK"
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

  mapfile -t bind_extra < <(extra_bind_args)

  local sandbox_spec="${LIB_DIR}/sandbox-images-spec"
  local -a sandbox_env=()
  if [ -f "$sandbox_spec" ]; then
    # shellcheck source=/dev/null
    . "$sandbox_spec"
    sandbox_env=(
      -e "MCP_TERMINAL_SANDBOX_IMAGE_PYTHON_DEV_3_12=${SANDBOX_IMAGE_python_dev_3_12:-}"
      -e "MCP_TERMINAL_SANDBOX_IMAGE_NODE_DEV_20=${SANDBOX_IMAGE_node_dev_20:-}"
      -e "MCP_TERMINAL_SANDBOX_IMAGE_BASE_TOOLS=${SANDBOX_IMAGE_base_tools:-}"
    )
  fi

  docker_opts=(
    --name "$CONTAINER_NAME"
    --shm-size "${MCP_TERMINAL_SHM_SIZE:-512m}"
    -v "${CONFIG_DIR}/${CONFIG_FILE}:/etc/mcp-terminal/term_server.json:ro"
    -v "${LOG_DIR}:/var/log/mcp-terminal"
    -v "${DATA_DIR}:/var/mcp-terminal"
    -v "${MTLS_DIR}:/etc/mcp-terminal/mtls_certificates:ro"
    -v /var/run/docker.sock:/var/run/docker.sock
    -p "${PORT}:3011"
    -e MCP_TERMINAL_SKIP_VENV_REEXEC=1
    -e MCP_TERMINAL_CONFIG_DIR=/etc/mcp-terminal
    -e MCP_TERMINAL_LOG_DIR=/var/log/mcp-terminal
    -e MCP_TERMINAL_DATA_DIR=/var/mcp-terminal
    -e MCP_TERMINAL_MTLS_DIR=/etc/mcp-terminal/mtls_certificates
    -e PYTHONUNBUFFERED=1
    --add-host host.docker.internal:host-gateway
    --restart=always
  )

  if [ "${#sandbox_env[@]}" -gt 0 ]; then
    docker_opts+=("${sandbox_env[@]}")
  fi

  if [ -n "$NETWORK" ]; then
    docker_opts+=(--network "$NETWORK")
  fi

  if [ "${#bind_extra[@]}" -gt 0 ]; then
    docker_opts+=("${bind_extra[@]}")
  fi

  echo "[INFO] Creating container (image=$IMAGE_NAME, port=$PORT, docker.sock mounted)"
  docker create "${docker_opts[@]}" "$IMAGE_NAME"
}

container_image_matches() {
  local current=""
  current="$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}' 2>/dev/null || true)"
  [ "$current" = "$IMAGE_NAME" ]
}

start_container() {
  docker start "$CONTAINER_NAME"
}

cmd_start() {
  local need_create=0
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    if ! container_image_matches; then
      echo "[INFO] Recreating $CONTAINER_NAME (image changed -> $IMAGE_NAME)"
      pull_image_from_spec
      docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
      need_create=1
    fi
  else
    need_create=1
  fi
  if [ "$need_create" = "1" ]; then
    if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
      pull_image_from_spec
    fi
    container_create
  fi
  start_container
  echo "[SUCCESS] Container $CONTAINER_NAME started (port=$PORT)"
}

cmd_stop() {
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
}

cmd_restart() {
  if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    cmd_start
    return
  fi
  cmd_stop
  docker start "$CONTAINER_NAME"
  echo "[SUCCESS] Container $CONTAINER_NAME restarted (same instance)"
}

cmd_recreate() {
  pull_image_from_spec
  pull_sandbox_if_requested
  cmd_stop
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  container_create
  start_container
  echo "[SUCCESS] Container $CONTAINER_NAME recreated (port=$PORT)"
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  recreate) cmd_recreate ;;
  pull) pull_image_from_spec ;;
  *)
    echo "Usage: $0 {start|stop|restart|recreate|pull}" >&2
    exit 1
    ;;
esac
