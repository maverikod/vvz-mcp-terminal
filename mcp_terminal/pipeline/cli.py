"""Project verification entrypoint."""

from __future__ import annotations

import argparse
import sys

from mcp_terminal.pipeline.registry import PIPELINE_CHECKS, pipeline_check_by_name
from mcp_terminal.repo_venv import ensure_repo_venv_interpreter


def _list_checks() -> int:
    for check in PIPELINE_CHECKS:
        print(f"{check.name}\t{check.description}")
    return 0


def _run_named_check(name: str) -> int:
    check = pipeline_check_by_name(name)
    if check is None:
        print(f"unknown check: {name}", file=sys.stderr)
        return 2
    return int(check.runner())


def _run_all_checks() -> int:
    for check in PIPELINE_CHECKS:
        exit_code = int(check.runner())
        if exit_code != 0:
            return exit_code
    return 0


def main() -> None:
    ensure_repo_venv_interpreter()
    parser = argparse.ArgumentParser(description="Project verification pipeline")
    parser.add_argument("check", nargs="?", help="Optional named check to run")
    parser.add_argument("--list", action="store_true", dest="list_checks")
    args = parser.parse_args()

    if args.list_checks:
        raise SystemExit(_list_checks())
    if args.check:
        raise SystemExit(_run_named_check(args.check))
    raise SystemExit(_run_all_checks())
