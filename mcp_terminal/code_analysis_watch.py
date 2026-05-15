"""
Call Code Analysis Server over JSON-RPC to discover watch directories.

Uses ``code_analysis_client.CodeAnalysisAsyncClient`` (mcp-proxy-adapter transport).
When ``code_analysis.enabled`` is true in ``term_server.json``, the merged watch
roots include every path returned by ``list_watch_dirs`` (each path is a parent
directory that contains project folders as immediate subdirectories).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from mcp_proxy_adapter.client.jsonrpc_client.exceptions import ClientError

from code_analysis_client import CodeAnalysisAsyncClient


def term_code_analysis_to_server_config(section: Dict[str, Any]) -> Dict[str, Any]:
    """Shape ``term_server.json`` ``code_analysis`` like code-analysis ``server`` config."""
    ssl_block = section.get("ssl")
    server: Dict[str, Any] = {
        "host": str(section.get("host", "127.0.0.1")).strip(),
        "port": int(section.get("port", 15000)),
        "protocol": str(section.get("protocol", "https")).lower(),
    }
    if isinstance(ssl_block, dict) and ssl_block:
        server["ssl"] = ssl_block
    return {"server": server}


def _run_coro_sync(coro: Any) -> Any:
    """Run ``async`` coroutine from sync code (refresh thread / startup)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _list_watch_dirs_async(section: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        inner = await client.call("list_watch_dirs", {})
    finally:
        await client.close()

    if not isinstance(inner, dict) or not inner.get("success"):
        raise ValueError(f"list_watch_dirs failed: {inner!r}")
    data = inner.get("data") or {}
    watch_dirs = data.get("watch_dirs")
    if not isinstance(watch_dirs, list):
        raise ValueError("list_watch_dirs: missing data.watch_dirs list")
    return watch_dirs


def list_watch_dirs_sync(section: Dict[str, Any], *, config_path: Path) -> List[Dict[str, Any]]:
    """Call ``list_watch_dirs`` on the configured Code Analysis Server (sync façade).

    Args:
        section: The ``code_analysis`` object from ``term_server.json``.
        config_path: Reserved for diagnostics (unused; kept for a stable API).

    Returns:
        List of watch-dir dicts with at least ``id``, ``name``, ``absolute_path``.
        Each ``absolute_path`` is a **parent directory** that contains project
        roots as its direct subdirectories (each may hold a ``projectid`` file).

    Raises:
        ValueError: On missing TLS configuration, unsuccessful RPC payload, or
            transport / client errors surfaced as failed calls.
    """
    _ = config_path
    try:
        return _run_coro_sync(_list_watch_dirs_async(section))
    except ClientError as exc:
        raise ValueError(f"code_analysis list_watch_dirs: {exc}") from exc
