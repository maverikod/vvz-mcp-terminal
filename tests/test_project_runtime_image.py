"""Tests for per-project runtime image state and session bootstrap wiring."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.services.project_runtime_image import (
    ensure_project_runtime_image,
    resolve_execution_image,
    runtime_fingerprint,
    verify_runtime_image_state,
)
from mcp_terminal.services.session_bootstrap import run_session_runtime_bootstrap


class ProjectRuntimeImageTests(unittest.TestCase):
    def test_runtime_fingerprint_changes_with_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            before = runtime_fingerprint(project_dir, image_profile="python_dev_3_12")
            (project_dir / "requirements.txt").write_text("x\n", encoding="utf-8")
            after = runtime_fingerprint(project_dir, image_profile="python_dev_3_12")
            self.assertNotEqual(before, after)

    def test_runtime_fingerprint_changes_with_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            before = runtime_fingerprint(project_dir, image_profile="python_dev_3_12")
            (project_dir / "pyproject.toml").write_text(
                """
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-project"
version = "0.1.0"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            after = runtime_fingerprint(project_dir, image_profile="python_dev_3_12")
            self.assertNotEqual(before, after)

    def test_resolve_uses_stock_without_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ref, err = resolve_execution_image(
                project_dir,
                project_id="00000000-0000-4000-8000-000000000001",
                image_profile="python_dev_3_12",
                stock_image_ref="ghcr.io/stock:1",
            )
            self.assertEqual(ref, "ghcr.io/stock:1")
            self.assertIsNone(err)

    def test_verify_runtime_false_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, reason = verify_runtime_image_state(Path(tmp))
            self.assertFalse(ok)
            self.assertEqual(reason, "no_state")

    @patch("mcp_terminal.services.project_runtime_image.ensure_project_runtime_image")
    def test_run_session_runtime_bootstrap_maps_success(self, mock_ensure) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            session_dir = project_dir / "session"
            session_dir.mkdir()
            mock_ensure.return_value = (True, True, 0, "image_verified")
            result = run_session_runtime_bootstrap(
                project_dir,
                project_id="00000000-0000-4000-8000-000000000001",
                session_dir=session_dir,
                image_profile="python_dev_3_12",
                timeout_seconds=60,
            )
            self.assertTrue(result.success)
            self.assertTrue(result.skipped)
            self.assertEqual(result.exit_code, 0)

    @patch("mcp_terminal.services.project_runtime_image._docker_image_id", return_value="sha256:test")
    @patch("mcp_terminal.services.project_runtime_image.subprocess.run")
    def test_python_runtime_bootstrap_builds_pyproject_project(
        self,
        mock_run,
        _mock_image_id,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / "pyproject.toml").write_text(
                """
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-project"
version = "0.1.0"

[project.optional-dependencies]
dev = ["pytest>=8.0", "mypy>=1.8.0", "ruff>=0.8.0"]
""".strip()
                + "\n",
                encoding="utf-8",
            )
            package_dir = project_dir / "demo_project"
            package_dir.mkdir()
            (package_dir / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

            ok, skipped, code, detail = ensure_project_runtime_image(
                project_dir,
                project_id="00000000-0000-4000-8000-000000000001",
                image_profile="python_dev_3_12",
                stock_image_ref="ghcr.io/stock:1",
            )

            self.assertTrue(ok)
            self.assertFalse(skipped)
            self.assertEqual(code, 0)
            self.assertEqual(detail, "built")
            self.assertTrue(mock_run.called)
            dockerfile = (
                project_dir / ".mcp_terminal" / "runtime" / "build_context" / "Dockerfile"
            ).read_text(encoding="utf-8")
            self.assertIn("FROM ghcr.io/stock:1", dockerfile)
            self.assertIn("pip install --no-cache-dir -e .[dev]", dockerfile)

    @patch("mcp_terminal.services.project_runtime_image._docker_image_id", return_value="sha256:test")
    @patch("mcp_terminal.services.project_runtime_image.subprocess.run")
    def test_runtime_image_build_uses_runtime_context_for_editable_requirements(
        self,
        mock_run,
        _mock_image_id,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / "pyproject.toml").write_text(
                """
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-project"
version = "0.1.0"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (project_dir / "requirements.txt").write_text("-e .\n", encoding="utf-8")
            package_dir = project_dir / "demo_project"
            package_dir.mkdir()
            (package_dir / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

            ok, skipped, code, detail = ensure_project_runtime_image(
                project_dir,
                project_id="00000000-0000-4000-8000-000000000001",
                image_profile="python_dev_3_12",
                stock_image_ref="ghcr.io/stock:1",
            )

            self.assertTrue(ok)
            self.assertFalse(skipped)
            self.assertEqual(code, 0)
            self.assertEqual(detail, "built")
            build_cmd = mock_run.call_args.args[0]
            context_dir = project_dir / ".mcp_terminal" / "runtime" / "build_context"
            self.assertEqual(build_cmd[-1], str(context_dir.resolve()))
            self.assertEqual(
                (context_dir / "requirements.txt").read_text(encoding="utf-8"),
                "-e .\n",
            )
            self.assertTrue((context_dir / "demo_project" / "__init__.py").is_file())


if __name__ == "__main__":
    unittest.main()
