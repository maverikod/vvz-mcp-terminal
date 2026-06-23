#!/bin/bash
# Manage ephemeral session public keys in target user authorized_keys.
# Usage:
#   manage-session-keys.sh add   <user> <session_id> '<full pubkey line>'
#   manage-session-keys.sh remove <user> <session_id>
#   manage-session-keys.sh reap  <user> '<comma-separated live session uuids>'
set -euo pipefail

ACTION="${1:?action required (add|remove|reap)}"
TARGET_USER="${2:?target user required}"
SESSION_ID="${3:?session id required}"
MARKER="mcp-term-session=${SESSION_ID}"

_home_dir() {
  local u="$1"
  getent passwd "$u" | cut -d: -f6
}

_auth_keys_path() {
  local home
  home="$(_home_dir "$1")"
  if [ -z "$home" ] || [ ! -d "$home" ]; then
    echo "unknown user: $1" >&2
    exit 1
  fi
  echo "${home}/.ssh/authorized_keys"
}

_ensure_ssh_dir() {
  local home="$1"
  local ssh_dir="${home}/.ssh"
  mkdir -p "$ssh_dir"
  chown "${TARGET_USER}:${TARGET_USER}" "$ssh_dir"
  chmod 0700 "$ssh_dir"
}

_add_key() {
  local pubkey="$1"
  local home auth
  home="$(_home_dir "$TARGET_USER")"
  _ensure_ssh_dir "$home"
  auth="$(_auth_keys_path "$TARGET_USER")"
  touch "$auth"
  chown "${TARGET_USER}:${TARGET_USER}" "$auth"
  chmod 0600 "$auth"
  if grep -qF "$MARKER" "$auth" 2>/dev/null; then
    grep -vF "$MARKER" "$auth" > "${auth}.tmp" || true
    mv "${auth}.tmp" "$auth"
    chmod 0600 "$auth"
    chown "${TARGET_USER}:${TARGET_USER}" "$auth"
  fi
  printf '%s\n' "$pubkey" >> "$auth"
}

_remove_by_marker() {
  local auth
  auth="$(_auth_keys_path "$TARGET_USER")"
  [ -f "$auth" ] || exit 0
  if grep -qF "$MARKER" "$auth" 2>/dev/null; then
    grep -vF "$MARKER" "$auth" > "${auth}.tmp" || true
    mv "${auth}.tmp" "$auth"
    chmod 0600 "$auth"
    chown "${TARGET_USER}:${TARGET_USER}" "$auth"
  fi
}

_reap_keys() {
  local live_csv="$1"
  local auth home
  home="$(_home_dir "$TARGET_USER")"
  auth="${home}/.ssh/authorized_keys"
  [ -f "$auth" ] || exit 0
  python3 - "$auth" "$live_csv" <<'PY'
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

auth_path = Path(sys.argv[1])
live_csv = sys.argv[2]
live = {x.strip() for x in live_csv.split(",") if x.strip()}
marker_re = re.compile(r"mcp-term-session=([0-9a-fA-F-]{36})")
ttl_re = re.compile(r"ttl=([0-9T:.+-Z]+)")

def expired(comment: str) -> bool:
    m = ttl_re.search(comment)
    if not m:
        return False
    try:
        ts = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return ts < datetime.now(timezone.utc)

lines = auth_path.read_text(encoding="utf-8").splitlines()
kept = []
for line in lines:
    if not line.strip() or line.startswith("#"):
        kept.append(line)
        continue
    m = marker_re.search(line)
    if not m:
        kept.append(line)
        continue
    sid = m.group(1)
    if sid not in live or expired(line):
        continue
    kept.append(line)
auth_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
PY
  chown "${TARGET_USER}:${TARGET_USER}" "$auth"
  chmod 0600 "$auth"
}

case "$ACTION" in
  add)
    PUBKEY="${4:?public key line required for add}"
    _add_key "$PUBKEY"
    ;;
  remove)
    _remove_by_marker
    ;;
  reap)
    LIVE="${4:-}"
    _reap_keys "$LIVE"
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 1
    ;;
esac
