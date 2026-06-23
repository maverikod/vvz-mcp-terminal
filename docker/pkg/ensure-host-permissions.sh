#!/bin/bash
# Normalize host permissions for mcp-terminal-docker (postinst, recreate).
#
# Must run as root. Bind-mounting foreign watch directories and chown on project
# trees requires root on the host — there is no unprivileged alternative.
#
# Sets:
#   - SSH host-execution prerequisites (known_hosts, target user home)
#   - mTLS for the service container
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
MCP_TERMINAL_SSH_TARGET_USER="${MCP_TERMINAL_SSH_TARGET_USER:-mcp-terminal-host}"
CONFIG_DIR="${MCP_TERMINAL_CONFIG_DIR:-/etc/mcp-terminal}"
CONFIG_FILE="${CONFIG_DIR}/${MCP_TERMINAL_CONFIG_FILE:-term_server.json}"
LOG_DIR="${MCP_TERMINAL_LOG_DIR:-/var/log/mcp-terminal}"
DATA_DIR="${MCP_TERMINAL_DATA_DIR:-/var/mcp-terminal}"
MTLS_DIR="${MCP_TERMINAL_MTLS_DIR:-/etc/mcp-terminal/mtls_certificates}"
DEFAULT_KNOWN_HOSTS="${CONFIG_DIR}/ssh_known_hosts"
PREPARE_LAYOUT="${LIB_DIR}/prepare_project_layout.py"
ENSURE_SSH_TARGET="${LIB_DIR}/ensure-ssh-target-user.sh"

fix_ssh_host_exec_prereqs() {
  local kh_path="$DEFAULT_KNOWN_HOSTS"
  if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    kh_path="$(python3 - <<'PY' "$CONFIG_FILE" "$DEFAULT_KNOWN_HOSTS"
import json, sys
from pathlib import Path
cfg_path, default = sys.argv[1], sys.argv[2]
try:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    print(default)
    raise SystemExit(0)
he = (cfg.get("terminal") or {}).get("host_execution") or {}
ssh = he.get("ssh") or {}
print(ssh.get("known_hosts_path") or default)
PY
)"
  fi
  install -d -o root -g root -m 755 "$(dirname "$kh_path")"
  if [ ! -f "$kh_path" ]; then
    touch "$kh_path"
  fi
  chown root:root "$kh_path"
  chmod 0644 "$kh_path"

  if [ -x "$ENSURE_SSH_TARGET" ]; then
    MCP_TERMINAL_SSH_TARGET_USER="$MCP_TERMINAL_SSH_TARGET_USER" "$ENSURE_SSH_TARGET"
  fi

  local home=""
  if getent passwd "$MCP_TERMINAL_SSH_TARGET_USER" >/dev/null 2>&1; then
    home="$(getent passwd "$MCP_TERMINAL_SSH_TARGET_USER" | cut -d: -f6)"
    if [ -n "$home" ] && [ -d "${home}/.ssh" ]; then
      chown -R "${MCP_TERMINAL_SSH_TARGET_USER}:${MCP_TERMINAL_SSH_TARGET_USER}" "${home}/.ssh"
      chmod 0700 "${home}/.ssh"
      if [ -f "${home}/.ssh/authorized_keys" ]; then
        chmod 0600 "${home}/.ssh/authorized_keys"
      fi
    fi
  fi
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

  local kh_path="$DEFAULT_KNOWN_HOSTS"
  if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    kh_path="$(python3 - <<'PY' "$CONFIG_FILE" "$DEFAULT_KNOWN_HOSTS"
import json, sys
from pathlib import Path
cfg_path, default = sys.argv[1], sys.argv[2]
try:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    print(default)
    raise SystemExit(0)
he = (cfg.get("terminal") or {}).get("host_execution") or {}
ssh = he.get("ssh") or {}
print(ssh.get("known_hosts_path") or default)
PY
)"
  fi
  if [ -f "$kh_path" ]; then
    if ! runuser -u "$reader" -- test -r "$kh_path" 2>/dev/null; then
      echo "[WARN] ${kh_path} not readable by ${reader}" >&2
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
  fix_ssh_host_exec_prereqs
  fix_mtls_permissions
  prepare_watch_and_projects
  verify_service_container_access

  echo "[SUCCESS] Host permissions normalized (service container user=${MCP_TERMINAL_CONTAINER_USER})"
}

main "$@"
