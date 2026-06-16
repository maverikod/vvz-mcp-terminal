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
  return 0
}
