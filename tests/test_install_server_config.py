"""Tests for install-server-config.sh (config never overwritten when present)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pkg" / "install-server-config.sh"
TEMPLATE = Path(__file__).resolve().parents[1] / "docker" / "packaging" / "term_server.json.template"


def _run_install(config_dir: Path, template: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), str(config_dir), str(template), "mcp-terminal"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_creates_config_when_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / "etc" / "mcp-terminal"
    proc = _run_install(config_dir, TEMPLATE)
    assert proc.returncode == 0, proc.stderr
    config = config_dir / "term_server.json"
    assert config.is_file()
    assert "REPLACE_ON_INSTALL" not in config.read_text(encoding="utf-8")
    assert "Installed new" in proc.stdout


def test_preserves_customized_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "etc" / "mcp-terminal"
    config_dir.mkdir(parents=True)
    config = config_dir / "term_server.json"
    custom = {"terminal": {"host_execution": {"enabled": False, "custom": True}}}
    config.write_text(json.dumps(custom), encoding="utf-8")

    proc = _run_install(config_dir, TEMPLATE)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(config.read_text(encoding="utf-8")) == custom
    assert "Preserved existing" in proc.stdout
    sidecar = config_dir / "term_server.json.template"
    assert sidecar.is_file()
    assert "host_execution" in sidecar.read_text(encoding="utf-8")


def test_finalizes_pristine_placeholder_only(tmp_path: Path) -> None:
    config_dir = tmp_path / "etc" / "mcp-terminal"
    config_dir.mkdir(parents=True)
    config = config_dir / "term_server.json"
    body = TEMPLATE.read_text(encoding="utf-8")
    assert "REPLACE_ON_INSTALL" in body
    config.write_text(body, encoding="utf-8")

    proc = _run_install(config_dir, TEMPLATE)
    assert proc.returncode == 0, proc.stderr
    updated = config.read_text(encoding="utf-8")
    assert "REPLACE_ON_INSTALL" not in updated
    assert "Finalized new" in proc.stdout
