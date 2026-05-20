"""
Hostile-input unit tests from tech_spec §24.

Covers sandbox policy and output-reader rejections at unit level using tmp_path.
No test_data/ fixtures.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_terminal.services.output_reader import OutputReader
from mcp_terminal.services.sandbox_policy import SandboxPolicy


def _policy(**overrides: object):
    base = dict(
        project_id="00000000-0000-4000-8000-000000000001",
        execution_kind="argv",
        cwd=".",
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        command=None,
        argv=["echo", "ok"],
    )
    base.update(overrides)
    return SandboxPolicy().validate(**base)


def test_hostile_rejects_docker_sock_path_in_shell_command() -> None:
    """§24: attempt reading /var/run/docker.sock via command is rejected."""
    result = _policy(
        execution_kind="shell",
        command="cat /var/run/docker.sock",
        argv=None,
    )
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"
    assert result.rejected_field == "command"


def test_hostile_rejects_network_host_option_in_shell_command() -> None:
    """§24: forbidden --network=host in shell command is rejected."""
    result = _policy(
        execution_kind="shell",
        command="curl --network=host https://example.com",
        argv=None,
    )
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"


@pytest.mark.parametrize("network", ["host", "open", "bridge"])
def test_hostile_rejects_forbidden_network_mode(network: str) -> None:
    """§24: attempt requesting forbidden network mode."""
    result = _policy(network=network)
    assert not result.permitted
    assert result.error_code == "NETWORK_MODE_NOT_ALLOWED"
    assert result.rejected_field == "network"


@pytest.mark.parametrize("cwd", ["/", "/tmp", "/workspace", "..", "foo/../bar"])
def test_hostile_rejects_absolute_or_traversal_cwd(cwd: str) -> None:
    """§24: attempt cwd=/ and path traversal in cwd."""
    result = _policy(cwd=cwd)
    assert not result.permitted
    assert result.error_code == "INVALID_CWD"
    assert result.rejected_field == "cwd"


def test_hostile_build_mount_spec_rejects_absolute_cwd(tmp_path: Path) -> None:
    """§24: absolute cwd outside workspace rejected at mount build."""
    spec, err = SandboxPolicy().build_mount_spec(
        workspace_source=tmp_path,
        mode="read_only",
        cwd="/etc",
    )
    assert spec is None
    assert err is not None
    assert not err.permitted
    assert err.error_code == "INVALID_CWD"


def test_hostile_rejects_privileged_option_in_command() -> None:
    """§24: attempt requesting privileged options."""
    result = _policy(
        execution_kind="shell",
        command="docker run --privileged alpine",
        argv=None,
    )
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"


def test_hostile_rejects_arbitrary_image_profile() -> None:
    """§24: attempt requesting arbitrary image."""
    result = _policy(image_profile="malicious_custom_image")
    assert not result.permitted
    assert result.error_code == "IMAGE_PROFILE_NOT_ALLOWED"


def test_hostile_rejects_unsafe_absolute_argv_executable() -> None:
    """§24: absolute executable outside safe PATH prefixes."""
    policy = SandboxPolicy()
    spec, err = policy.build_image_and_command_spec(
        image_profile="python_dev_3_12",
        execution_kind="argv",
        command=None,
        argv=["/opt/evil/bin"],
    )
    assert spec is None
    assert err is not None
    assert not err.permitted
    assert err.error_code == "INVALID_COMMAND"


@pytest.mark.parametrize(
    "stream",
    [
        "combined",
        "../stdout",
        "stdout/../../../etc/passwd",
        "",
        "STDOUT",
    ],
)
def test_hostile_output_reader_rejects_invalid_stream(tmp_path: Path, stream: str) -> None:
    """§24: output reader rejects invalid stream names (path traversal instead of seq)."""
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    reader = OutputReader(session_dir)
    data, err = reader.read(1, stream)
    assert data is None
    assert err == "INVALID_STREAM"


def test_hostile_output_reader_symlink_escape_rejected(tmp_path: Path) -> None:
    """§24: reading output via symlink escape from session dir is rejected."""
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("leaked", encoding="utf-8")
    (session_dir / "000001.stdout.log").symlink_to(outside)
    reader = OutputReader(session_dir)
    data, err = reader.read(1, "stdout")
    assert data is None
    assert err == "INVALID_CWD"


def test_hostile_output_reader_valid_seq_reads_contained_file(tmp_path: Path) -> None:
    """§24: legitimate seq-based read stays inside session output files."""
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    log = session_dir / "000002.stdout.log"
    log.write_text("safe\n", encoding="utf-8")
    reader = OutputReader(session_dir)
    data, err = reader.read(2, "stdout")
    assert err is None
    assert data == b"safe\n"
