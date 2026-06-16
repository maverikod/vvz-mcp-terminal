#!/bin/bash
# Resolve full Docker image references for sandbox worker profiles.
# shellcheck shell=bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"

sandbox_repo_user() {
  if [ -n "${MCP_TERMINAL_SANDBOX_REPO_USER:-}" ]; then
    printf '%s\n' "$MCP_TERMINAL_SANDBOX_REPO_USER"
    return 0
  fi
  local repo
  repo="$(dockerhub_repo_default)"
  printf '%s\n' "${repo%%/*}"
}

sandbox_image_python_dev() {
  if [ -n "${MCP_TERMINAL_SANDBOX_IMAGE_PYTHON_DEV_3_12:-}" ]; then
    printf '%s\n' "$MCP_TERMINAL_SANDBOX_IMAGE_PYTHON_DEV_3_12"
    return 0
  fi
  printf '%s/mcp-terminal-python-dev:3.12\n' "$(sandbox_repo_user)"
}

sandbox_image_node_dev() {
  if [ -n "${MCP_TERMINAL_SANDBOX_IMAGE_NODE_DEV_20:-}" ]; then
    printf '%s\n' "$MCP_TERMINAL_SANDBOX_IMAGE_NODE_DEV_20"
    return 0
  fi
  printf '%s/mcp-terminal-node-dev:20\n' "$(sandbox_repo_user)"
}

sandbox_image_base_tools() {
  if [ -n "${MCP_TERMINAL_SANDBOX_IMAGE_BASE_TOOLS:-}" ]; then
    printf '%s\n' "$MCP_TERMINAL_SANDBOX_IMAGE_BASE_TOOLS"
    return 0
  fi
  printf '%s/mcp-terminal-base-tools:latest\n' "$(sandbox_repo_user)"
}
