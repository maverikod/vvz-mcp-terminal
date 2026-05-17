"""Tests for Docker bridge /etc/hosts → --add-host helpers."""

from __future__ import annotations

from pathlib import Path

from mcp_terminal.services.docker_hosts import (
    docker_run_add_host_args,
    is_docker_bridge_ipv4,
    parse_docker_host_mappings,
    resolve_container_network_mode,
)


def test_is_docker_bridge_ipv4() -> None:
    assert is_docker_bridge_ipv4("172.18.0.5")
    assert is_docker_bridge_ipv4("172.31.255.1")
    assert not is_docker_bridge_ipv4("127.0.0.1")
    assert not is_docker_bridge_ipv4("8.8.8.8")
    assert not is_docker_bridge_ipv4("10.0.0.1")
    assert not is_docker_bridge_ipv4("not-an-ip")


def test_parse_docker_host_mappings_filters(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_text(
        "127.0.0.1 localhost\n"
        "172.18.0.5 code-analysis-db.techsup.od.ua\n"
        "172.18.0.2 mcp-proxy.techsup.od.ua extra.alias\n"
        "8.8.8.8 dns.google\n",
        encoding="utf-8",
    )
    mappings = parse_docker_host_mappings(hosts)
    assert len(mappings) == 2
    assert mappings[0].ip == "172.18.0.5"
    assert mappings[0].hostnames == ("code-analysis-db.techsup.od.ua",)
    assert mappings[1].hostnames == ("mcp-proxy.techsup.od.ua", "extra.alias")


def test_docker_run_add_host_args() -> None:
    from mcp_terminal.services.docker_hosts import HostMapping

    args = docker_run_add_host_args(
        [HostMapping(ip="172.18.0.5", hostnames=("db.example",))]
    )
    assert args == ["--add-host", "db.example:172.18.0.5"]


def test_resolve_container_network_mode(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "empty_hosts"
    empty.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr(
        "mcp_terminal.services.docker_hosts._DEFAULT_HOSTS_PATH",
        empty,
    )
    assert resolve_container_network_mode("none") == "none"
    assert resolve_container_network_mode("package_registry") == "bridge"

    docker_hosts = tmp_path / "docker_hosts"
    docker_hosts.write_text(
        "172.18.0.5 db.internal\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "mcp_terminal.services.docker_hosts._DEFAULT_HOSTS_PATH",
        docker_hosts,
    )
    assert resolve_container_network_mode("none") == "bridge"
