# Sandbox image profile: node_dev_20
# Published as <docker-user>/mcp-terminal-node-dev:20 (see docker/sandbox_images.sh)

FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fd-find \
        git \
        iproute2 \
        jq \
        less \
        lsof \
        make \
        net-tools \
        openssl \
        pkg-config \
        procps \
        ripgrep \
        tree \
        wget \
        yq \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
