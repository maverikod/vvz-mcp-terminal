# Sandbox image profile: python_dev_3_12
# Published as <docker-user>/mcp-terminal-python-dev:3.12 (see docker/sandbox_images.sh)
#
# procps provides ps/pgrep/pkill required for host-PID discovery (e.g. casmgr status
# with pid_namespace=host) and for in-sandbox process diagnostics (tech_spec §13.1).
#
# Host-created .venv often symlinks bin/python -> /usr/bin/python. The official image
# only installs python under /usr/local/bin. Do not use apt python-is-python3 here:
# it pulls Debian python3.11 into /usr/bin and breaks 3.12 venv site-packages.
# Symlink /usr/bin/python(3) to the image interpreter instead.

FROM python:3.12-slim-bookworm

# Docker CLI for sandbox image builds. The client talks to the fleet dind
# daemon via DOCKER_HOST (runtime.docker_host, injected by terminal_run);
# the host docker daemon stays unreachable from sandboxes.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        diffutils \
        fd-find \
        file \
        gawk \
        git \
        htop \
        iproute2 \
        jq \
        less \
        lsof \
        make \
        nano \
        net-tools \
        openssh-client \
        openssl \
        patch \
        p7zip-full \
        pkg-config \
        procps \
        psmisc \
        ripgrep \
        rsync \
        sqlite3 \
        tree \
        unzip \
        vim-tiny \
        wget \
        xz-utils \
        yq \
        zip \
    && ln -sf /usr/local/bin/python3 /usr/bin/python3 \
    && ln -sf /usr/local/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
        bandit \
        black \
        build \
        coverage \
        flake8 \
        ipython \
        isort \
        mypy \
        nox \
        pip-audit \
        pip-tools \
        pipdeptree \
        pre-commit \
        pylint \
        pytest \
        pytest-cov \
        radon \
        ruff \
        tox \
        wheel \
        vulture

# Contract: agents must be able to create project-local virtualenvs in the sandbox.
# Use the official Python image's stdlib venv/ensurepip; do not apt-install
# python3-venv here because Debian bookworm would add Python 3.11 beside 3.12.
RUN python -m venv /tmp/mcp-terminal-venv-smoke \
    && /tmp/mcp-terminal-venv-smoke/bin/python -m pip --version \
    && rm -rf /tmp/mcp-terminal-venv-smoke

WORKDIR /workspace
