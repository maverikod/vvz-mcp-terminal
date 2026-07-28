"""
Runtime network defaults from term server config (``runtime`` section).

``terminal_run`` uses these when the ``network`` parameter is omitted, and the
container layer resolves the ``service`` mode to the Docker network that the
fleet services share (so sandbox containers can reach them by DNS name).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

#: Network mode that joins the sandbox to the shared services Docker network.
SERVICE_NETWORK_MODE = "service"

_BUILTIN_DEFAULT_NETWORK = "none"


def _config_data() -> Dict[str, Any]:
    try:
        from mcp_proxy_adapter.config import get_config

        data = getattr(get_config(), "config_data", None)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _runtime_section() -> Dict[str, Any]:
    raw = _config_data().get("runtime")
    if not isinstance(raw, dict):
        return {}
    return raw


def resolve_default_network() -> str:
    """Return ``runtime.default_network`` (built-in fallback: ``none``)."""
    raw = _runtime_section().get("default_network", _BUILTIN_DEFAULT_NETWORK)
    value = str(raw).strip().lower()
    return value or _BUILTIN_DEFAULT_NETWORK


def resolve_service_network_names() -> Tuple[str, ...]:
    """Return ``runtime.service_networks`` — Docker networks shared with services.

    The first entry is the primary network (``docker run --network``); the
    rest are attached to the session container with ``docker network connect``
    after start. Accepts legacy scalar ``runtime.service_network`` as a
    one-element list. Empty when unset; the ``service`` network mode then
    fails validation in ``terminal_run`` instead of silently joining another
    network.
    """
    section = _runtime_section()
    raw = section.get("service_networks")
    if raw is None:
        legacy = section.get("service_network")
        raw = [legacy] if legacy is not None else []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    names: list[str] = []
    for item in raw:
        value = str(item).strip()
        if value and value not in names:
            names.append(value)
    return tuple(names)


def resolve_service_network_name() -> Optional[str]:
    """Return the primary service network (first of ``service_networks``)."""
    names = resolve_service_network_names()
    return names[0] if names else None


def resolve_docker_host() -> Optional[str]:
    """Return ``runtime.docker_host`` — the sandbox build daemon endpoint.

    Sandboxes carry a docker CLI; when this is set (e.g.
    ``tcp://mcp-terminal-dind:2375``) terminal_run injects it as DOCKER_HOST so
    ``docker build``/``docker run`` inside the sandbox talk to the fleet dind
    daemon. The daemon lives on the service docker network, so this only works
    for sessions using the ``service`` network mode. ``None`` when unset.
    """
    raw = _runtime_section().get("docker_host")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None
