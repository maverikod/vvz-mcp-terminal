"""
Smoke tests for package and third-party adapter imports.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib


def test_package_version() -> None:
    import mcp_terminal

    assert hasattr(mcp_terminal, "__version__")
    assert mcp_terminal.__version__


def test_mcp_proxy_adapter_importable() -> None:
    mod = importlib.import_module("mcp_proxy_adapter")
    assert mod is not None
