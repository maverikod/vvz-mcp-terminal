# Sandbox image profile: node_dev_20
# Published as <docker-user>/mcp-terminal-node-dev:20 (see docker/sandbox_images.sh)

FROM node:20-bookworm-slim

# Docker CLI for sandbox image builds (DOCKER_HOST -> fleet dind daemon).
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

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
        openssh-client \
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
