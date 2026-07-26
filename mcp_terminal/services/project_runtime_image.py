"""Per-project Docker runtime image under ``.mcp_terminal/runtime/`` (C-005).

On session open (once per fingerprint): ``docker build`` with a generated Dockerfile
when the project exposes a Python install manifest. Stores ``image_state.json`` with
``image_id`` from ``docker image inspect`` for later verification.

``terminal_run`` uses that local tag when state is valid; rejects stale/missing image.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mcp_terminal.services.host_run_identity import prepare_path_for_project_owner_access

logger = logging.getLogger(__name__)

RUNTIME_SUBDIR = Path(".mcp_terminal") / "runtime"
STATE_NAME = "image_state.json"
CONTEXT_SUBDIR = "build_context"
DOCKERFILE_NAME = "Dockerfile"
# Bump when the generated Dockerfile recipe or build context layout changes.
DOCKERFILE_TEMPLATE_VERSION = "4"

_MANIFEST_FILES = (
    "requirements-dev.txt",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "MANIFEST.in",
)
_METADATA_FILES = (
    "LICENSE",
    "README",
    "README.md",
    "README.rst",
    "README.txt",
)


def _runtime_dir(project_dir: Path) -> Path:
    return project_dir / RUNTIME_SUBDIR


def _runtime_context_dir(project_dir: Path) -> Path:
    return _runtime_dir(project_dir) / CONTEXT_SUBDIR


def _state_path(project_dir: Path) -> Path:
    return _runtime_dir(project_dir) / STATE_NAME


def _dockerfile_path(project_dir: Path) -> Path:
    return _runtime_context_dir(project_dir) / DOCKERFILE_NAME


def _image_tag(project_id: str) -> str:
    """Stable local tag per project_id (Docker-safe)."""
    h = hashlib.sha256(project_id.strip().lower().encode()).hexdigest()[:12]
    return f"mcp-terminal:pid-{h}"


def _project_has_dev_extra(project_dir: Path) -> bool:
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.is_file():
        return False
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = data.get("project")
    if not isinstance(project, dict):
        return False
    optional = project.get("optional-dependencies")
    return isinstance(optional, dict) and "dev" in optional


def _runtime_install_command(project_dir: Path) -> Optional[str]:
    if (project_dir / "requirements-dev.txt").is_file():
        return "pip install --no-cache-dir -r requirements-dev.txt"
    if (project_dir / "requirements.txt").is_file():
        return "pip install --no-cache-dir -r requirements.txt"
    if (project_dir / "pyproject.toml").is_file():
        if _project_has_dev_extra(project_dir):
            return "pip install --no-cache-dir -e .[dev]"
        return "pip install --no-cache-dir -e ."
    if (project_dir / "setup.py").is_file() or (project_dir / "setup.cfg").is_file():
        return "pip install --no-cache-dir -e ."
    return None


def _project_source_entries(project_dir: Path) -> tuple[str, ...]:
    entries: list[str] = []
    if (project_dir / "src").is_dir():
        entries.append("src")
    for child in sorted(project_dir.iterdir(), key=lambda p: p.name):
        if child.name.startswith("."):
            continue
        if child.name in {"build", "dist", "__pycache__"}:
            continue
        if child.is_dir() and (child / "__init__.py").is_file():
            entries.append(child.name)
        elif child.is_file() and child.suffix == ".py":
            entries.append(child.name)
    return tuple(dict.fromkeys(entries))


def _runtime_context_entries(project_dir: Path) -> tuple[str, ...]:
    entries: list[str] = []
    for name in _MANIFEST_FILES + _METADATA_FILES:
        if (project_dir / name).exists():
            entries.append(name)
    entries.extend(_project_source_entries(project_dir))
    return tuple(dict.fromkeys(entries))


def _copy_runtime_context_entry(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _prepare_runtime_build_context(project_dir: Path) -> Tuple[Path, Optional[str]]:
    context_dir = _runtime_context_dir(project_dir)
    if context_dir.exists():
        shutil.rmtree(context_dir)
    context_dir.mkdir(parents=True, exist_ok=True)
    entries = _runtime_context_entries(project_dir)
    if not entries:
        return context_dir, "no_python_project_manifest"
    for rel_name in entries:
        source = project_dir / rel_name
        if source.exists():
            _copy_runtime_context_entry(source, context_dir / rel_name)
    return context_dir, None


def _write_runtime_dockerfile(
    project_dir: Path,
    *,
    base_image_ref: str,
    install_command: str,
) -> None:
    body = (
        "# Generated by mcp_terminal -- do not edit. Rebuilt when fingerprint changes.\n"
        f"FROM {base_image_ref}\n"
        "ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \\\n"
        "    PYTHONDONTWRITEBYTECODE=1\n"
        "WORKDIR /workspace\n"
        "COPY . /workspace\n"
        "RUN python -m pip install --upgrade pip setuptools wheel \\\n"
        f"    && {install_command}\n"
    )
    _dockerfile_path(project_dir).write_text(body, encoding="utf-8")


def runtime_fingerprint(project_dir: Path, *, image_profile: str) -> str:
    """Hash of inputs that define the project runtime image."""
    h = hashlib.sha256()
    h.update(DOCKERFILE_TEMPLATE_VERSION.encode())
    h.update(b"\0")
    h.update(image_profile.encode())
    install_command = _runtime_install_command(project_dir)
    if install_command is not None:
        h.update(b"\0")
        h.update(install_command.encode())
    for rel_name in _runtime_context_entries(project_dir):
        path = project_dir / rel_name
        if not path.is_file():
            continue
        h.update(b"\0")
        h.update(rel_name.encode())
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def _docker_image_id(image_tag: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["docker", "image", "inspect", image_tag, "--format", "{{.Id}}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        tid = out.strip()
        return tid or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("docker image inspect %s: %s", image_tag, exc)
        return None


def verify_runtime_image_state(project_dir: Path) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason) comparing ``image_state.json`` to live ``docker image inspect``."""
    sp = _state_path(project_dir)
    if not sp.is_file():
        return False, "no_state"
    try:
        data: Dict[str, Any] = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "state_corrupt"
    tag = data.get("image_tag")
    expected_id = data.get("image_id")
    if not isinstance(tag, str) or not isinstance(expected_id, str):
        return False, "state_incomplete"
    current = _docker_image_id(tag)
    if current is None:
        return False, "image_missing"
    if current != expected_id:
        return False, "image_id_mismatch"
    return True, None


