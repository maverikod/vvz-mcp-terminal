"""Sandbox docker builds via the packaged dind daemon (bug fa4f51aa follow-up).

Sandboxes carry a docker CLI and get DOCKER_HOST injected from
``runtime.docker_host`` so builds run on the fleet Docker-in-Docker daemon,
never on the host daemon (the host socket stays on the sandbox denylist).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from mcp_terminal.services import runtime_network, sandbox_policy
from mcp_terminal.services.runtime_network import resolve_docker_host
from mcp_terminal.services.sandbox_policy import SandboxPolicy

ROOT = Path(__file__).resolve().parents[1]


class DockerHostResolverTests(unittest.TestCase):
    def test_unset_or_blank_is_none(self) -> None:
        for runtime in ({}, {"docker_host": ""}, {"docker_host": "  "}):
            with mock.patch.object(
                runtime_network, "_config_data", return_value={"runtime": runtime}
            ):
                self.assertIsNone(resolve_docker_host())

    def test_configured_endpoint_returned(self) -> None:
        data = {"runtime": {"docker_host": "tcp://mcp-terminal-dind:2375"}}
        with mock.patch.object(runtime_network, "_config_data", return_value=data):
            self.assertEqual(resolve_docker_host(), "tcp://mcp-terminal-dind:2375")


class DockerHostInjectionTests(unittest.TestCase):
    def _spec_env(self) -> dict:
        spec, err = SandboxPolicy().build_image_and_command_spec(
            image_profile="python_dev_3_12",
            execution_kind="shell",
            command="docker version",
            argv=None,
        )
        assert err is None and spec is not None
        return dict(spec.environment)

    def test_docker_host_injected_when_configured(self) -> None:
        with mock.patch.object(
            sandbox_policy,
            "resolve_docker_host",
            return_value="tcp://mcp-terminal-dind:2375",
        ):
            env = self._spec_env()
        self.assertEqual(env.get("DOCKER_HOST"), "tcp://mcp-terminal-dind:2375")

    def test_no_docker_host_when_unconfigured(self) -> None:
        with mock.patch.object(
            sandbox_policy, "resolve_docker_host", return_value=None
        ):
            env = self._spec_env()
        self.assertNotIn("DOCKER_HOST", env)

    def test_host_docker_socket_stays_forbidden(self) -> None:
        # dind must not soften the zero-trust rule against the host daemon.
        self.assertIn(
            "/var/run/docker.sock", SandboxPolicy._FORBIDDEN_OPTIONS
        )


class DindPackagingContractTests(unittest.TestCase):
    def test_sandbox_images_ship_docker_cli(self) -> None:
        for profile in ("python-dev", "node-dev", "base-tools"):
            text = (ROOT / "docker" / profile / "Dockerfile").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "COPY --from=docker:cli /usr/local/bin/docker", text, profile
            )

    def test_docker_run_sh_manages_dind(self) -> None:
        text = (ROOT / "docker/pkg/docker-run.sh").read_text(encoding="utf-8")
        for needle in (
            "dind-start",
            "dind-stop",
            "dind-recreate",
            "mcp-terminal-dind",
            "DOCKER_TLS_CERTDIR=",
        ):
            self.assertIn(needle, text)
        # The build daemon must never be published on a host port.
        self.assertNotIn("-p \"${DIND", text)

    def test_template_points_sandboxes_at_dind(self) -> None:
        text = (
            ROOT / "docker/packaging/term_server.json.template"
        ).read_text(encoding="utf-8")
        self.assertIn('"docker_host": "tcp://mcp-terminal-dind:2375"', text)

    def test_info_guide_documents_the_technology(self) -> None:
        text = (ROOT / "mcp_terminal/docs/INFO.md").read_text(encoding="utf-8")
        self.assertIn("## Sandbox Docker Builds", text)
        for needle in (
            "DOCKER_HOST",
            "mcp-terminal-dind",
            "docker save",
            "Cannot connect to the Docker daemon",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
