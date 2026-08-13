"""Host-safe contract checks for the packaged term_server template."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docker" / "packaging" / "term_server.json.template"


class PackagingTemplateContractTests(unittest.TestCase):
    def test_packaging_template_defaults_to_docker_dns_advertised_host(self) -> None:
        data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(data["server"]["advertised_host"], "mcp-terminal")

    def test_packaging_template_carries_no_static_version(self) -> None:
        """The dpkg conffile must not freeze a version: runtime injects it (single source)."""
        data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        registration = data["registration"]
        self.assertNotIn("version", registration)
        self.assertNotIn("version", registration["metadata"])
        self.assertNotIn("@VERSION@", TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
