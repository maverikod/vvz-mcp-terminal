#!/bin/bash
# Ensure MCP_TERMINAL_USER / MCP_TERMINAL_GROUP exist on the host.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

ensure_mcp_terminal_host_user() {
  local user="${MCP_TERMINAL_USER:-mcp-terminal}"
  local group="${MCP_TERMINAL_GROUP:-mcp-terminal}"

  if ! getent group "$group" >/dev/null 2>&1; then
    if command -v addgroup >/dev/null 2>&1; then
      echo "[INFO] Creating system group: ${group}"
      addgroup --system "$group"
    else
      echo "[ERROR] Group not found and addgroup unavailable: ${group}" >&2
      return 1
    fi
  fi

  if ! getent passwd "$user" >/dev/null 2>&1; then
    if command -v adduser >/dev/null 2>&1; then
      echo "[INFO] Creating system user: ${user} (group ${group})"
      adduser --system --ingroup "$group" --home /var/lib/mcp-terminal \
        --no-create-home --disabled-login --disabled-password "$user"
    else
      echo "[ERROR] User not found and adduser unavailable: ${user}" >&2
      return 1
    fi
  fi

  MCP_TERMINAL_UID="$(id -u "$user")"
  MCP_TERMINAL_GID="$(id -g "$group")"
  export MCP_TERMINAL_USER="$user" MCP_TERMINAL_GROUP="$group" MCP_TERMINAL_UID MCP_TERMINAL_GID

  if getent group docker >/dev/null 2>&1; then
    if id -nG "$user" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
      :
    elif command -v usermod >/dev/null 2>&1; then
      echo "[INFO] Adding ${user} to docker group for sandbox docker.sock access"
      usermod -aG docker "$user" 2>/dev/null || true
    fi
  fi

  for group_name in ${MCP_TERMINAL_EXTRA_GROUPS:-}; do
    [ -n "$group_name" ] || continue
    if id -nG "$user" 2>/dev/null | tr ' ' '\n' | grep -qx "$group_name"; then
      continue
    fi
    if getent group "$group_name" >/dev/null 2>&1 && command -v usermod >/dev/null 2>&1; then
      echo "[INFO] Adding ${user} to group ${group_name}"
      usermod -aG "$group_name" "$user" 2>/dev/null || true
    fi
  done

  return 0
}
