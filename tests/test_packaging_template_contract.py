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


if __name__ == "__main__":
    unittest.main()
