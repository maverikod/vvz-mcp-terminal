# Sandbox image profile: base_tools
# Published as <docker-user>/mcp-terminal-base-tools:latest (see docker/sandbox_images.sh)

FROM debian:bookworm-slim

# Docker CLI for sandbox image builds (DOCKER_HOST -> fleet dind daemon).
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        fd-find \
        gawk \
        git \
        grep \
        iproute2 \
        jq \
        less \
        lsof \
        net-tools \
        openssh-client \
        openssl \
        procps \
        ripgrep \
        sed \
        tree \
        wget \
        yq \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
