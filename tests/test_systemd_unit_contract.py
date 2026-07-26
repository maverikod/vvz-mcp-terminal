"""Host-safe packaging checks for systemd unit installation."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SystemdUnitContractTests(unittest.TestCase):
    def test_systemd_units_exist_in_debian_tree(self) -> None:
        service = ROOT / "docker/debian/lib/systemd/system/mcp-terminal-docker.service"
        recreate = ROOT / "docker/debian/lib/systemd/system/mcp-terminal-docker-recreate.service"
        self.assertTrue(service.is_file())
        self.assertTrue(recreate.is_file())

    def test_primary_service_uses_docker_run_entrypoints(self) -> None:
        text = (
            ROOT / "docker/debian/lib/systemd/system/mcp-terminal-docker.service"
        ).read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/lib/mcp-terminal/docker-run.sh start", text)
        self.assertIn("ExecStop=/usr/lib/mcp-terminal/docker-run.sh stop", text)
        self.assertIn("ExecReload=/usr/lib/mcp-terminal/docker-run.sh restart", text)

    def test_primary_service_is_oneshot_with_remain_after_exit(self) -> None:
        """Regression: Type=simple restart-looped the container every ~16s.

        docker-run.sh starts the container detached and exits, so with
        Type=simple systemd deactivated the unit, ran ExecStop (docker stop)
        and Restart=always revived it forever. The unit must stay a oneshot
        that remains active after ExecStart exits, and must not carry a
        Restart= policy (docker's own restart policy owns the container).
        """
        text = (
            ROOT / "docker/debian/lib/systemd/system/mcp-terminal-docker.service"
        ).read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", text)
        self.assertIn("RemainAfterExit=yes", text)
        self.assertNotIn("Type=simple", text)
        self.assertNotIn("Restart=", text.replace("RestartSec=", ""))
        self.assertNotIn("RestartSec=", text)

    def test_recreate_service_uses_docker_run_recreate(self) -> None:
        text = (
            ROOT / "docker/debian/lib/systemd/system/mcp-terminal-docker-recreate.service"
        ).read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/lib/mcp-terminal/docker-run.sh recreate", text)


if __name__ == "__main__":
    unittest.main()
