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

from pathlib import Path
from typing import Any, Dict, List

from mcp_proxy_adapter.client.jsonrpc_client.exceptions import ClientError

from mcp_terminal.code_analysis_rpc import call_code_analysis_async, run_coro_sync


async def _list_watch_dirs_async(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = await call_code_analysis_async(section, "list_watch_dirs", {})
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
        return run_coro_sync(_list_watch_dirs_async(section))
    except ClientError as exc:
        raise ValueError(f"code_analysis list_watch_dirs: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"code_analysis list_watch_dirs: {exc}") from exc
