"""Static checks for sandbox image tool availability."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_python_dev_image_bakes_diagnostic_toolset() -> None:
    text = _text("docker/python-dev/Dockerfile")
    for tool in (
        "ruff",
        "flake8",
        "black",
        "isort",
        "pylint",
        "mypy",
        "pytest",
        "pytest-cov",
        "coverage",
        "bandit",
        "vulture",
        "radon",
        "ipython",
        "pip-tools",
    ):
        assert tool in text


def test_python_dev_image_can_create_virtualenvs() -> None:
    text = _text("docker/python-dev/Dockerfile")
    assert "python -m venv /tmp/mcp-terminal-venv-smoke" in text
    assert "apt-get install -y --no-install-recommends python3-venv" not in text


def test_sandbox_images_include_core_os_utilities() -> None:
    for rel in (
        "docker/python-dev/Dockerfile",
        "docker/base-tools/Dockerfile",
        "docker/node-dev/Dockerfile",
    ):
        text = _text(rel)
        for pkg in ("git", "ripgrep", "fd-find", "tree", "jq", "yq", "curl", "wget"):
            assert pkg in text
        assert "ln -sf /usr/bin/fdfind /usr/local/bin/fd" in text
