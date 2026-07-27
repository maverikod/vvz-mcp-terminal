"""
Host ``/etc/hosts`` entries for Docker bridge networks → ``docker run --add-host``.

Only mappings whose IPv4 address lies in Docker's default bridge range (172.16.0.0/12)
are copied. Localhost and public DNS entries are skipped.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from mcp_terminal.services.runtime_network import (
    SERVICE_NETWORK_MODE,
    resolve_service_network_name,
)

logger = logging.getLogger(__name__)

_DOCKER_IPV4_NETWORK = ipaddress.ip_network("172.16.0.0/12")
_DEFAULT_HOSTS_PATH = Path("/etc/hosts")


@dataclass(frozen=True)
class HostMapping:
    """One IP with one or more hostnames from a hosts(5) line."""

    ip: str
    hostnames: tuple[str, ...]


def is_docker_bridge_ipv4(ip_str: str) -> bool:
    """True when ``ip_str`` is an IPv4 address in 172.16.0.0/12 (Docker bridges)."""
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    if ip.version != 4:
        return False
    return ip in _DOCKER_IPV4_NETWORK


def parse_docker_host_mappings(
    hosts_path: Path | None = None,
) -> List[HostMapping]:
    """
    Read ``hosts_path`` and return Docker-bridge mappings only.

    Skips comments, blank lines, and lines whose first field is not a
    Docker-bridge IPv4 address.
    """
    path = hosts_path if hosts_path is not None else _DEFAULT_HOSTS_PATH
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("docker_hosts: cannot read %s: %s", path, exc)
        return []

    out: List[HostMapping] = []
    seen: set[tuple[str, str]] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ip = parts[0]
        if not is_docker_bridge_ipv4(ip):
            continue
        names: List[str] = []
        for name in parts[1:]:
            if name.startswith("#"):
                break
            if name not in names:
                names.append(name)
        if not names:
            continue
        key = (ip, names[0])
        if key in seen:
            continue
        seen.add(key)
        out.append(HostMapping(ip=ip, hostnames=tuple(names)))

    return out


def resolve_container_network_mode(network_spec: str) -> str:
    """
    Map policy ``network_spec`` to ``docker run --network`` value.

    ``service`` joins the Docker network shared with fleet services
    (``runtime.service_network``), so their DNS names resolve inside the
    sandbox; when that name is not configured, fall back to ``bridge``
    (``terminal_run`` validates the configuration up front and rejects
    ``service`` requests before reaching this fallback).

    When policy is ``none`` but the host has Docker-bridge ``/etc/hosts``
    entries, use ``bridge`` so those IPs are reachable (``--add-host`` alone
    is not enough with ``--network none``).
    """
    if network_spec == SERVICE_NETWORK_MODE:
        return resolve_service_network_name() or "bridge"
    if network_spec != "none":
        return "bridge"
    if parse_docker_host_mappings():
        return "bridge"
    return "none"


def docker_run_add_host_args(
    mappings: Sequence[HostMapping] | None = None,
    *,
    hosts_path: Path | None = None,
) -> List[str]:
    """
    Build ``docker run`` flags: ``--add-host name:ip`` for each Docker mapping.

    Returns a flat list suitable for extending a docker argv (pairs of flag + value).
    """
    rows = (
        list(mappings)
        if mappings is not None
        else parse_docker_host_mappings(hosts_path)
    )
    args: List[str] = []
    for row in rows:
        for hostname in row.hostnames:
            args.extend(["--add-host", f"{hostname}:{row.ip}"])
    return args
