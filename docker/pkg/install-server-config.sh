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
ENSURE_SSH_TARGET="${ENSURE_SSH_TARGET:-/usr/lib/mcp-terminal/ensure-ssh-target-user.sh}"
if [ -x "$(dirname "$0")/ensure-ssh-target-user.sh" ]; then
  ENSURE_SSH_TARGET="$(cd "$(dirname "$0")" && pwd)/ensure-ssh-target-user.sh"
fi

_run_ensure_ssh_target() {
  if [ "$(id -u)" -ne 0 ]; then
    return 0
  fi
  if [ ! -x "$ENSURE_SSH_TARGET" ]; then
    return 0
  fi
  echo "[INFO] Ensuring SSH target user for terminal_host_exec ..."
  "$ENSURE_SSH_TARGET"
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
  local instance_uuid=""
  if command -v uuidgen >/dev/null 2>&1; then
    instance_uuid="$(uuidgen)"
  elif command -v python3 >/dev/null 2>&1; then
    instance_uuid="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"
  fi
  if [ -z "$instance_uuid" ]; then
    echo "[WARN] Could not generate registration.instance_uuid; leaving REPLACE_ON_INSTALL in place" >&2
    return 0
  fi
  sed -i \
    "0,/\"instance_uuid\": \"REPLACE_ON_INSTALL\"/s//\"instance_uuid\": \"${instance_uuid}\"/" \
    "$CONFIG"
}

_finalize_advertised_host() {
  sed -i \
    '0,/"advertised_host": "CHANGE_ME"/s//"advertised_host": "mcp-terminal"/' \
    "$CONFIG"
}

if [ -f "$CONFIG" ]; then
  if grep -q '"advertised_host": "CHANGE_ME"' "$CONFIG" 2>/dev/null; then
    _finalize_advertised_host
  fi
  if grep -q 'REPLACE_ON_INSTALL' "$CONFIG" 2>/dev/null; then
    _finalize_instance_uuid
    if [ "$(id -u)" -eq 0 ]; then
      chown root:"$MCP_TERMINAL_GROUP" "$CONFIG" 2>/dev/null || chown root:root "$CONFIG"
    fi
    chmod 644 "$CONFIG"
    echo "Finalized new ${CONFIG} from package template"
    _run_ensure_ssh_target
    exit 0
  fi
  _copy_template_to "$TEMPLATE_SRC" "$CONFIG_TEMPLATE_LOCAL"
  if [ "$(id -u)" -eq 0 ]; then
    chown root:"$MCP_TERMINAL_GROUP" "$CONFIG_TEMPLATE_LOCAL" 2>/dev/null || chown root:root "$CONFIG_TEMPLATE_LOCAL"
  fi
  chmod 644 "$CONFIG_TEMPLATE_LOCAL"
  echo "Preserved existing ${CONFIG}; new package template at ${CONFIG_TEMPLATE_LOCAL}"
  _run_ensure_ssh_target
  exit 0
fi

_copy_template_to "$TEMPLATE_SRC" "$CONFIG"
_finalize_advertised_host
_finalize_instance_uuid
if [ "$(id -u)" -eq 0 ]; then
  chown root:"$MCP_TERMINAL_GROUP" "$CONFIG" 2>/dev/null || chown root:root "$CONFIG"
fi
chmod 644 "$CONFIG"
echo "Installed new ${CONFIG} from package template"
_run_ensure_ssh_target
