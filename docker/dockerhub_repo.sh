#!/bin/bash
# Resolve Docker Hub image repository for mcp-terminal builds.
# shellcheck shell=bash

# Priority: MCP_TERMINAL_DOCKERHUB_REPO > docker logged-in Username > MCP_TERMINAL_DOCKERHUB_USERNAME > vasilyvz
dockerhub_repo_default() {
  if [ -n "${MCP_TERMINAL_DOCKERHUB_REPO:-}" ]; then
    printf '%s\n' "$MCP_TERMINAL_DOCKERHUB_REPO"
    return 0
  fi
  local user=""
  if command -v docker >/dev/null 2>&1; then
    user="$(docker info 2>/dev/null | sed -n 's/^ Username: //p' | head -1 | tr -d '[:space:]')"
  fi
  if [ -z "$user" ] && [ -n "${MCP_TERMINAL_DOCKERHUB_USERNAME:-}" ]; then
    user="$MCP_TERMINAL_DOCKERHUB_USERNAME"
  fi
  if [ -z "$user" ]; then
    user="vasilyvz"
  fi
  printf '%s/mcp-terminal\n' "$user"
}

dockerhub_logged_in_user() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  docker info 2>/dev/null | sed -n 's/^ Username: //p' | head -1 | tr -d '[:space:]'
}
