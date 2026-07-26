"""Tests for install-server-config.sh (config never overwritten when present)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pkg" / "install-server-config.sh"
TEMPLATE = Path(__file__).resolve().parents[1] / "docker" / "packaging" / "term_server.json.template"


def _run_install(config_dir: Path, template: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), str(config_dir), str(template), "mcp-terminal"],
        capture_output=True,
        text=True,
        check=False,
    )


class InstallServerConfigTests(unittest.TestCase):
    def test_creates_config_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "etc" / "mcp-terminal"
            proc = _run_install(config_dir, TEMPLATE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            config = config_dir / "term_server.json"
            self.assertTrue(config.is_file())
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertNotEqual(data["registration"]["instance_uuid"], "REPLACE_ON_INSTALL")
            self.assertIn("Installed new", proc.stdout)

    def test_preserves_customized_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "etc" / "mcp-terminal"
            config_dir.mkdir(parents=True)
            config = config_dir / "term_server.json"
            custom = {"terminal": {"host_execution": {"enabled": False, "custom": True}}}
            config.write_text(json.dumps(custom), encoding="utf-8")

            proc = _run_install(config_dir, TEMPLATE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(config.read_text(encoding="utf-8")), custom)
            self.assertIn("Preserved existing", proc.stdout)
            sidecar = config_dir / "term_server.json.template"
            self.assertTrue(sidecar.is_file())
            self.assertIn("host_execution", sidecar.read_text(encoding="utf-8"))

    def test_finalizes_pristine_placeholder_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "etc" / "mcp-terminal"
            config_dir.mkdir(parents=True)
            config = config_dir / "term_server.json"
            body = TEMPLATE.read_text(encoding="utf-8")
            self.assertIn("REPLACE_ON_INSTALL", body)
            config.write_text(body, encoding="utf-8")

            proc = _run_install(config_dir, TEMPLATE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            updated = json.loads(config.read_text(encoding="utf-8"))
            self.assertNotEqual(updated["registration"]["instance_uuid"], "REPLACE_ON_INSTALL")
            self.assertEqual(updated["server"]["advertised_host"], "mcp-terminal")
            self.assertIn("Finalized new", proc.stdout)

    def test_migrates_legacy_advertised_host_placeholder_in_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "etc" / "mcp-terminal"
            config_dir.mkdir(parents=True)
            config = config_dir / "term_server.json"
            data = {
                "server": {"advertised_host": "CHANGE_ME"},
                "registration": {
                    "instance_uuid": "00000000-0000-4000-8000-000000000001"
                },
                "terminal": {"host_execution": {"enabled": False}},
            }
            config.write_text(json.dumps(data), encoding="utf-8")

            proc = _run_install(config_dir, TEMPLATE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            updated = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(updated["server"]["advertised_host"], "mcp-terminal")
            self.assertEqual(
                updated["registration"]["instance_uuid"],
                "00000000-0000-4000-8000-000000000001",
            )
            self.assertIn("Preserved existing", proc.stdout)


if __name__ == "__main__":
    unittest.main()
