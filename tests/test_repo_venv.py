"""Tests for ``mcp_terminal.repo_venv`` (PEP 405 detection, no re-exec in tests)."""

from __future__ import annotations

import textwrap

from mcp_terminal.repo_venv import (
    is_valid_python_venv,
    repo_venv_interpreter,
    venv_interpreter_path,
)


def test_is_valid_python_venv_accepts_minimal_unix_layout(tmp_path) -> None:
    vdir = tmp_path / ".venv"
    vdir.mkdir()
    (vdir / "pyvenv.cfg").write_text(
        textwrap.dedent(
            """\
            home = /usr/bin
            include-system-site-packages = false
            version = 3.12.0
            """
        ),
        encoding="utf-8",
    )
    bin_dir = vdir / "bin"
    bin_dir.mkdir()
    py = bin_dir / "python3"
    py.write_text("#!/bin/sh\necho\n", encoding="utf-8")
    py.chmod(0o755)
    assert is_valid_python_venv(vdir) is True
    assert venv_interpreter_path(vdir) == py


def test_is_valid_python_venv_rejects_missing_pyvenv_cfg(tmp_path) -> None:
    vdir = tmp_path / ".venv"
    vdir.mkdir()
    assert is_valid_python_venv(vdir) is False


def test_is_valid_python_venv_rejects_empty_cfg(tmp_path) -> None:
    vdir = tmp_path / ".venv"
    vdir.mkdir()
    (vdir / "pyvenv.cfg").write_text("# nothing\n", encoding="utf-8")
    bin_dir = vdir / "bin"
    bin_dir.mkdir()
    py = bin_dir / "python3"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    py.chmod(0o755)
    assert is_valid_python_venv(vdir) is False


def test_is_valid_python_venv_rejects_no_interpreter(tmp_path) -> None:
    vdir = tmp_path / ".venv"
    vdir.mkdir()
    (vdir / "pyvenv.cfg").write_text("home = /x\nversion = 3\n", encoding="utf-8")
    (vdir / "bin").mkdir()
    assert is_valid_python_venv(vdir) is False


def test_repo_venv_interpreter_none_when_not_dir(tmp_path) -> None:
    assert repo_venv_interpreter(tmp_path, venv_dirname="nope") is None
