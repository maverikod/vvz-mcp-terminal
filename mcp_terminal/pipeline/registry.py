"""Named checks exposed by the project pipeline CLI."""

from __future__ import annotations

from mcp_terminal.pipeline.base import Check
from mcp_terminal.pipeline.checks.live_server_api import run_live_server_api_check
from mcp_terminal.pipeline.checks.python_contracts import (
    run_info_command_contract_check,
    run_package_config_contract_check,
    run_pipeline_cli_contract_check,
    run_pytest_suite_check,
    run_sandbox_runtime_bootstrap_check,
    run_sandbox_toolchain_contract_check,
)


PIPELINE_CHECKS: tuple[Check, ...] = (
    Check(
        name="sandbox_runtime_bootstrap",
        description="Regression tests for Python project runtime bootstrap and image reuse.",
        runner=run_sandbox_runtime_bootstrap_check,
    ),
    Check(
        name="sandbox_toolchain_contract",
        description="Static contract for baseline Python sandbox tools and utilities.",
        runner=run_sandbox_toolchain_contract_check,
    ),
    Check(
        name="info_command_contract",
        description="Contract tests for info pagination and CLI documentation coverage.",
        runner=run_info_command_contract_check,
    ),
    Check(
        name="pipeline_cli_contract",
        description="Contract tests for the pipeline package CLI and named-check registry.",
        runner=run_pipeline_cli_contract_check,
    ),
    Check(
        name="package_config_contract",
        description="Contract tests that Debian install preserves customized term_server.json.",
        runner=run_package_config_contract_check,
    ),
    Check(
        name="pytest_suite",
        description="Run the full pytest suite when pytest is available in the active interpreter.",
        runner=run_pytest_suite_check,
    ),
    Check(
        name="live_server_api",
        description="Probe the deployed HTTPS server via /health and /openapi.json.",
        runner=run_live_server_api_check,
    ),
)


def pipeline_check_by_name(name: str) -> Check | None:
    """Return the registered check for *name*, or ``None`` if missing."""
    for check in PIPELINE_CHECKS:
        if check.name == name:
            return check
    return None
