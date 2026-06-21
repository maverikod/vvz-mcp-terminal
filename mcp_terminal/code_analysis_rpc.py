"""
Shared JSON-RPC helpers for Code Analysis Server (casmgr) from mcp_terminal.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


def is_tls_protocol(protocol: str | None) -> bool:
    """True when config protocol uses HTTPS transport (``https`` or ``mtls``)."""
    return (protocol or "http").lower() in ("https", "mtls")


def run_coro_sync(coro: Any) -> Any:
    """Run ``async`` coroutine from sync code (refresh thread / command handlers)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Inside Hypercorn/async command handlers: cannot nest run_until_complete on the
    # running loop; execute the coroutine in a worker thread with its own loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(frozen=True)
class CodeAnalysisRpcError(Exception):
    """Structured failure from a casmgr JSON-RPC command."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def code_analysis_section(app_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``code_analysis`` block from merged app config."""
    section = app_config.get("code_analysis")
    if not isinstance(section, dict):
        raise ValueError("code_analysis section is required")
    return section


def terminal_instance_uuid(app_config: Dict[str, Any]) -> str:
    """``registration.instance_uuid`` for subordinate_session server_uuid."""
    registration = app_config.get("registration")
    if not isinstance(registration, dict):
        raise ValueError("registration section is required")
    raw = registration.get("instance_uuid")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("registration.instance_uuid is required")
    return raw.strip()


def _rpc_error_code(inner: Dict[str, Any]) -> str:
    err = inner.get("error")
    if isinstance(err, dict):
        code = err.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    for key in ("error", "code"):
        val = inner.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "RPC_ERROR"


def _rpc_error_message(inner: Dict[str, Any]) -> str:
    err = inner.get("error")
    if isinstance(err, dict):
        for key in ("message", "error_message", "detail"):
            val = err.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    for key in ("message", "error_message", "detail"):
        val = inner.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return repr(inner)


def unwrap_rpc_success(inner: Any, *, command: str) -> Dict[str, Any]:
    """Require ``success`` payload from casmgr ``execute_command`` result."""
    if not isinstance(inner, dict):
        raise CodeAnalysisRpcError("RPC_ERROR", f"{command}: unexpected response {inner!r}")
    if inner.get("success"):
        data = inner.get("data")
        return data if isinstance(data, dict) else {}
    raise CodeAnalysisRpcError(_rpc_error_code(inner), _rpc_error_message(inner))


async def call_code_analysis_async(
    section: Dict[str, Any],
    command: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute one casmgr command and return unwrapped ``data`` dict."""
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
        inner = await client.call(command, params or {})
        return unwrap_rpc_success(inner, command=command)
    finally:
        await client.close()


def call_code_analysis_sync(
    section: Dict[str, Any],
    command: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sync façade over :func:`call_code_analysis_async`."""
    try:
        return run_coro_sync(call_code_analysis_async(section, command, params))
    except ClientError as exc:
        raise CodeAnalysisRpcError("CODE_ANALYSIS_UNAVAILABLE", str(exc)) from exc
    except CodeAnalysisRpcError:
        raise
    except Exception as exc:
        raise CodeAnalysisRpcError("CODE_ANALYSIS_UNAVAILABLE", str(exc)) from exc