def resolve_execution_image(
    project_dir: Path,
    *,
    project_id: str,
    image_profile: str,
    stock_image_ref: str,
) -> Tuple[str, Optional[str]]:
    """Pick local project image tag if state valid and fingerprint matches; else stock.

    Returns:
        (image_ref, error_code) where error_code is set when a local state exists but is unusable.
    """
    if not image_profile.startswith("python_"):
        return stock_image_ref, None
    if _runtime_install_command(project_dir) is None:
        return stock_image_ref, None
    fp_now = runtime_fingerprint(project_dir, image_profile=image_profile)
    sp = _state_path(project_dir)
    if not sp.is_file():
        return stock_image_ref, None
    try:
        data: Dict[str, Any] = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return stock_image_ref, "RUNTIME_IMAGE_STATE_CORRUPT"
    if data.get("fingerprint") != fp_now:
        return stock_image_ref, "RUNTIME_IMAGE_STALE"
    tag = data.get("image_tag")
    if not isinstance(tag, str) or not tag:
        return stock_image_ref, "RUNTIME_IMAGE_STATE_INCOMPLETE"
    ok, reason = verify_runtime_image_state(project_dir)
    if not ok:
        code = f"RUNTIME_IMAGE_{reason.upper()}" if reason else "RUNTIME_IMAGE_INVALID"
        return stock_image_ref, code
    return tag, None


def ensure_project_runtime_image(
    project_dir: Path,
    *,
    project_id: str,
    image_profile: str,
    stock_image_ref: Optional[str] = None,
    build_timeout_seconds: int = 1200,
) -> Tuple[bool, bool, int, str]:
    """Build or reuse project runtime image. Returns (success, skipped_build, exit_code, detail).

    When no Python install manifest is present or profile is not Python-based, no-op (skipped).
    """
    if not image_profile.startswith("python_"):
        return True, True, 0, "not_python_profile"
    install_command = _runtime_install_command(project_dir)
    if install_command is None:
        return True, True, 0, "no_python_project_manifest"
    base_image_ref = stock_image_ref
    if base_image_ref is None:
        from mcp_terminal.services.sandbox_policy import IMAGE_PROFILE_MAP

        base_image_ref = IMAGE_PROFILE_MAP.get(image_profile)
    if not isinstance(base_image_ref, str) or not base_image_ref:
        return False, False, 1, "unknown_base_image"

    rd = _runtime_dir(project_dir)
    rd.mkdir(parents=True, exist_ok=True)
    prepare_path_for_project_owner_access(project_dir, rd)
    context_dir, context_err = _prepare_runtime_build_context(project_dir)
    if context_err is not None:
        return True, True, 0, context_err
    _write_runtime_dockerfile(
        project_dir,
        base_image_ref=base_image_ref,
        install_command=install_command,
    )

    fp = runtime_fingerprint(project_dir, image_profile=image_profile)
    tag = _image_tag(project_id)
    sp = _state_path(project_dir)
    if sp.is_file():
        try:
            prev = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
        if (
            isinstance(prev, dict)
            and prev.get("fingerprint") == fp
            and prev.get("image_tag") == tag
        ):
            ok, _reason = verify_runtime_image_state(project_dir)
            if ok:
                return True, True, 0, "image_verified"

    cmd = [
        "docker",
        "build",
        "-t",
        tag,
        "-f",
        str(_dockerfile_path(project_dir).resolve()),
        str(context_dir.resolve()),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=build_timeout_seconds,
        )  # noqa: S603
    except FileNotFoundError:
        return False, False, 127, "docker_not_found"
    except subprocess.TimeoutExpired:
        return False, False, 124, "docker_build_timeout"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-8000:]
        return False, False, proc.returncode, tail

    img_id = _docker_image_id(tag)
    if not img_id:
        return False, False, 1, "inspect_failed_after_build"

    payload = {
        "fingerprint": fp,
        "image_tag": tag,
        "image_id": img_id,
        "image_profile": image_profile,
        "dockerfile_template_version": DOCKERFILE_TEMPLATE_VERSION,
    }
    sp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True, False, 0, "built"


def runtime_image_summary(project_dir: Path) -> Optional[Dict[str, Any]]:
    sp = _state_path(project_dir)
    if not sp.is_file():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
