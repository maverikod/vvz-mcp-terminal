#!/usr/bin/env python3
"""Derive Docker bind-mount and supplementary group specs for watch_dirs (docker-run)."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

_PLACEHOLDER_MARKERS = ("WATCH_DIRS_ROOT", "CHANGE_ME", "REPLACE_ON_INSTALL", "MCP_PROXY_HOST")


def _host_path_from_bind_spec(spec: str) -> str | None:
    spec = spec.strip()
    if not spec:
        return None
    host = spec.split(":", 1)[0].strip()
    return host or None


def _is_placeholder(path: str) -> bool:
    return any(marker in path for marker in _PLACEHOLDER_MARKERS)


def _iter_config_watch_paths(config_path: Path) -> list[str]:
    if not config_path.is_file():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    watch_dirs = data.get("watch_dirs")
    if not isinstance(watch_dirs, dict):
        return []
    directories = watch_dirs.get("directories")
    if not isinstance(directories, list):
        return []
    paths: list[str] = []
    for item in directories:
        if not isinstance(item, str) or not item.strip():
            continue
        path = item.strip()
        if not path.startswith("/") or _is_placeholder(path):
            continue
        paths.append(path)
    return paths


def watch_dir_supplementary_gids(config_path: Path) -> list[int]:
    """Return host gids the service container needs to traverse watch_dirs (``--group-add``)."""
    gids: set[int] = set()
    for path_str in _iter_config_watch_paths(config_path):
        try:
            st = os.stat(path_str, follow_symlinks=True)
        except OSError:
            continue
        if not stat.S_ISDIR(st.st_mode):
            continue
        mode = st.st_mode & 0o777
        # World-readable/executable (e.g. 755): no extra group in container.
        if (mode & 0o005) == 0o005:
            continue
        # Group permissions present (e.g. 750): service user needs st_gid via --group-add.
        if (mode & 0o050) != 0:
            gids.add(st.st_gid)
    return sorted(gids)


def watch_dir_bind_specs(
    config_path: Path,
    *,
    extra_binds: str = "",
) -> list[str]:
    """Return ``host:container:ro`` bind specs for configured watch directories."""
    if not config_path.is_file():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    watch_dirs = data.get("watch_dirs")
    if not isinstance(watch_dirs, dict):
        return []
    directories = watch_dirs.get("directories")
    if not isinstance(directories, list):
        return []

    already: set[str] = set()
    for spec in extra_binds.split():
        host = _host_path_from_bind_spec(spec)
        if host:
            already.add(host.rstrip("/"))

    specs: list[str] = []
    for path in _iter_config_watch_paths(config_path):
        norm = path.rstrip("/")
        if norm in already:
            continue
        specs.append(f"{path}:{path}")
        already.add(norm)
    return specs


def _main_bind_specs(config_path: Path, extra: str) -> int:
    for spec in watch_dir_bind_specs(config_path, extra_binds=extra):
        print(spec)
    return 0


def _main_supplementary_gids(config_path: Path) -> int:
    for gid in watch_dir_supplementary_gids(config_path):
        print(gid)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: watch_dir_bind_specs.py CONFIG.json [EXTRA_BINDS...]\n"
            "       watch_dir_bind_specs.py --supplementary-gids CONFIG.json",
            file=sys.stderr,
        )
        return 2
    if sys.argv[1] == "--supplementary-gids":
        if len(sys.argv) != 3:
            print("Usage: watch_dir_bind_specs.py --supplementary-gids CONFIG.json", file=sys.stderr)
            return 2
        return _main_supplementary_gids(Path(sys.argv[2]))
    config_path = Path(sys.argv[1])
    extra = " ".join(sys.argv[2:])
    return _main_bind_specs(config_path, extra)


if __name__ == "__main__":
    raise SystemExit(main())
