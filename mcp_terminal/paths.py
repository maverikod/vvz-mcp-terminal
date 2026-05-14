"""
Repository root resolution (runtime cwd-independent).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return absolute path to repository root (parent of `mcp_terminal` package)."""
    return Path(__file__).resolve().parent.parent
