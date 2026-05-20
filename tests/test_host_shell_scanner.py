"""Host shell scanner: decomposition and forbidden-pattern detection (C-018 H-3..H-5)."""

from __future__ import annotations

from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import validate_host_shell_command
from mcp_terminal.services.host_shell_scanner import (
    HOST_FORBIDDEN_EXECUTABLES,
    decompose_shell_command,
    extract_heredoc_bodies,
    extract_redirection_targets,
    find_forbidden_in_shell_command,
    find_forbidden_substring,
)


def test_h3_hard_forbidden_beats_allowlist_docker() -> None:
    """H-3: docker in allowed_commands is still HOST_FORBIDDEN_COMMAND."""
    allowed = frozenset({"docker", "pytest"})
    v = validate_host_shell_command("docker ps", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    assert "docker" in (v.detail or "")


def test_h3_hard_forbidden_beats_allowlist_argv_style() -> None:
    """H-3: hard-forbidden executable rejected even when sole allowlist entry."""
    allowed = frozenset({"kubectl"})
    v = validate_host_shell_command("kubectl get pods", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_h4_forbidden_pattern_in_redirect_target() -> None:
    """H-4: forbidden substring in redirect target is detected."""
    allowed = frozenset({"pytest"})
    v = validate_host_shell_command(
        "pytest -q > /var/run/docker.sock",
        allowed,
    )
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    assert "redirect" in (v.detail or "")


def test_h4_forbidden_pattern_in_heredoc_body() -> None:
    """H-4: forbidden substring inside heredoc body is detected."""
    allowed = frozenset({"pytest"})
    command = "pytest -q <<EOF\nline with --pid=host inside\nEOF"
    hit = find_forbidden_in_shell_command(command)
    assert hit is not None
    forbidden, ctx = hit
    assert forbidden == "--pid=host"
    assert ctx == "heredoc"

    v = validate_host_shell_command(command, allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    assert "heredoc" in (v.detail or "")


def test_h5_kubectl_in_allowlist_still_forbidden() -> None:
    """H-5: kubectl listed in allowed_commands remains HOST_FORBIDDEN_COMMAND."""
    assert "kubectl" in HOST_FORBIDDEN_EXECUTABLES
    allowed = frozenset({"kubectl", "pytest"})
    v = validate_host_shell_command("kubectl get pods", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_h5_helm_in_allowlist_still_forbidden() -> None:
    """H-5: helm listed in allowed_commands remains HOST_FORBIDDEN_COMMAND."""
    assert "helm" in HOST_FORBIDDEN_EXECUTABLES
    allowed = frozenset({"helm", "git"})
    v = validate_host_shell_command("helm list", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_decompose_shell_command_basic() -> None:
    assert decompose_shell_command("a && b") == ["a", "b"]


def test_find_forbidden_substring_docker_sock() -> None:
    assert find_forbidden_substring("--pid=host") == "--pid=host"


def test_extract_redirection_targets_finds_path() -> None:
    targets = extract_redirection_targets("pytest -q > /tmp/out.txt")
    assert "/tmp/out.txt" in targets


def test_extract_heredoc_bodies_finds_content() -> None:
    bodies = extract_heredoc_bodies("cat <<EOF\nhello\nEOF")
    assert bodies == ["hello"]
