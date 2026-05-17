# Sandbox image profile: python_dev_3_12
# Published as ghcr.io/mcp-terminal/python-dev:3.12
#
# procps provides ps/pgrep/pkill required for host-PID discovery (e.g. casmgr status
# with pid_namespace=host) and for in-sandbox process diagnostics (tech_spec §13.1).
#
# Host-created .venv often symlinks bin/python -> /usr/bin/python. The official image
# only installs python under /usr/local/bin. Do not use apt python-is-python3 here:
# it pulls Debian python3.11 into /usr/bin and breaks 3.12 venv site-packages.
# Symlink /usr/bin/python(3) to the image interpreter instead.

FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && ln -sf /usr/local/bin/python3 /usr/bin/python3 \
    && ln -sf /usr/local/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
