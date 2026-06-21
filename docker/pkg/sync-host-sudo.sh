#!/bin/bash
# Generate /etc/sudoers.d/mcp-terminal from term_server.json host_execution config.
# Must run as root. Validates with visudo before installing.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

# shellcheck source=/dev/null
[ -f /etc/default/mcp-terminal ] && . /etc/default/mcp-terminal

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f /etc/default/mcp-terminal ] && . /etc/default/mcp-terminal

MCP_TERMINAL_GROUP="${MCP_TERMINAL_GROUP:-mcp-terminal}"
CONFIG_DIR="${MCP_TERMINAL_CONFIG_DIR:-/etc/mcp-terminal}"
CONFIG_BASENAME="${MCP_TERMINAL_CONFIG_FILE:-term_server.json}"
CONFIG_FILE="${1:-${CONFIG_DIR}/${CONFIG_BASENAME}}"
SUDOERS_PATH="${MCP_TERMINAL_SUDOERS_FILE:-/etc/sudoers.d/mcp-terminal}"
SUDOERS_TMP="$(mktemp)"

cleanup() {
  rm -f "$SUDOERS_TMP"
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] sync-host-sudo.sh must run as root" >&2
  exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[ERROR] Config not found: $CONFIG_FILE" >&2
  exit 1
fi

if ! command -v visudo >/dev/null 2>&1; then
  echo "[ERROR] visudo not found (install sudo package)" >&2
  exit 1
fi

python3 "${LIB_DIR}/sync_host_sudo_lib.py" "$CONFIG_FILE" >"$SUDOERS_TMP"

install -d -o root -g root -m 750 /etc/sudoers.d
chmod 0640 "$SUDOERS_TMP"
if ! visudo -cf "$SUDOERS_TMP"; then
  echo "[ERROR] visudo rejected generated sudoers rules" >&2
  exit 1
fi
install -o root -g "$MCP_TERMINAL_GROUP" -m 0640 "$SUDOERS_TMP" "$SUDOERS_PATH"
echo "[SUCCESS] Installed ${SUDOERS_PATH}"

if [ -x "${LIB_DIR}/ensure-host-permissions.sh" ]; then
  "${LIB_DIR}/ensure-host-permissions.sh"
fi
