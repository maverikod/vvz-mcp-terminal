"""
Config CLI for mcp_terminal (C-013).

Exposes generate, validate, and help subcommands.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.config.config_validator import validate_terminal_config


def _optional_bool(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected boolean string, got {raw!r}")


def _collect_code_analysis_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    """Build keyword arguments for ``generate_terminal_config`` from CLI flags."""
    out: Dict[str, Any] = {}
    if args.code_analysis_enabled is not None:
        out["code_analysis_enabled"] = args.code_analysis_enabled
    if args.code_analysis_protocol is not None:
        out["code_analysis_protocol"] = args.code_analysis_protocol
    if args.code_analysis_host is not None:
        out["code_analysis_host"] = args.code_analysis_host
    if args.code_analysis_port is not None:
        out["code_analysis_port"] = args.code_analysis_port
    if args.code_analysis_jsonrpc_path is not None:
        out["code_analysis_jsonrpc_path"] = args.code_analysis_jsonrpc_path
    if args.code_analysis_timeout_seconds is not None:
        out["code_analysis_timeout_seconds"] = args.code_analysis_timeout_seconds
    if args.code_analysis_watch_dir_index is not None:
        out["code_analysis_watch_dir_index"] = args.code_analysis_watch_dir_index
    if args.code_analysis_ssl_cert is not None:
        out["code_analysis_ssl_cert"] = args.code_analysis_ssl_cert
    if args.code_analysis_ssl_key is not None:
        out["code_analysis_ssl_key"] = args.code_analysis_ssl_key
    if args.code_analysis_ssl_ca is not None:
        out["code_analysis_ssl_ca"] = args.code_analysis_ssl_ca
    if args.code_analysis_ssl_crl is not None:
        out["code_analysis_ssl_crl"] = args.code_analysis_ssl_crl
    if args.code_analysis_ssl_dnscheck is not None:
        out["code_analysis_ssl_dnscheck"] = args.code_analysis_ssl_dnscheck
    if args.code_analysis_ssl_check_hostname is not None:
        out["code_analysis_ssl_check_hostname"] = args.code_analysis_ssl_check_hostname
    return out


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate a default terminal config and write to output path."""
    ca_kw = _collect_code_analysis_kwargs(args)
    config = generate_terminal_config({}, **ca_kw)
    output = Path(args.output) if args.output else None
    text = json.dumps(config, indent=2)
    if output:
        output.write_text(text, encoding="utf-8")
        print(f"Generated config written to {output}")
    else:
        print(text)


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a terminal config file and report errors."""
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_terminal_config(config)
    if errors:
        for err in errors:
            print(f"ERROR [{err.field}]: {err.message}", file=sys.stderr)
        raise SystemExit(1)
    print("Config is valid.")


def main() -> None:
    """Entry point for the mcp_terminal config CLI."""
    parser = argparse.ArgumentParser(
        prog="mcp-terminal-config",
        description="mcp_terminal configuration tool (C-013)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    gen = subparsers.add_parser("generate", help="Generate default config")
    gen.add_argument("--output", type=str, default=None, help="Output file path")
    gen.add_argument(
        "--code-analysis-enabled",
        type=_optional_bool,
        default=None,
        metavar="BOOL",
        help="code_analysis.enabled (true/false)",
    )
    gen.add_argument(
        "--code-analysis-protocol",
        type=str,
        default=None,
        choices=("http", "https"),
        help="code_analysis.protocol",
    )
    gen.add_argument("--code-analysis-host", type=str, default=None, help="code_analysis.host")
    gen.add_argument(
        "--code-analysis-port",
        type=int,
        default=None,
        metavar="PORT",
        help="code_analysis.port",
    )
    gen.add_argument(
        "--code-analysis-jsonrpc-path",
        type=str,
        default=None,
        help="code_analysis.jsonrpc_path (default /api/jsonrpc)",
    )
    gen.add_argument(
        "--code-analysis-timeout-seconds",
        type=float,
        default=None,
        metavar="SECONDS",
        help="code_analysis.timeout_seconds",
    )
    gen.add_argument(
        "--code-analysis-watch-dir-index",
        type=int,
        default=None,
        metavar="N",
        help="code_analysis.watch_dir_index",
    )
    gen.add_argument(
        "--code-analysis-ssl-cert",
        type=str,
        default=None,
        help="code_analysis.ssl.cert path",
    )
    gen.add_argument(
        "--code-analysis-ssl-key",
        type=str,
        default=None,
        help="code_analysis.ssl.key path",
    )
    gen.add_argument(
        "--code-analysis-ssl-ca",
        type=str,
        default=None,
        help="code_analysis.ssl.ca path",
    )
    gen.add_argument(
        "--code-analysis-ssl-crl",
        type=str,
        default=None,
        help="code_analysis.ssl.crl path or empty to clear",
    )
    gen.add_argument(
        "--code-analysis-ssl-dnscheck",
        type=_optional_bool,
        default=None,
        metavar="BOOL",
        help="code_analysis.ssl.dnscheck",
    )
    gen.add_argument(
        "--code-analysis-ssl-check-hostname",
        type=_optional_bool,
        default=None,
        metavar="BOOL",
        help="code_analysis.ssl.check_hostname",
    )
    gen.set_defaults(func=cmd_generate)
    val = subparsers.add_parser("validate", help="Validate config file")
    val.add_argument("config", type=str, help="Path to config file")
    val.set_defaults(func=cmd_validate)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
