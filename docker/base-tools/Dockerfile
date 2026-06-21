# Sandbox image profile: base_tools
# Published as <docker-user>/mcp-terminal-base-tools:latest (see docker/sandbox_images.sh)

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        gawk \
        grep \
        jq \
        procps \
        sed \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
