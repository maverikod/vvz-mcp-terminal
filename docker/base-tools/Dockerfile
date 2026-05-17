# Sandbox image profile: base_tools
# Published as ghcr.io/mcp-terminal/base-tools:latest

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
