"""
Re-invoke CLI entry points under ``<repo_root>/.venv`` when that tree is a real venv.

Uses ``pyvenv.cfg`` and a platform interpreter path (``bin/python`` / ``Scripts/python.exe``)
so a stray directory named ``.venv`` is not treated as an environment.

Skip re-exec with env ``MCP_TERMINAL_SKIP_VENV_REEXEC=1`` (true/yes/1).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_SKIP_ENV = "MCP_TERMINAL_SKIP_VENV_REEXEC"


def _pyvenv_cfg_looks_valid(text: str) -> bool:
    """Require at least one ``key = value`` line typical of PEP 405 ``pyvenv.cfg``."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip().lower()
        if key in ("home", "version", "include-system-site-packages", "implementation"):
            return True
    return False


def venv_interpreter_path(venv_root: Path) -> Optional[Path]:
    """Return the interpreter inside *venv_root*, or None if not present."""
    if sys.platform == "win32":
        p = venv_root / "Scripts" / "python.exe"
        return p if p.is_file() else None
    for name in ("python3", "python"):
        p = venv_root / "bin" / name
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def is_valid_python_venv(venv_root: Path) -> bool:
    """True if *venv_root* is a PEP 405 ``venv`` layout with a usable interpreter."""
    cfg = venv_root / "pyvenv.cfg"
    if not cfg.is_file():
        return False
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not _pyvenv_cfg_looks_valid(text):
        return False
    return venv_interpreter_path(venv_root) is not None


def repo_venv_interpreter(repo_root: Path, *, venv_dirname: str = ".venv") -> Optional[Path]:
    """Resolved interpreter path for ``repo_root / venv_dirname`` if valid, else None."""
    vdir = (repo_root / venv_dirname).resolve()
    if not vdir.is_dir():
        return None
    if not is_valid_python_venv(vdir):
        return None
    py = venv_interpreter_path(vdir)
    if py is None:
        return None
    try:
        return py.resolve()
    except OSError:
        return None


def ensure_repo_venv_interpreter(
    *,
    repo_root_path: Optional[Path] = None,
    venv_dirname: str = ".venv",
) -> None:
    """If repo ``.venv`` is valid and this process is not already using it, ``execv`` into it."""
    val = os.environ.get(_SKIP_ENV, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return
    from mcp_terminal.paths import repo_root as default_repo_root

    root = repo_root_path if repo_root_path is not None else default_repo_root()
    vpy = repo_venv_interpreter(root, venv_dirname=venv_dirname)
    if vpy is None:
        return
    try:
        current = Path(sys.executable).resolve()
    except OSError:
        return
    if current == vpy:
        return
    argv = [str(vpy)] + sys.argv[1:]
    os.execv(str(vpy), argv)
