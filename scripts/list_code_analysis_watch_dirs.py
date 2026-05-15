#!/usr/bin/env python3
"""Print watch directories from code-analysis-server using code_analysis_client.

Reads ``configs/term_server.json`` (repo root) and uses the ``code_analysis``
section for TLS/host/port. Run from repo root with venv:

  source .venv/bin/activate && python scripts/list_code_analysis_watch_dirs.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from code_analysis_client import CodeAnalysisAsyncClient

# Repo root = parent of scripts/
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_code_analysis_section(config_path: Path) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    section = data.get("code_analysis")
    if not isinstance(section, dict):
        print("No code_analysis section in config.", file=sys.stderr)
        raise SystemExit(1)
    return section


async def _fetch(section: dict) -> dict:
    from mcp_terminal.code_analysis_watch import term_code_analysis_to_server_config

    wrapped = term_code_analysis_to_server_config(section)
    ssl_block = section.get("ssl")
    check_hostname = False
    if isinstance(ssl_block, dict):
        check_hostname = bool(ssl_block.get("check_hostname", ssl_block.get("dnscheck", False)))
    timeout = float(section.get("timeout_seconds", 30) or 30)
    client = CodeAnalysisAsyncClient.from_server_config(
        wrapped,
        timeout=timeout,
        check_hostname=check_hostname,
    )
    try:
        return await client.call("list_watch_dirs", {})
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "configs" / "term_server.json",
        help="Path to term_server.json",
    )
    args = parser.parse_args()
    section = _load_code_analysis_section(args.config)
    raw = asyncio.run(_fetch(section))
    print(json.dumps(raw, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
