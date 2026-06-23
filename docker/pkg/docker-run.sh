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
MCP_TERMINAL_CONTAINER_USER="${MCP_TERMINAL_CONTAINER_USER:-root}"
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

ensure_host_ssh_prereqs() {
  local config="${CONFIG_DIR}/${CONFIG_FILE}"
  if [ "$(id -u)" -ne 0 ]; then
    return 0
  fi
  if [ -x "${LIB_DIR}/ensure-ssh-target-user.sh" ]; then
    "${LIB_DIR}/ensure-ssh-target-user.sh" || true
  fi
  if [ -f "$config" ] && command -v python3 >/dev/null 2>&1; then
    local kh_path
    kh_path="$(python3 - <<'PY' "$config"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
he = (cfg.get("terminal") or {}).get("host_execution") or {}
ssh = he.get("ssh") or {}
print(ssh.get("known_hosts_path") or "/etc/mcp-terminal/ssh_known_hosts")
PY
)"
    if [ -n "$kh_path" ] && [ ! -f "$kh_path" ]; then
      install -d -o root -g root -m 755 "$(dirname "$kh_path")"
      touch "$kh_path"
      chmod 644 "$kh_path"
      echo "[WARN] Created empty ${kh_path}; pin host SSH key before enabling host_execution" >&2
    fi
  fi
  if [ -x "${LIB_DIR}/ensure-host-permissions.sh" ]; then
    "${LIB_DIR}/ensure-host-permissions.sh"
  fi
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
  if [ "${MCP_TERMINAL_AUTO_BIND_WATCH_DIRS:-1}" = "1" ] \
    && [ -f "${CONFIG_DIR}/${CONFIG_FILE}" ] \
    && [ -f "${LIB_DIR}/watch_dir_bind_specs.py" ]; then
    while IFS= read -r spec; do
      [ -n "$spec" ] || continue
      args+=(-v "$spec")
    done < <(python3 "${LIB_DIR}/watch_dir_bind_specs.py" \
      "${CONFIG_DIR}/${CONFIG_FILE}" "$EXTRA_BINDS")
  fi
  if [ "${#args[@]}" -gt 0 ]; then
    printf '%s\n' "${args[@]}"
  fi
}

container_create() {
  local -a docker_opts bind_extra

  if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] docker-run.sh must run as root (watch_dir bind-mounts and project chown require root)" >&2
    exit 1
  fi

  ensure_host_owner
  ensure_host_ssh_prereqs

  mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$DATA_DIR" "$MTLS_DIR"
  if [ -x "${LIB_DIR}/ensure-host-permissions.sh" ]; then
    "${LIB_DIR}/ensure-host-permissions.sh"
  fi

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
    -v /etc/passwd:/etc/passwd:ro
    -v /etc/group:/etc/group:ro
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

  if [ -f /etc/mcp-terminal/ssh_known_hosts ]; then
    docker_opts+=(-v /etc/mcp-terminal/ssh_known_hosts:/etc/mcp-terminal/ssh_known_hosts:ro)
  fi
  for host_script in manage-session-keys.sh ensure-ssh-target-user.sh; do
    if [ -f "${LIB_DIR}/${host_script}" ]; then
      docker_opts+=(-v "${LIB_DIR}/${host_script}:${LIB_DIR}/${host_script}:ro")
    fi
  done
  local ssh_target_home="/var/lib/mcp-terminal-host"
  if [ -d "$ssh_target_home" ]; then
    docker_opts+=(-v "${ssh_target_home}:${ssh_target_home}")
  fi

  if [ "${MCP_TERMINAL_CONTAINER_USER:-root}" != "root" ]; then
    docker_opts+=(--user "${MCP_TERMINAL_UID}:${MCP_TERMINAL_GID}")
  fi

  if [ "${MCP_TERMINAL_MOUNT_HOST_DOCKER:-1}" = "1" ]; then
    local host_docker="/usr/bin/docker"
    if [ -x "$host_docker" ]; then
      docker_opts+=(-v "${host_docker}:${host_docker}:ro")
    else
      echo "[WARN] Host docker CLI not found at ${host_docker}; sandbox may fail on Engine 29+" >&2
    fi
  fi

  if [ "${#sandbox_env[@]}" -gt 0 ]; then
    docker_opts+=("${sandbox_env[@]}")
  fi

  if [ -n "$NETWORK" ]; then
    docker_opts+=(--network "$NETWORK")
  fi

  if [ "${#bind_extra[@]}" -gt 0 ]; then
    docker_opts+=("${bind_extra[@]}")
    echo "[INFO] Extra bind mounts: ${#bind_extra[@]} volume(s) (watch_dirs auto-bind=${MCP_TERMINAL_AUTO_BIND_WATCH_DIRS:-1})"
  fi

  echo "[INFO] Creating container (image=$IMAGE_NAME, port=$PORT, user=${MCP_TERMINAL_CONTAINER_USER:-root}, docker.sock mounted)"
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
  if [ "$(id -u)" -eq 0 ] && [ -x "${LIB_DIR}/ensure-host-permissions.sh" ]; then
    "${LIB_DIR}/ensure-host-permissions.sh" || exit 1
  fi
  if [ "$(id -u)" -eq 0 ]; then
    ensure_host_ssh_prereqs || true
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
