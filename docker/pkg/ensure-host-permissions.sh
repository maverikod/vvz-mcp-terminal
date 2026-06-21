#!/bin/bash
# Normalize host permissions for mcp-terminal-docker (postinst, recreate, sync).
#
# Must run as root. Bind-mounting foreign watch directories and chown on project
# trees requires root on the host — there is no unprivileged alternative.
#
# Sets:
#   - sudoers/mTLS for the service container
#   - log/data/config dirs
#   - watch_dirs mount paths (verify) and project .terminals/ ownership
#
# Usage: ensure-host-permissions.sh
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f /etc/default/mcp-terminal ] && . /etc/default/mcp-terminal

MCP_TERMINAL_USER="${MCP_TERMINAL_USER:-mcp-terminal}"
MCP_TERMINAL_GROUP="${MCP_TERMINAL_GROUP:-mcp-terminal}"
MCP_TERMINAL_CONTAINER_USER="${MCP_TERMINAL_CONTAINER_USER:-root}"
CONFIG_DIR="${MCP_TERMINAL_CONFIG_DIR:-/etc/mcp-terminal}"
CONFIG_FILE="${CONFIG_DIR}/${MCP_TERMINAL_CONFIG_FILE:-term_server.json}"
LOG_DIR="${MCP_TERMINAL_LOG_DIR:-/var/log/mcp-terminal}"
DATA_DIR="${MCP_TERMINAL_DATA_DIR:-/var/mcp-terminal}"
MTLS_DIR="${MCP_TERMINAL_MTLS_DIR:-/etc/mcp-terminal/mtls_certificates}"
SUDOERS_PATH="${MCP_TERMINAL_SUDOERS_FILE:-/etc/sudoers.d/mcp-terminal}"
PREPARE_LAYOUT="${LIB_DIR}/prepare_project_layout.py"

fix_sudoers_permissions() {
  [ -f "$SUDOERS_PATH" ] || return 0
  chown root:"$MCP_TERMINAL_GROUP" "$SUDOERS_PATH"
  chmod 0640 "$SUDOERS_PATH"
}

fix_mtls_permissions() {
  [ -d "$MTLS_DIR" ] || return 0
  chown -R root:"$MCP_TERMINAL_GROUP" "$MTLS_DIR"
  find "$MTLS_DIR" -type d -exec chmod 0750 {} +
  find "$MTLS_DIR" -type f -name '*.key' -exec chmod 0640 {} +
  find "$MTLS_DIR" -type f ! -name '*.key' -exec chmod 0644 {} +
  if [ -f "${MTLS_DIR}/ca/ca.key" ]; then
    chmod 0600 "${MTLS_DIR}/ca/ca.key"
    chown root:"$MCP_TERMINAL_GROUP" "${MTLS_DIR}/ca/ca.key"
  fi
}

fix_runtime_dirs() {
  install -d -o root -g root -m 0755 "$LOG_DIR"
  install -d -o root -g root -m 0755 "$DATA_DIR"
  install -d -o root -g root -m 0755 "$CONFIG_DIR"
  install -d -o root -g root -m 0755 /var/lib/mcp-terminal
  if [ -f "$CONFIG_FILE" ]; then
    chown root:"$MCP_TERMINAL_GROUP" "$CONFIG_FILE" 2>/dev/null || chown root:root "$CONFIG_FILE"
    chmod 0644 "$CONFIG_FILE"
  fi
}

prepare_watch_and_projects() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "[INFO] Skipping watch/project layout (config missing: ${CONFIG_FILE})"
    return 0
  fi
  if [ ! -f "$PREPARE_LAYOUT" ]; then
    echo "[WARN] ${PREPARE_LAYOUT} missing; skip project .terminals prep" >&2
    return 0
  fi
  python3 "$PREPARE_LAYOUT" "$CONFIG_FILE"
}

verify_service_container_access() {
  local reader="$MCP_TERMINAL_CONTAINER_USER"
  if [ "$reader" = "root" ]; then
    reader="root"
  else
    reader="$MCP_TERMINAL_USER"
  fi

  if [ -f "$SUDOERS_PATH" ]; then
    if ! runuser -u "$reader" -- test -r "$SUDOERS_PATH" 2>/dev/null; then
      echo "[WARN] ${SUDOERS_PATH} not readable by ${reader}" >&2
    fi
  fi

  local sample_key
  sample_key="$(find "$MTLS_DIR" -type f -name '*.key' 2>/dev/null | head -1 || true)"
  if [ -n "$sample_key" ]; then
    if ! runuser -u "$reader" -- test -r "$sample_key" 2>/dev/null; then
      echo "[WARN] mTLS key not readable by ${reader}: ${sample_key}" >&2
    fi
  fi
}

main() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] ensure-host-permissions.sh must run as root" >&2
    return 1
  fi

  # shellcheck source=ensure-host-user.sh
  . "${LIB_DIR}/ensure-host-user.sh"
  ensure_mcp_terminal_host_user

  fix_runtime_dirs
  fix_sudoers_permissions
  fix_mtls_permissions
  prepare_watch_and_projects
  verify_service_container_access

  echo "[SUCCESS] Host permissions normalized (service container user=${MCP_TERMINAL_CONTAINER_USER})"
}

main "$@"
