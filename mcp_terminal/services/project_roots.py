"""
Merge **watchable parent directories** (each contains project folders).

A watchable directory is a host path whose **immediate subdirectories** are
candidate project roots (each subdirectory may contain a ``projectid`` file).

``watch_dirs.directories`` lists such paths from ``term_server.json``. When
``code_analysis.enabled``, the Code Analysis Server ``list_watch_dirs`` RPC
returns the same kind of paths (parents of project trees); they are merged in.
Duplicates are removed while preserving order.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

from mcp_terminal.code_analysis_watch import list_watch_dirs_sync

logger = logging.getLogger(__name__)


def merge_unique_root_paths(paths: Iterable[Path]) -> List[Path]:
    """Return unique resolved directories; first occurrence wins."""
    seen: set[str] = set()
    out: List[Path] = []
    for p in paths:
        try:
            rp = p.resolve()
        except OSError as exc:
            logger.debug("Skipping root %s: %s", p, exc)
            continue
        if not rp.is_dir():
            logger.debug("Skipping root (not a directory): %s", rp)
            continue
        key = str(rp)
        if key in seen:
            continue
        seen.add(key)
        out.append(rp)
    return out


def roots_from_watch_dirs_config(app_config: Dict[str, Any]) -> List[Path]:
    """Paths from ``watch_dirs.directories`` (each dir contains project roots as subdirs)."""
    section = app_config.get("watch_dirs")
    if not isinstance(section, dict):
        return []
    raw = section.get("directories")
    if not isinstance(raw, list):
        return []
    out: List[Path] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        out.append(Path(item.strip()).expanduser())
    return out


def roots_from_code_analysis(
    app_config: Dict[str, Any],
    *,
    config_path: Path,
    log_errors: bool = True,
) -> List[Path]:
    """Paths from Code Analysis ``list_watch_dirs`` (parent dirs that contain projects)."""
    section = app_config.get("code_analysis")
    if not isinstance(section, dict) or not section.get("enabled"):
        return []
    try:
        rows = list_watch_dirs_sync(section, config_path=config_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        if log_errors:
            logger.warning("code_analysis.list_watch_dirs failed: %s", exc)
        return []
    out: List[Path] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("absolute_path")
        if not path or not isinstance(path, str):
            continue
        out.append(Path(path.strip()).expanduser())
    return out


def merged_project_anchor_dirs(
    app_config: Dict[str, Any],
    *,
    config_path: Path,
    log_code_analysis_errors: bool = True,
) -> List[Path]:
    """Union of ``watch_dirs.directories`` and Code Analysis ``list_watch_dirs`` paths.

    Each path is a **parent** directory whose immediate subdirectories (and
    optionally the directory itself if it contains ``projectid``) are scanned.
    Duplicates are removed while preserving order.

    When both sources are empty or disabled, returns an empty list (no implicit
    fallback to the mcp_terminal package tree).
    """
    combined: List[Path] = []
    combined.extend(roots_from_watch_dirs_config(app_config))
    combined.extend(
        roots_from_code_analysis(
            app_config, config_path=config_path, log_errors=log_code_analysis_errors
        )
    )
    merged = merge_unique_root_paths(combined)
    if not merged:
        logger.debug(
            "No project watch anchors: populate watch_dirs.directories and/or "
            "enable code_analysis to merge list_watch_dirs paths."
        )
    return merged


def resolve_projects_root_dir(app_config: Dict[str, Any], *, config_path: Path) -> Path:
    """Return the first merged anchor directory (backward compatibility).

    Prefer ``merged_project_anchor_dirs`` for multi-root callers.

    Raises:
        ValueError: When no watch anchor directories are configured or resolved.
    """
    roots = merged_project_anchor_dirs(app_config, config_path=config_path)
    if not roots:
        raise ValueError(
            "No project watch anchors: set watch_dirs.directories and/or enable "
            "code_analysis so list_watch_dirs can supply paths."
        )
    return roots[0]
