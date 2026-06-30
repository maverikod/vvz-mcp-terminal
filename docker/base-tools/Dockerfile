# Sandbox image profile: base_tools
# Published as <docker-user>/mcp-terminal-base-tools:latest (see docker/sandbox_images.sh)

FROM debian:bookworm-slim

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
