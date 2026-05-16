"""
Expose Command.metadata() through adapter help (cmdname) responses.

The stock CommandRegistry.get_command_info only includes descr as summary.
This patch adds ai_metadata and detailed_description for AI clients.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.command_registry import CommandRegistry
from mcp_proxy_adapter.core.logging import get_global_logger

_PATCHED = False


def apply_registry_metadata_patch() -> None:
    """Patch CommandRegistry once to merge Command.metadata() into help output."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    logger = get_global_logger()
    original = CommandRegistry.get_command_info

    def get_command_info(
        self: CommandRegistry,
        command_name: str,
    ) -> Optional[Dict[str, Any]]:
        result = original(self, command_name)
        if result is None:
            return None
        with self._lock:
            command_class = self._commands.get(command_name)
        if command_class is None or not hasattr(command_class, "metadata"):
            return result
        try:
            ai_meta = cast(Dict[str, Any], command_class.metadata())
        except Exception as exc:  # noqa: BLE001
            logger.warning("metadata() failed for %s: %s", command_name, exc)
            return result
        if not ai_meta:
            return result
        result["ai_metadata"] = ai_meta
        meta_block = result.setdefault("metadata", {})
        if isinstance(meta_block, dict):
            detailed = ai_meta.get("detailed_description")
            if detailed:
                meta_block["detailed_description"] = detailed
            meta_block["usage_examples"] = ai_meta.get("usage_examples")
            meta_block["error_cases"] = ai_meta.get("error_cases")
            meta_block["best_practices"] = ai_meta.get("best_practices")
            meta_block["parameters_docs"] = ai_meta.get("parameters")
            meta_block["return_value"] = ai_meta.get("return_value")
        return result

    CommandRegistry.get_command_info = get_command_info  # type: ignore[method-assign]
    logger.info("CommandRegistry.get_command_info patched for ai_metadata")
