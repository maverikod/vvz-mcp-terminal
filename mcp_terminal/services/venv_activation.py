"""
Project ``.venv`` activation for session exec scripts.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shlex
import textwrap
from pathlib import Path

WORKSPACE_VENV_ROOT = "/workspace/.venv"


def venv_activation_shell_block(*, use_venv: bool = True) -> str:
    """
    Bash lines to run after ``cd`` under ``/workspace``.

    Prepends the project venv to PATH (no ``source activate``). Console scripts
    (``casmgr``, ``pytest``, …) and ``python`` resolve from ``.venv/bin``.
    """
    if not use_venv:
        return ""
    root = WORKSPACE_VENV_ROOT
    return textwrap.dedent(
        f"""\
        if [ -d {root}/bin ]; then
          export VIRTUAL_ENV={root}
          export PATH="{root}/bin:${{PATH}}"
        fi
        """
    )


def host_venv_activation_shell_block(project_dir: Path, *, use_venv: bool = True) -> str:
    """Bash lines to prepend ``project_dir/.venv/bin`` on the host after ``cd``."""
    if not use_venv:
        return ""
    root = project_dir.resolve() / ".venv"
    root_q = shlex.quote(str(root))
    return textwrap.dedent(
        f"""\
        if [ -d {root_q}/bin ]; then
          export VIRTUAL_ENV={root_q}
          export PATH="{root_q}/bin:${{PATH}}"
        fi
        """
    )


def project_has_usable_venv(project_dir: Path) -> bool:
    """True when ``project_dir/.venv`` is a valid PEP 405 environment."""
    from mcp_terminal.repo_venv import is_valid_python_venv

    return is_valid_python_venv(project_dir / ".venv")
