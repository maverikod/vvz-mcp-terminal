"""Static regression checks for the baseline Python sandbox toolchain."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SandboxToolchainBaselineTests(unittest.TestCase):
    def test_python_dev_image_includes_required_os_packages(self) -> None:
        text = (ROOT / "docker/python-dev/Dockerfile").read_text(encoding="utf-8")
        for package_name in (
            "file",
            "patch",
            "psmisc",
            "sqlite3",
            "rsync",
            "unzip",
            "xz-utils",
            "zip",
            "p7zip-full",
        ):
            self.assertIn(package_name, text)

    def test_python_dev_image_includes_required_python_tools(self) -> None:
        text = (ROOT / "docker/python-dev/Dockerfile").read_text(encoding="utf-8")
        for package_name in (
            "bandit",
            "build",
            "coverage",
            "mypy",
            "nox",
            "pip-audit",
            "pip-tools",
            "pipdeptree",
            "pre-commit",
            "pytest",
            "pytest-cov",
            "ruff",
            "tox",
            "wheel",
        ):
            self.assertIn(package_name, text)


if __name__ == "__main__":
    unittest.main()
