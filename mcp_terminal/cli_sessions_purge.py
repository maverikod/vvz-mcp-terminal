"""
CLI: purge all terminal session directories and stop sandbox containers.

Used by ``termgr purge-sessions`` (host-side only; no JSON-RPC / MCP).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Set

from mcp_terminal.services.project_roots import merged_project_anchor_dirs
from mcp_terminal.services.session_store import SessionStore

_MCP_TERMINAL_IMAGE_PREFIX = "mcp-terminal:pid-"
_SESSION_CONTAINER_PREFIX = "mcp-term-"


@dataclass
class PurgeReport:
    """Summary of a ``purge_all_terminal_sessions`` run."""

    containers_killed: int = 0
    session_dirs_removed: int = 0
    terminals_trees_removed: int = 0
    runtime_dirs_removed: int = 0
    errors: List[str] = field(default_factory=list)


def discover_terminals_dirs(config_path: Path) -> List[Path]:
    """Return ``.terminals`` directories under watch anchors and their project children."""
    try:
        app_config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read config {config_path}: {exc}") from exc
    if not isinstance(app_config, dict):
        raise ValueError(f"Config root must be an object: {config_path}")

    anchors = merged_project_anchor_dirs(app_config, config_path=config_path)
    found: Set[Path] = set()
    terminals_name = SessionStore.TERMINALS_DIR

    def _add_terminals(parent: Path) -> None:
        td = parent / terminals_name
        if td.is_dir():
            found.add(td.resolve())

    for anchor in anchors:
        _add_terminals(anchor)
        try:
            children = list(anchor.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                _add_terminals(child)
    return sorted(found)


def kill_mcp_terminal_sandbox_containers(*, dry_run: bool = False) -> int:
    """SIGKILL running containers whose image tag starts with ``mcp-terminal:pid-``."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.ID}}\t{{.Image}}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except FileNotFoundError:
        return 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 0

    killed = 0
    for line in out.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        cid, image = line.split("\t", 1)
        if not image.startswith(_MCP_TERMINAL_IMAGE_PREFIX):
            continue
        if dry_run:
            killed += 1
            continue
        try:
            subprocess.run(
                ["docker", "kill", "-9", cid],
                capture_output=True,
                timeout=30,
                check=False,
            )
            killed += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    return killed


def kill_session_containers(*, dry_run: bool = False) -> int:
    """Remove session idle containers (``mcp-term-*`` names or session label)."""
    try:
        fmt = "{{.ID}}\t{{.Names}}\t{{.Label \"mcp.terminal.session\"}}"
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--format", fmt],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except FileNotFoundError:
        return 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 0

    removed = 0
    for line in out.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        cid = parts[0]
        names = parts[1]
        label = parts[2] if len(parts) > 2 else ""
        if label != "true" and not any(
            n.startswith(_SESSION_CONTAINER_PREFIX) for n in names.split(",")
        ):
            continue
        if dry_run:
            removed += 1
            continue
        try:
            subprocess.run(
                ["docker", "rm", "-f", cid],
                capture_output=True,
                timeout=30,
                check=False,
            )
            removed += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    return removed


def purge_all_terminal_sessions(
    config_path: Path,
    *,
    dry_run: bool = False,
    kill_docker: bool = True,
    remove_runtime: bool = False,
) -> PurgeReport:
    """Remove every ``.terminals/<session_id>/`` tree; optionally kill Docker sandboxes."""
    report = PurgeReport()
    if kill_docker:
        report.containers_killed = kill_mcp_terminal_sandbox_containers(dry_run=dry_run)
        report.containers_killed += kill_session_containers(dry_run=dry_run)

    try:
        terminals_dirs = discover_terminals_dirs(config_path)
    except ValueError as exc:
        report.errors.append(str(exc))
        return report

    for terminals_root in terminals_dirs:
        try:
            session_dirs = [p for p in terminals_root.iterdir() if p.is_dir()]
        except OSError as exc:
            report.errors.append(f"Cannot list {terminals_root}: {exc}")
            continue
        for session_dir in session_dirs:
            if dry_run:
                report.session_dirs_removed += 1
            else:
                try:
                    shutil.rmtree(session_dir, ignore_errors=False)
                    report.session_dirs_removed += 1
                except OSError as exc:
                    report.errors.append(f"Cannot remove {session_dir}: {exc}")

        if not dry_run:
            try:
                remaining = list(terminals_root.iterdir())
            except OSError:
                remaining = [Path(".")]
            if not remaining:
                try:
                    terminals_root.rmdir()
                    report.terminals_trees_removed += 1
                except OSError as exc:
                    report.errors.append(f"Cannot rmdir {terminals_root}: {exc}")

        if remove_runtime:
            runtime_dir = terminals_root.parent / ".mcp_terminal"
            if runtime_dir.is_dir():
                if dry_run:
                    report.runtime_dirs_removed += 1
                else:
                    try:
                        shutil.rmtree(runtime_dir, ignore_errors=False)
                        report.runtime_dirs_removed += 1
                    except OSError as exc:
                        report.errors.append(f"Cannot remove {runtime_dir}: {exc}")

    return report


def add_purge_sessions_parser(sub: Any) -> None:
    """Register ``purge-sessions`` on a ``termgr`` subparser group."""
    p = sub.add_parser(
        "purge-sessions",
        help="SIGKILL mcp-terminal sandbox containers and delete all .terminals/ session dirs",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="term_server.json path (default: configs/term_server.json under repo root)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without deleting or killing",
    )
    p.add_argument(
        "--no-kill-docker",
        action="store_true",
        help="Skip docker kill for containers using mcp-terminal:pid-* images",
    )
    p.add_argument(
        "--remove-runtime",
        action="store_true",
        help="Also remove each project's .mcp_terminal/ runtime build dir",
    )
    p.set_defaults(func=cmd_purge_sessions)


def cmd_purge_sessions(args: argparse.Namespace) -> int:
    from mcp_terminal.term_config import default_config_path

    cfg = args.config if args.config is not None else default_config_path()
    if cfg is None or not Path(cfg).is_file():
        print(f"Config not found: {cfg}")
        return 1
    config_path = Path(cfg).resolve()

    report = purge_all_terminal_sessions(
        config_path,
        dry_run=bool(args.dry_run),
        kill_docker=not bool(args.no_kill_docker),
        remove_runtime=bool(args.remove_runtime),
    )
    mode = "dry-run" if args.dry_run else "done"
    print(
        f"purge-sessions ({mode}): "
        f"containers_killed={report.containers_killed} "
        f"session_dirs_removed={report.session_dirs_removed} "
        f"empty_terminals_trees_removed={report.terminals_trees_removed} "
        f"runtime_dirs_removed={report.runtime_dirs_removed}"
    )
    for err in report.errors:
        print(f"  error: {err}", file=sys.stderr)
    return 1 if report.errors else 0
