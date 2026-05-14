"""
Minimal MCP Proxy Adapter HTTP server (built-in commands only, HTTPS).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mcp_proxy_adapter.api.app import create_app
from mcp_proxy_adapter.config import get_config
from mcp_proxy_adapter.core.app_factory.ssl_config import build_server_ssl_config
from mcp_proxy_adapter.core.server_engine import ServerEngineFactory
from mcp_terminal.paths import repo_root
from mcp_terminal.term_config import (
    DEFAULT_TERM_SERVER_LISTEN_PORT,
    load_validated_term_simple_config,
)


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    """Load SimpleConfig, validate, create FastAPI app, run Hypercorn (HTTPS if configured)."""
    parser = argparse.ArgumentParser(description="MCP terminal minimal HTTPS server")
    parser.add_argument(
        "--config",
        type=str,
        default=str(repo_root() / "configs" / "term_server.json"),
        help="Path to SimpleConfig JSON (see mcp_terminal/term_server.defaults.json)",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    if not cfg_path.is_file():
        _die(f"Configuration file not found: {cfg_path}")

    try:
        app_config: dict = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _die(f"Failed to read configuration: {exc}")

    try:
        simple_config, model = load_validated_term_simple_config(cfg_path)
    except ValueError as exc:
        _die(str(exc))
    for section, value in simple_config.to_dict().items():
        app_config[section] = value

    app_config.setdefault("server", {})
    app_config["server"].setdefault("debug", False)
    app_config["server"].setdefault("log_level", "INFO")

    cfg = get_config()
    cfg.config_path = str(cfg_path)
    setattr(cfg, "model", model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    app = create_app(
        title="MCP Terminal (minimal)",
        description="HTTPS JSON-RPC adapter with built-in commands only.",
        version="0.1.0",
        app_config=app_config,
        config_path=str(cfg_path),
    )

    host = str(app_config.get("server", {}).get("host", "127.0.0.1"))
    port = int(app_config.get("server", {}).get("port", DEFAULT_TERM_SERVER_LISTEN_PORT))

    server_config: dict = {
        "host": host,
        "port": port,
        "log_level": "info",
        "reload": False,
    }
    try:
        ssl_engine = build_server_ssl_config(app_config)
        if ssl_engine:
            server_config.update(ssl_engine)
    except ValueError as exc:
        _die(f"SSL configuration invalid: {exc}")

    engine = ServerEngineFactory.get_engine("hypercorn")
    assert engine is not None, "Hypercorn engine not available"
    engine.run_server(app, server_config)


if __name__ == "__main__":
    main()
