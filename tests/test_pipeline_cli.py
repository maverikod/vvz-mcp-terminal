"""Contract tests for the pipeline package CLI."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from mcp_terminal.pipeline.registry import PIPELINE_CHECKS, pipeline_check_by_name


ROOT = Path(__file__).resolve().parents[1]


class PipelineCliTests(unittest.TestCase):
    def test_pipeline_registry_contains_named_checks(self) -> None:
        names = [check.name for check in PIPELINE_CHECKS]
        self.assertIn("sandbox_runtime_bootstrap", names)
        self.assertIn("sandbox_toolchain_contract", names)
        self.assertIn("info_command_contract", names)
        self.assertIn("pipeline_cli_contract", names)
        self.assertIn("package_config_contract", names)
        self.assertIn("pytest_suite", names)
        self.assertIn("live_server_api", names)
        self.assertIsNotNone(pipeline_check_by_name("sandbox_runtime_bootstrap"))
        self.assertIsNone(pipeline_check_by_name("missing"))

    def test_python_module_lists_checks(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "mcp_terminal.pipeline", "--list"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("sandbox_runtime_bootstrap", proc.stdout)
        self.assertIn("live_server_api", proc.stdout)


if __name__ == "__main__":
    unittest.main()
