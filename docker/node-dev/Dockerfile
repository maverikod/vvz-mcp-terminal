# Sandbox image profile: node_dev_20
# Published as ghcr.io/mcp-terminal/node-dev:20

FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
