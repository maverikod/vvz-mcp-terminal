FROM python:3.12-slim-bookworm

LABEL maintainer="Vasiliy Zdanovskiy <vasilyvz@gmail.com>"
LABEL description="MCP Terminal — sandboxed terminal sessions with MCP proxy integration"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MCP_TERMINAL_SKIP_VENV_REEXEC=1
ENV MCP_TERMINAL_CONFIG_DIR=/etc/mcp-terminal
ENV MCP_TERMINAL_LOG_DIR=/var/log/mcp-terminal
ENV MCP_TERMINAL_DATA_DIR=/var/mcp-terminal

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    docker.io \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml LICENSE ./
COPY mcp_terminal/ mcp_terminal/

RUN pip install --no-cache-dir --default-timeout=300 .

EXPOSE 3011

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f -sk https://127.0.0.1:3011/health || exit 1

CMD ["python", "-m", "mcp_terminal.term_server", "--config", "/etc/mcp-terminal/term_server.json"]
