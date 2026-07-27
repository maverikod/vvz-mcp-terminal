"""Pipeline checks implemented as local Python subprocesses."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(argv: list[str]) -> int:
    proc = subprocess.run(tuple(argv), cwd=REPO_ROOT)  # noqa: S603
    return int(proc.returncode)


def _run_unittest_module(module_name: str) -> int:
    return _run([sys.executable, "-m", "unittest", "-q", module_name])


def run_sandbox_runtime_bootstrap_check() -> int:
    """Run the regression module that covers runtime bootstrap behavior."""
    return _run_unittest_module("tests.test_project_runtime_image")


def run_sandbox_toolchain_contract_check() -> int:
    """Run static toolchain coverage tests for the Python sandbox image."""
    return _run_unittest_module("tests.test_sandbox_toolchain_baseline")


def run_info_command_contract_check() -> int:
    """Run info-command contract tests."""
    return _run_unittest_module("tests.test_info_contract")


def run_pipeline_cli_contract_check() -> int:
    """Run pipeline package contract tests."""
    return _run_unittest_module("tests.test_pipeline_cli")


def run_package_config_contract_check() -> int:
    """Run Debian config-preservation contract tests."""
    return _run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "tests.test_build_entrypoint_contract",
            "tests.test_packaging_template_contract",
            "tests.test_install_server_config",
            "tests.test_build_deb_contract",
            "tests.test_systemd_unit_contract",
        ]
    )


def run_session_lifecycle_contract_check() -> int:
    """Run session lifecycle regressions (restart adoption, bootstrap hints)."""
    return _run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "tests.test_session_across_restart",
            "tests.test_session_bootstrap_queue",
        ]
    )


def run_pytest_suite_check() -> int:
    """Run the full pytest suite when pytest is available."""
    if importlib.util.find_spec("pytest") is None:
        print("SKIP pytest_suite: pytest is not installed in the active interpreter")
        return 0
    return _run([sys.executable, "-m", "pytest", "-q"])
