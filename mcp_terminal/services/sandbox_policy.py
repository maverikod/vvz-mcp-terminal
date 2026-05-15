"""Trust classification schema and sandbox policy validation for mcp_terminal.

Every request from the model is treated as untrusted regardless of session
history or prior successful requests (zero-trust invariant).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, FrozenSet, Optional


class TrustCategory(Enum):
    """Categories of entities in the trust classification schema."""

    TRUSTED_COMPONENT = auto()
    UNTRUSTED_INPUT = auto()
    SENSITIVE_HOST_RESOURCE = auto()


@dataclass(frozen=True)
class TrustBoundary:
    """Closed trust categories: inputs not in trusted_components are untrusted."""

    trusted_components: FrozenSet[str] = field(default_factory=frozenset)
    """Names of trusted system components."""
    untrusted_input_categories: FrozenSet[str] = field(default_factory=frozenset)
    """Names of input categories that must never be trusted."""
    sensitive_host_resources: FrozenSet[str] = field(default_factory=frozenset)
    """Host resource names that must never be exposed to the sandbox."""


# fmt: off
TERMINAL_TRUST_BOUNDARY: TrustBoundary = TrustBoundary(
    trusted_components=frozenset(
        {
            "service_code",
            "project_registry",
            "server_side_policy_config",
            "container_image_allowlist",
        }
    ),
    untrusted_input_categories=frozenset(
        {
            "command_arguments", "cwd_values", "environment_variable_requests",
            "network_mode_requests", "write_mode_requests", "mounted_project_file_content",
        }
    ),
    sensitive_host_resources=frozenset(
        {
            "host_root_filesystem", "home_directories_outside_project", "ssh_credentials",
            "cloud_credentials", "docker_socket", "host_etc_proc_sys_dev",
            "parent_watch_directories", "unrelated_project_directories",
        }
    ),
)
# fmt: on


@dataclass(frozen=True)
class PolicyConfig:
    """Immutable policy from ConfigOverlay (C-013); consumed by SandboxPolicy."""

    allowed_modes: FrozenSet[str]
    """Permitted mount modes: read_only, workspace_write, scratch_write."""
    allowed_network_modes: FrozenSet[str]
    """Permitted network modes in MVP: none, package_registry."""
    allowed_image_profiles: FrozenSet[str]
    """Server-side image profile allowlist (e.g. python_dev_3_12)."""
    safe_path_prefixes: FrozenSet[str]
    """Executable path prefixes considered safe (used by command policy)."""


DEFAULT_POLICY_CONFIG: PolicyConfig = PolicyConfig(
    allowed_modes=frozenset({"read_only", "workspace_write", "scratch_write"}),
    allowed_network_modes=frozenset({"none", "package_registry"}),
    allowed_image_profiles=frozenset({"python_dev_3_12", "node_dev_20", "base_tools"}),
    safe_path_prefixes=frozenset({"/usr/bin", "/usr/local/bin", "/bin", "/usr/sbin"}),
)


@dataclass(frozen=True)
class MountSpec:
    """Mount config for ContainerRuntime (C-010); /workspace is the fixed mount point."""

    workspace_source: Path
    """Verified canonical host path of the project root to mount at /workspace."""
    workspace_readonly: bool
    """True for read_only and scratch_write modes; False for workspace_write."""
    scratch_enabled: bool
    """True for all modes (scratch tmpfs is always provided)."""
    workdir: str
    """Absolute container path for working directory, e.g. /workspace/tests."""
    mode: str
    """Validated mount mode string: read_only, workspace_write, or scratch_write."""


@dataclass(frozen=True)
class NetworkSpec:
    """Network config for a container (C-010); from SandboxPolicy.build_network_spec()."""

    mode: str
    """Validated network mode: 'none' or 'package_registry'."""
    allow_egress: bool
    """True when mode is 'package_registry'; False for 'none'."""
    allowed_hosts: FrozenSet[str]
    """Allowlisted host names for egress; empty when allow_egress is False."""


DEFAULT_NETWORK_SPEC: NetworkSpec = NetworkSpec(
    mode="none", allow_egress=False, allowed_hosts=frozenset()
)
PACKAGE_REGISTRY_NETWORK_SPEC: NetworkSpec = NetworkSpec(
    mode="package_registry",
    allow_egress=True,
    allowed_hosts=frozenset({"pypi.org", "files.pythonhosted.org"}),
)


@dataclass(frozen=True)
class ImageAndCommandSpec:
    """Resolved image + argv for ContainerRunner.build_cmd() (C-003/C-010)."""

    image_reference: str
    """Concrete server-side image reference resolved from image_profile."""
    execution_kind: str
    """Validated execution kind: 'shell' or 'argv'."""
    resolved_argv: list
    """Actual argv passed to container entrypoint."""
    environment: dict
    """Safe minimal environment variables; no host secrets."""
    resolved_executable: Optional[str]
    """First element of resolved_argv for audit logging; None for shell kind."""


IMAGE_PROFILE_MAP: Dict[str, str] = {
    "python_dev_3_12": "ghcr.io/mcp-terminal/python-dev:3.12",
    "node_dev_20": "ghcr.io/mcp-terminal/node-dev:20",
    "base_tools": "ghcr.io/mcp-terminal/base-tools:latest",
}


@dataclass(frozen=True)
class ValidationResult:
    """SandboxPolicy check outcome; on failure includes stable ErrorContract code (C-015)."""

    permitted: bool
    """True if the request passed all policy checks."""
    error_code: Optional[str] = None
    """Stable ErrorContract code (C-015) when permitted is False."""
    rejected_field: Optional[str] = None
    """Name of the request field that triggered the rejection."""
    detail: Optional[str] = None
    """Human-readable detail string; not stable across versions."""


class SandboxPolicy:
    """Zero-trust request validator (C-003): every request checked against PolicyConfig."""

    # Forbidden runtime option strings; presence in any request field triggers
    # immediate rejection regardless of context.
    _FORBIDDEN_OPTIONS: FrozenSet[str] = frozenset(
        {
            "--privileged",
            "--pid=host",
            "--pid host",
            "--network=host",
            "--network host",
            "--ipc=host",
            "--ipc host",
            "--uts=host",
            "--uts host",
            "--cap-add=SYS_ADMIN",
            "--cap-add SYS_ADMIN",
            "/var/run/docker.sock",
        }
    )

    @staticmethod
    def _fail(error_code: str, rejected_field: str, detail: str) -> ValidationResult:
        return ValidationResult(
            permitted=False, error_code=error_code, rejected_field=rejected_field, detail=detail
        )

    def __init__(self, config: PolicyConfig = DEFAULT_POLICY_CONFIG) -> None:
        """Initialise SandboxPolicy; ``config`` defaults to ``DEFAULT_POLICY_CONFIG``."""
        self._config = config

    def validate(
        self,
        *,
        project_id: Optional[str],
        execution_kind: Optional[str],
        cwd: Optional[str],
        mode: Optional[str],
        network: Optional[str],
        image_profile: Optional[str],
        command: Optional[str],
        argv: Optional[list],
    ) -> ValidationResult:
        """Validate a terminal_run request; first failing check wins (ErrorContract, C-015)."""
        if project_id is None or project_id.strip() == "":
            return self._fail("INVALID_COMMAND", "project_id", "project_id is required")
        if project_id.startswith("/") or ".." in project_id:
            return self._fail(
                "PROJECT_PATH_OUT_OF_SCOPE",
                "project_id",
                "project_id must not be a host path",
            )
        if execution_kind not in ("shell", "argv"):
            return self._fail(
                "INVALID_COMMAND",
                "execution_kind",
                f"execution_kind must be 'shell' or 'argv', got {execution_kind!r}",
            )
        if execution_kind == "shell":
            if not command or not command.strip():
                return self._fail(
                    "INVALID_COMMAND",
                    "command",
                    "command is required for shell execution_kind",
                )
            if "\x00" in command:
                return self._fail(
                    "INVALID_COMMAND", "command", "command must not contain NUL bytes"
                )
        if execution_kind == "argv":
            if not argv:
                return self._fail(
                    "INVALID_COMMAND",
                    "argv",
                    "argv must be a non-empty list for argv execution_kind",
                )
            for element in argv:
                if not isinstance(element, str) or "\x00" in element:
                    return self._fail(
                        "INVALID_COMMAND",
                        "argv",
                        "argv elements must be non-null strings without NUL bytes",
                    )
        if cwd is not None and (cwd.startswith("/") or ".." in cwd):
            return self._fail(
                "INVALID_CWD",
                "cwd",
                "cwd must be relative and must not contain ..",
            )
        if mode not in self._config.allowed_modes:
            return self._fail("MODE_NOT_ALLOWED", "mode", f"mode {mode!r} is not allowed")
        if network not in self._config.allowed_network_modes:
            return self._fail(
                "NETWORK_MODE_NOT_ALLOWED",
                "network",
                f"network {network!r} is not allowed in MVP",
            )
        if image_profile not in self._config.allowed_image_profiles:
            return self._fail(
                "IMAGE_PROFILE_NOT_ALLOWED",
                "image_profile",
                f"image_profile {image_profile!r} is not in the server allowlist",
            )
        if command:
            for forbidden in self._FORBIDDEN_OPTIONS:
                if forbidden in command:
                    return self._fail(
                        "INVALID_COMMAND",
                        "command",
                        f"command contains forbidden option: {forbidden}",
                    )
        return ValidationResult(permitted=True)

    def build_mount_spec(
        self,
        *,
        workspace_source: Path,
        mode: str,
        cwd: Optional[str],
    ) -> tuple[Optional[MountSpec], Optional[ValidationResult]]:
        """Return ``(MountSpec, None)`` or ``(None, ValidationResult)`` for bad ``cwd``."""
        safe_cwd = (cwd or ".").strip()
        if safe_cwd.startswith("/") or ".." in safe_cwd:
            return None, self._fail(
                "INVALID_CWD",
                "cwd",
                "cwd must be relative and must not contain ..",
            )
        workdir = f"/workspace/{safe_cwd}".rstrip("/") or "/workspace"
        readonly = mode in ("read_only", "scratch_write")
        return (
            MountSpec(
                workspace_source=workspace_source,
                workspace_readonly=readonly,
                scratch_enabled=True,
                workdir=workdir,
                mode=mode,
            ),
            None,
        )

    def build_network_spec(
        self,
        network: str,
    ) -> tuple[Optional[NetworkSpec], Optional[ValidationResult]]:
        """Map ``network`` to ``NetworkSpec``; ``open`` and unknown modes fail."""
        if network not in self._config.allowed_network_modes:
            return None, self._fail(
                "NETWORK_MODE_NOT_ALLOWED",
                "network",
                f"network {network!r} is not allowed in MVP",
            )
        if network == "none":
            return DEFAULT_NETWORK_SPEC, None
        if network == "package_registry":
            return PACKAGE_REGISTRY_NETWORK_SPEC, None
        return None, self._fail(
            "NETWORK_MODE_NOT_ALLOWED",
            "network",
            f"unhandled network mode: {network!r}",
        )

    def build_image_and_command_spec(
        self,
        *,
        image_profile: str,
        execution_kind: str,
        command: Optional[str],
        argv: Optional[list],
    ) -> tuple[Optional[ImageAndCommandSpec], Optional[ValidationResult]]:
        """Resolve image profile to image ref and command line; enforces safe argv paths."""
        image_ref = IMAGE_PROFILE_MAP.get(image_profile)
        if image_ref is None:
            return None, self._fail(
                "IMAGE_PROFILE_NOT_ALLOWED",
                "image_profile",
                f"image_profile {image_profile!r} is not in the server allowlist",
            )
        safe_env: dict = {
            "HOME": "/tmp/home",
            "TMPDIR": "/tmp",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        }
        resolved_exe: Optional[str]
        if execution_kind == "shell":
            resolved: list = ["bash", "-lc", command or ""]
            resolved_exe = None
        else:
            resolved = list(argv or [])
            resolved_exe = resolved[0] if resolved else None
            if resolved_exe and resolved_exe.startswith("/"):
                safe = any(resolved_exe.startswith(p) for p in self._config.safe_path_prefixes)
                if not safe:
                    return None, self._fail(
                        "INVALID_COMMAND",
                        "argv",
                        f"absolute executable {resolved_exe!r} outside safe PATH",
                    )
        return (
            ImageAndCommandSpec(
                image_reference=image_ref,
                execution_kind=execution_kind,
                resolved_argv=resolved,
                environment=safe_env,
                resolved_executable=resolved_exe,
            ),
            None,
        )
