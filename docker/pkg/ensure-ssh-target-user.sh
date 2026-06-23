#!/bin/bash
# Create SSH target user(s) with ~/.ssh for host execution platzdarm.
set -euo pipefail

ensure_ssh_target_user() {
  local user="${MCP_TERMINAL_SSH_TARGET_USER:-mcp-terminal-host}"
  local group="${MCP_TERMINAL_SSH_TARGET_GROUP:-$user}"

  if ! getent group "$group" >/dev/null 2>&1; then
    groupadd --system "$group" 2>/dev/null || true
  fi
  if ! id "$user" >/dev/null 2>&1; then
    useradd --system --gid "$group" --home "/var/lib/${user}" \
      --create-home --shell /usr/sbin/nologin "$user"
  fi
  local home
  home="$(getent passwd "$user" | cut -d: -f6)"
  mkdir -p "${home}/.ssh"
  chown "${user}:${group}" "${home}/.ssh"
  chmod 0700 "${home}/.ssh"
  touch "${home}/.ssh/authorized_keys"
  chown "${user}:${group}" "${home}/.ssh/authorized_keys"
  chmod 0600 "${home}/.ssh/authorized_keys"
}

ensure_ssh_target_user "$@"
