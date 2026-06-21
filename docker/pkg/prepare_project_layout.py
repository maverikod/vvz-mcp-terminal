#!/usr/bin/env python3
"""Prepare watch-dir bind mounts and project .terminals/ ownership (root at install).

Bind-mounting host paths into Docker requires root on the host. This script runs
from postinst / ensure-host-permissions / docker-run (as root) to:

- verify configured watch_dirs exist and are traversable;
- ensure each discovered project root has ``.terminals/`` owned by the project
  directory owner (uid/gid from stat), mode 2770, so session state is writable
  regardless of which uid the service or sandbox uses internally.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

_MARKER = "projectid"
_PLACEHOLDER_MARKERS = ("WATCH_DIRS_ROOT", "CHANGE_ME", "REPLACE_ON_INSTALL", "MCP_PROXY_HOST")
_TERM_MODE = 0o2770
_FILE_MODE = 0o664


def _is_placeholder(path: str) -> bool:
    return any(marker in path for marker in _PLACEHOLDER_MARKERS)


def _iter_watch_anchors(config_path: Path) -> list[Path]:
    if not config_path.is_file():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    watch_dirs = data.get("watch_dirs")
    if not isinstance(watch_dirs, dict):
        return []
    directories = watch_dirs.get("directories")
    if not isinstance(directories, list):
        return []
    anchors: list[Path] = []
    for item in directories:
        if not isinstance(item, str) or not item.strip():
            continue
        raw = item.strip()
        if not raw.startswith("/") or _is_placeholder(raw):
            continue
        anchors.append(Path(raw))
    return anchors


def _discover_project_dirs(anchor: Path) -> list[Path]:
    projects: list[Path] = []
    if not anchor.is_dir():
        return projects
    marker = anchor / _MARKER
    if marker.is_file():
        projects.append(anchor.resolve())
    try:
        children = sorted(anchor.iterdir())
    except OSError:
        return projects
    for child in children:
        if not child.is_dir():
            continue
        if (child / _MARKER).is_file():
            projects.append(child.resolve())
    return projects


def _owner_ids(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_uid, st.st_gid


def _apply_owner_tree(path: Path, uid: int, gid: int, *, dir_mode: int, file_mode: int) -> None:
    os.chown(path, uid, gid)
    if path.is_dir():
        os.chmod(path, dir_mode)
        try:
            entries = list(path.iterdir())
        except OSError:
            return
        for child in entries:
            _apply_owner_tree(child, uid, gid, dir_mode=dir_mode, file_mode=file_mode)
    else:
        os.chmod(path, file_mode)


def prepare_terminals_dir(project_dir: Path) -> bool:
    """Create or normalize ``project_dir/.terminals`` for the project owner."""
    uid, gid = _owner_ids(project_dir)
    terminals = project_dir / ".terminals"
    terminals.mkdir(exist_ok=True)
    os.chown(terminals, uid, gid)
    os.chmod(terminals, _TERM_MODE)
    try:
        for session_dir in terminals.iterdir():
            if session_dir.is_dir():
                _apply_owner_tree(session_dir, uid, gid, dir_mode=_TERM_MODE, file_mode=_FILE_MODE)
    except OSError:
        pass
    return True


def verify_watch_anchor(anchor: Path) -> tuple[bool, str]:
    """Return (ok, message) for a configured watch anchor."""
    if not anchor.exists():
        return False, f"missing: {anchor}"
    if not anchor.is_dir():
        return False, f"not a directory: {anchor}"
    try:
        anchor.stat()
        os.access(anchor, os.R_OK | os.X_OK)
    except OSError as exc:
        return False, f"inaccessible: {anchor} ({exc})"
    return True, f"ok: {anchor}"


def prepare_from_config(config_path: Path) -> int:
    """Prepare all project ``.terminals/`` trees; print status lines; return exit code."""
    if os.geteuid() != 0:
        print("[ERROR] prepare_project_layout.py must run as root", file=sys.stderr)
        return 1

    issues = 0
    anchors = _iter_watch_anchors(config_path)
    if not anchors:
        print("[INFO] No resolved watch_dirs in config (skipped project layout prep)")
        return 0

    for anchor in anchors:
        ok, msg = verify_watch_anchor(anchor)
        if ok:
            print(f"[INFO] watch_dir {msg}")
        else:
            print(f"[WARN] watch_dir {msg}", file=sys.stderr)
            issues += 1
            continue

        for project_dir in _discover_project_dirs(anchor):
            try:
                prepare_terminals_dir(project_dir)
                uid, gid = _owner_ids(project_dir)
                t = project_dir / ".terminals"
                mode = stat.S_IMODE(t.stat().st_mode)
                print(
                    f"[INFO] .terminals {t} -> uid={uid} gid={gid} mode={mode:o}"
                )
            except OSError as exc:
                print(
                    f"[WARN] failed to prepare .terminals under {project_dir}: {exc}",
                    file=sys.stderr,
                )
                issues += 1

    if issues:
        print(f"[WARN] project layout prep finished with {issues} issue(s)", file=sys.stderr)
        return 0
    print("[SUCCESS] project layout prepared for watch_dirs")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: prepare_project_layout.py CONFIG.json", file=sys.stderr)
        return 2
    return prepare_from_config(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
