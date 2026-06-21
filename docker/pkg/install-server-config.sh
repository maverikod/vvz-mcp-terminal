#!/bin/bash
# Install or refresh mcp-terminal term_server.json (postinst / admin helper).
#
# The Debian package does NOT ship /etc/mcp-terminal/term_server.json — only the
# template under /usr/share/mcp-terminal/. This script is the sole writer of the
# live config:
#
# - term_server.json missing     → create from shipped template (+ instance UUID)
# - term_server.json present, still pristine (REPLACE_ON_INSTALL) → finalize UUID only
# - term_server.json present, customized → leave unchanged; refresh template alongside
#
# Usage: install-server-config.sh CONFIG_DIR TEMPLATE_DOC [GROUP]

set -euo pipefail

CONFIG_DIR="${1:?CONFIG_DIR required}"
TEMPLATE_DOC="${2:?TEMPLATE_DOC required}"
MCP_TERMINAL_GROUP="${3:-mcp-terminal}"

CONFIG="${CONFIG_DIR}/term_server.json"
CONFIG_TEMPLATE_LOCAL="${CONFIG_DIR}/term_server.json.template"
SYNC_SUDO="${SYNC_SUDO:-/usr/lib/mcp-terminal/sync-host-sudo.sh}"
if [ -x "$(dirname "$0")/sync-host-sudo.sh" ]; then
  SYNC_SUDO="$(cd "$(dirname "$0")" && pwd)/sync-host-sudo.sh"
fi

_run_sync_host_sudo() {
  if [ "$(id -u)" -ne 0 ]; then
    return 0
  fi
  if [ ! -x "$SYNC_SUDO" ] || [ ! -f "$CONFIG" ]; then
    return 0
  fi
  echo "[INFO] Refreshing host sudoers from ${CONFIG} ..."
  "$SYNC_SUDO" "$CONFIG"
}

_resolve_template_source() {
  local primary="$1"
  if [ -f "$primary" ]; then
    printf '%s\n' "$primary"
    return 0
  fi
  if [ -f "${primary}.gz" ]; then
    printf '%s\n' "${primary}.gz"
    return 0
  fi
  return 1
}

_copy_template_to() {
  local src="$1" dest="$2"
  if [[ "$src" == *.gz ]]; then
    zcat "$src" >"$dest"
  else
    cp "$src" "$dest"
  fi
}

TEMPLATE_SRC="$(_resolve_template_source "$TEMPLATE_DOC" || true)"
if [ -z "${TEMPLATE_SRC:-}" ]; then
  echo "ERROR: template not found: ${TEMPLATE_DOC} (or ${TEMPLATE_DOC}.gz)" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"

_finalize_instance_uuid() {
  if command -v uuidgen >/dev/null 2>&1; then
    local instance_uuid
    instance_uuid="$(uuidgen)"
    sed -i "s/REPLACE_ON_INSTALL/${instance_uuid}/" "$CONFIG"
  fi
}

if [ -f "$CONFIG" ]; then
  if grep -q 'REPLACE_ON_INSTALL' "$CONFIG" 2>/dev/null; then
    _finalize_instance_uuid
    if [ "$(id -u)" -eq 0 ]; then
      chown root:"$MCP_TERMINAL_GROUP" "$CONFIG" 2>/dev/null || chown root:root "$CONFIG"
    fi
    chmod 644 "$CONFIG"
    echo "Finalized new ${CONFIG} from package template"
    _run_sync_host_sudo
    exit 0
  fi
  _copy_template_to "$TEMPLATE_SRC" "$CONFIG_TEMPLATE_LOCAL"
  if [ "$(id -u)" -eq 0 ]; then
    chown root:"$MCP_TERMINAL_GROUP" "$CONFIG_TEMPLATE_LOCAL" 2>/dev/null || chown root:root "$CONFIG_TEMPLATE_LOCAL"
  fi
  chmod 644 "$CONFIG_TEMPLATE_LOCAL"
  echo "Preserved existing ${CONFIG}; new package template at ${CONFIG_TEMPLATE_LOCAL}"
  _run_sync_host_sudo
  exit 0
fi

_copy_template_to "$TEMPLATE_SRC" "$CONFIG"
_finalize_instance_uuid
if [ "$(id -u)" -eq 0 ]; then
  chown root:"$MCP_TERMINAL_GROUP" "$CONFIG" 2>/dev/null || chown root:root "$CONFIG"
fi
chmod 644 "$CONFIG"
echo "Installed new ${CONFIG} from package template"
_run_sync_host_sudo
