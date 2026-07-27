"""Service network mode: sandbox joins the Docker network shared with services.

Covers TODO 1bb64c90-a042-4a61-9d35-515c57ffe298: sandbox containers must be
able to reach deployed fleet services (planmgr, mcp-proxy, ...) by DNS name,
which requires joining the same Docker network instead of the default bridge.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
from mcp_terminal.services import docker_hosts, runtime_network
from mcp_terminal.services.docker_hosts import resolve_container_network_mode
from mcp_terminal.services.runtime_network import (
    resolve_default_network,
    resolve_service_network_name,
    resolve_service_network_names,
)
from mcp_terminal.services.sandbox_policy import (
    SERVICE_NETWORK_SPEC,
    SandboxPolicy,
)


class RuntimeNetworkResolverTests(unittest.TestCase):
    def test_default_network_falls_back_to_none(self) -> None:
        with mock.patch.object(runtime_network, "_config_data", return_value={}):
            self.assertEqual(resolve_default_network(), "none")

    def test_default_network_reads_runtime_section(self) -> None:
        data = {"runtime": {"default_network": "Service"}}
        with mock.patch.object(runtime_network, "_config_data", return_value=data):
            self.assertEqual(resolve_default_network(), "service")

    def test_service_network_name_unset_is_none(self) -> None:
        for runtime in ({}, {"service_networks": []}, {"service_networks": ["  "]}):
            with mock.patch.object(
                runtime_network, "_config_data", return_value={"runtime": runtime}
            ):
                self.assertIsNone(resolve_service_network_name())

    def test_service_networks_list_configured(self) -> None:
        data = {"runtime": {"service_networks": ["smart-assistant", "backend", "smart-assistant"]}}
        with mock.patch.object(runtime_network, "_config_data", return_value=data):
            self.assertEqual(
                resolve_service_network_names(), ("smart-assistant", "backend")
            )
            self.assertEqual(resolve_service_network_name(), "smart-assistant")

    def test_service_network_legacy_scalar_accepted(self) -> None:
        data = {"runtime": {"service_network": "smart-assistant"}}
        with mock.patch.object(runtime_network, "_config_data", return_value=data):
            self.assertEqual(resolve_service_network_names(), ("smart-assistant",))
            self.assertEqual(resolve_service_network_name(), "smart-assistant")


class ServiceNetworkPolicyTests(unittest.TestCase):
    def test_policy_allows_service_mode(self) -> None:
        net, err = SandboxPolicy().build_network_spec("service")
        self.assertIsNone(err)
        self.assertIs(net, SERVICE_NETWORK_SPEC)
        self.assertEqual(net.mode, "service")
        self.assertTrue(net.allow_egress)

    def test_container_network_mode_uses_configured_service_network(self) -> None:
        with mock.patch.object(
            docker_hosts, "resolve_service_network_name", return_value="smart-assistant"
        ):
            self.assertEqual(
                resolve_container_network_mode("service"), "smart-assistant"
            )

    def test_container_network_mode_service_without_name_falls_back(self) -> None:
        with mock.patch.object(
            docker_hosts, "resolve_service_network_name", return_value=None
        ):
            self.assertEqual(resolve_container_network_mode("service"), "bridge")


class ExtraServiceNetworkConnectTests(unittest.TestCase):
    def test_secondary_networks_attached_via_docker_network_connect(self) -> None:
        from mcp_terminal.services import session_container

        spec = mock.Mock()
        spec.network_spec = "service"
        with mock.patch.object(
            session_container,
            "resolve_service_network_names",
            return_value=("smart-assistant", "backend"),
        ), mock.patch.object(session_container.subprocess, "run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stderr=b"")
            session_container._connect_extra_service_networks(
                "mcp-term-x", spec, mock.Mock()
            )
        run_mock.assert_called_once()
        self.assertEqual(
            run_mock.call_args[0][0],
            ["docker", "network", "connect", "backend", "mcp-term-x"],
        )

    def test_non_service_mode_attaches_nothing(self) -> None:
        from mcp_terminal.services import session_container

        spec = mock.Mock()
        spec.network_spec = "none"
        with mock.patch.object(session_container.subprocess, "run") as run_mock:
            session_container._connect_extra_service_networks(
                "mcp-term-x", spec, mock.Mock()
            )
        run_mock.assert_not_called()


class TerminalRunServiceNetworkGateTests(unittest.TestCase):
    def test_service_mode_rejected_when_network_not_configured(self) -> None:
        with mock.patch.object(
            runtime_network, "_config_data", return_value={"runtime": {}}
        ):
            result = asyncio.run(
                TerminalRunCommand().execute(
                    project_id="00000000-0000-4000-8000-000000000000",
                    session_id="00000000-0000-4000-8000-000000000001",
                    execution_kind="shell",
                    command="true",
                    network="service",
                )
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "SERVICE_NETWORK_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
