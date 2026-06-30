"""Package identity helpers shared by runtime and Debian docs."""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

PACKAGE_NAME = "mcp-terminal"
DEBIAN_PACKAGE_NAME = "mcp-terminal-docker"


def package_version() -> str:
    """Return the checkout/build version, falling back to installed metadata."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if text:
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0"
