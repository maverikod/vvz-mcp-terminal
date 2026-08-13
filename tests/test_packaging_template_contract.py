"""Host-safe contract checks for the packaged term_server template."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docker" / "packaging" / "term_server.json.template"
DEFAULTS = ROOT / "mcp_terminal" / "term_server.defaults.json"
ENSURE_MTLS = ROOT / "docker" / "pkg" / "ensure-mtls-certificates.sh"


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

    def test_mtls_paths_use_flat_layout(self) -> None:
        """Cert paths use a single mtls_certificates/ segment; only the legacy
        migration in ensure-mtls-certificates.sh may mention the nested tree."""
        doubled = "mtls_certificates/mtls_certificates"
        self.assertNotIn(doubled, TEMPLATE.read_text(encoding="utf-8"))
        self.assertNotIn(doubled, DEFAULTS.read_text(encoding="utf-8"))
        ensure_text = ENSURE_MTLS.read_text(encoding="utf-8")
        for line in ensure_text.splitlines():
            if "install -d" in line or "mkdir" in line:
                self.assertNotIn('"${MTLS_DIR}/mtls_certificates', line)


if __name__ == "__main__":
    unittest.main()
