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
DEFAULT_SECRETS_PATH="${DATA_DIR}/secrets"
PREPARE_LAYOUT="${LIB_DIR}/prepare_project_layout.py"
ENSURE_SSH_TARGET="${LIB_DIR}/ensure-ssh-target-user.sh"

host_execution_secrets_path() {
  local default_path="$DEFAULT_SECRETS_PATH"
  if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY' "$CONFIG_FILE" "$default_path"
import json
import sys
from pathlib import Path

cfg_path, default = sys.argv[1], sys.argv[2]
try:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    print(default)
    raise SystemExit(0)
he = (cfg.get("terminal") or {}).get("host_execution") or {}
raw = he.get("secrets_path")
print(raw.strip() if isinstance(raw, str) and raw.strip() else default)
PY
    return 0
  fi
  printf '%s\n' "$default_path"
}

ensure_root_authorized_keys() {
  install -d -o root -g root -m 0700 /root/.ssh
  touch /root/.ssh/authorized_keys
  chown root:root /root/.ssh /root/.ssh/authorized_keys
  chmod 0700 /root/.ssh
  chmod 0600 /root/.ssh/authorized_keys
}

ensure_pubkey_for_root() {
  local pub_file="$1"
  local line marker auth tmp
  auth="/root/.ssh/authorized_keys"
  line="$(tr -d '\r\n' < "$pub_file")"
  [ -n "$line" ] || return 0

  if grep -qxF "$line" "$auth" 2>/dev/null; then
    return 0
  fi

  marker="$(printf '%s\n' "$line" | grep -oE 'mcp-term-session=[0-9a-fA-F-]{36}' | head -1 || true)"
  if [ -n "$marker" ] && grep -qF "$marker" "$auth" 2>/dev/null; then
    tmp="$(mktemp "${auth}.XXXXXX")"
    grep -vF "$marker" "$auth" > "$tmp" || true
    cat "$tmp" > "$auth"
    rm -f "$tmp"
  fi

  printf '%s\n' "$line" >> "$auth"
  chown root:root "$auth"
  chmod 0600 "$auth"
}

sync_host_exec_keys_to_root() {
  local secrets_path="$1"
  local pub_file count=0
  ensure_root_authorized_keys
  while IFS= read -r pub_file; do
    [ -n "$pub_file" ] || continue
    ensure_pubkey_for_root "$pub_file"
    count=$((count + 1))
  done < <(find "$secrets_path" -type f -path '*/.ssh/session_ed25519.pub' 2>/dev/null | sort)
  if [ "$count" -gt 0 ]; then
    echo "[INFO] Ensured ${count} host-exec public key(s) in /root/.ssh/authorized_keys"
  fi
}

ensure_stable_host_exec_key() {
  local secrets_path="$1"
  local key_dir private public marker
  key_dir="${secrets_path}/host_exec/.ssh"
  private="${key_dir}/session_ed25519"
  public="${private}.pub"
  marker="mcp-term-session=00000000-0000-4000-8000-000000000000 host_exec"

  install -d -o root -g root -m 0700 "$key_dir"
  if [ ! -f "$private" ]; then
    if ! command -v ssh-keygen >/dev/null 2>&1; then
      echo "[WARN] ssh-keygen missing; cannot create stable host-exec key" >&2
      return 0
    fi
    ssh-keygen -q -t ed25519 -N "" -C "$marker" -f "$private"
  fi
  chown root:root "$key_dir" "$private" 2>/dev/null || true
  chmod 0700 "$key_dir"
  chmod 0600 "$private"
  if [ -f "$public" ]; then
    chown root:root "$public"
    chmod 0644 "$public"
  fi
}

fix_host_exec_secrets_permissions() {
  local secrets_path
  secrets_path="$(host_execution_secrets_path)"
  if [ -z "$secrets_path" ]; then
    secrets_path="$DEFAULT_SECRETS_PATH"
  fi

  install -d -o root -g root -m 0700 "$secrets_path"
  chown root:root "$secrets_path"
  chmod 0700 "$secrets_path"

  find "$secrets_path" -type d -exec chown root:root {} +
  find "$secrets_path" -type d -exec chmod 0700 {} +
  find "$secrets_path" -type f -name 'session_ed25519' -exec chown root:root {} +
  find "$secrets_path" -type f -name 'session_ed25519' -exec chmod 0600 {} +
  find "$secrets_path" -type f -name 'session_ed25519.pub' -exec chown root:root {} +
  find "$secrets_path" -type f -name 'session_ed25519.pub' -exec chmod 0644 {} +

  ensure_stable_host_exec_key "$secrets_path"
  sync_host_exec_keys_to_root "$secrets_path"
}

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
  fix_host_exec_secrets_permissions
  fix_mtls_permissions
  prepare_watch_and_projects
  verify_service_container_access

  echo "[SUCCESS] Host permissions normalized (service container user=${MCP_TERMINAL_CONTAINER_USER})"
}

main "$@"
