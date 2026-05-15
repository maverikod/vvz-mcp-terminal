"""
Process-wide terminal services for MCP command handlers.

Populated from ``term_server.main`` so adapter ``Command.run`` can resolve
``SessionStore`` and ``ProjectRegistry`` without custom adapter patches.

All reads/writes of the shared ``ProjectRegistry`` pointer and reads of its
in-memory index (project lists, resolve, watch layout) must go through this
module so ``_project_registry_lock`` (``threading.RLock``) is taken consistently.
Background registry refresh swaps the pointer under the same lock.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable, FrozenSet, Optional, TypeVar

if TYPE_CHECKING:
    from mcp_terminal.services.project_registry import ProjectRegistry, ResolutionResult
    from mcp_terminal.services.session_store import SessionStore

T = TypeVar("T")

_session_store: Optional["SessionStore"] = None
_project_registry: Optional["ProjectRegistry"] = None
_project_registry_lock = threading.RLock()


def _with_project_registry(fn: Callable[["ProjectRegistry"], T]) -> T:
    """Run ``fn`` on the active registry while holding ``_project_registry_lock``."""
    with _project_registry_lock:
        if _project_registry is None:
            raise RuntimeError("ProjectRegistry not configured (term_server startup incomplete)")
        return fn(_project_registry)


def set_terminal_services(
    *,
    session_store: "SessionStore",
    project_registry: "ProjectRegistry",
) -> None:
    """Install shared stores for the current process (called once at startup)."""
    global _session_store, _project_registry
    with _project_registry_lock:
        _session_store = session_store
        _project_registry = project_registry


def set_project_registry(project_registry: "ProjectRegistry") -> None:
    """Replace the active ``ProjectRegistry`` (used by background refresh)."""
    global _project_registry
    with _project_registry_lock:
        _project_registry = project_registry


def get_session_store() -> "SessionStore":
    """Return the active ``SessionStore`` or raise if startup did not configure it."""
    if _session_store is None:
        raise RuntimeError("SessionStore not configured (term_server startup incomplete)")
    return _session_store


def get_project_registry() -> "ProjectRegistry":
    """Return the active ``ProjectRegistry`` (unsafe for concurrent index reads).

    The lock is **not** held after this call returns. A background thread may
    replace the registry instance at any time; calling ``.resolve()``,
    ``.known_project_ids``, ``.list_watch_layout()``, or other registry reads on the
    returned object can race with that swap.

    For handlers, use ``registry_resolve_project``, ``registry_known_project_ids``,
    and ``registry_list_watch_layout`` — each takes ``_project_registry_lock`` for
    the whole operation.
    """
    return _with_project_registry(lambda reg: reg)


def registry_resolve_project(project_id: str) -> "ResolutionResult":
    """Resolve ``project_id`` under the registry mutex."""
    return _with_project_registry(lambda reg: reg.resolve(project_id))


def registry_known_project_ids() -> FrozenSet[str]:
    """Return known project ids under the registry mutex."""
    return _with_project_registry(lambda reg: reg.known_project_ids)


def registry_list_watch_layout() -> dict[str, Any]:
    """Return ``ProjectRegistry.list_watch_layout()`` under the registry mutex."""
    return _with_project_registry(lambda reg: reg.list_watch_layout())
