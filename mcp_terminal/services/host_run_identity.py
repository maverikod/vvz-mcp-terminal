"""
Resolve effective host execution identity (project owner vs sudo override).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional

from mcp_terminal.services.host_execution_config import HostExecutionConfig


@dataclass(frozen=True)
class HostRunIdentity:
    """Effective user context for one host-side execution."""

    run_as_mode: str
    """``project_owner`` or ``sudo_override``."""
    sudo_user: str
    """First argument to ``sudo -u`` (account name preferred; numeric uid fallback)."""
    sudo_group: Optional[str]
    """Optional argument to ``sudo -g``."""
    effective_uid: Optional[int]
    """Numeric uid when known (project owner path)."""
    effective_gid: Optional[int]
    """Numeric gid when known (project owner path)."""
    primary_basename: str
    """Leading executable basename for this invocation."""


def project_owner_ids(project_dir: Path) -> tuple[int, int]:
    """Return ``(uid, gid)`` for the host project directory owner."""
    st = os.stat(project_dir.resolve(), follow_symlinks=True)
    return st.st_uid, st.st_gid


def project_owner_login(project_dir: Path) -> str:
    """Return the project owner account name for ``sudo -u`` inside the service container.

    Requires host ``/etc/passwd`` (bind-mounted into the service container). Falls
    back to numeric uid string when the name is not resolvable.
    """
    uid, _ = project_owner_ids(project_dir)
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def project_owner_user_spec(project_dir: Path, *, fallback: str = "65534:65534") -> str:
    """Return ``uid:gid`` for ``docker run --user`` on a project ``/workspace`` bind mount."""
    try:
        uid, gid = project_owner_ids(project_dir)
    except OSError:
        return fallback
    return f"{uid}:{gid}"


def prepare_path_for_project_owner_access(project_dir: Path, path: Path) -> None:
    """Make *path* owned by the project directory owner (requires root on the host).

    Session state (``.terminals/``) must belong to the project owner so host
    executors can read/write ``shell_state.json`` under sudo as that owner.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    if os.geteuid() != 0:
        return
    try:
        uid, gid = project_owner_ids(project_dir)
        os.chown(path, uid, gid)
        os.chmod(path, 0o2770)
    except OSError:
        pass


def _chown_tree(path: Path, uid: int, gid: int) -> None:
    """Recursively ``chown`` *path* and all descendants."""
    try:
        for root, dirs, files in os.walk(path, topdown=False):
            root_path = Path(root)
            for name in (*files, *dirs):
                try:
                    os.chown(root_path / name, uid, gid)
                except OSError:
                    pass
        os.chown(path, uid, gid)
    except OSError:
        pass


def _add_other_write_tree(path: Path) -> None:
    """Recursively add other-write (and traverse bits on dirs) for non-root dev."""
    try:
        for root, dirs, files in os.walk(path):
            root_path = Path(root)
            for name in files:
                try:
                    entry = root_path / name
                    mode = stat.S_IMODE(entry.stat().st_mode)
                    os.chmod(entry, mode | stat.S_IWOTH)
                except OSError:
                    pass
            for name in dirs:
                try:
                    entry = root_path / name
                    mode = stat.S_IMODE(entry.stat().st_mode)
                    os.chmod(
                        entry,
                        mode | stat.S_IWOTH | stat.S_IROTH | stat.S_IXOTH,
                    )
                except OSError:
                    pass
        mode = stat.S_IMODE(path.stat().st_mode)
        os.chmod(path, mode | stat.S_IWOTH | stat.S_IROTH | stat.S_IXOTH)
    except OSError:
        pass


def _strip_other_write_tree(path: Path) -> None:
    """Remove other-write bits introduced by ``_add_other_write_tree``."""
    try:
        for root, dirs, files in os.walk(path, topdown=False):
            root_path = Path(root)
            for name in (*files, *dirs):
                try:
                    entry = root_path / name
                    mode = stat.S_IMODE(entry.stat().st_mode) & ~stat.S_IWOTH
                    os.chmod(entry, mode)
                except OSError:
                    pass
        mode = stat.S_IMODE(path.stat().st_mode) & ~stat.S_IWOTH
        os.chmod(path, mode)
    except OSError:
        pass


def prepare_workspace_tree_for_sandbox_write(project_dir: Path) -> None:
    """Legacy helper: temporarily open the project tree for root-in-container writes.

    Writer sessions now run as the project owner (see ``writer_session_user``) and
    do not call this function. Kept for tests and any remaining root-container paths.
    """
    root = project_dir.resolve()
    if os.geteuid() == 0:
        _chown_tree(root, 0, 0)
        return
    _add_other_write_tree(root)


def restore_workspace_tree_project_owner(project_dir: Path) -> None:
    """Return the project tree to the project owner after a writer sandbox run."""
    root = project_dir.resolve()
    if os.geteuid() == 0:
        try:
            uid, gid = project_owner_ids(root)
        except OSError:
            return
        _chown_tree(root, uid, gid)
        return
    _strip_other_write_tree(root)


def prepare_workspace_for_sandbox_write(project_dir: Path) -> None:
    """Allow hardened sandbox root to create files under ``/workspace`` (bind mount).

    Deprecated alias for :func:`prepare_workspace_tree_for_sandbox_write`.
    """
    prepare_workspace_tree_for_sandbox_write(project_dir)


def prepare_session_dir_for_sandbox(
    project_dir: Path,
    session_dir: Path,
    *,
    container_user: str,
) -> None:
    """Make *session_dir* writable by the sandbox container process.

    Writer sessions run as the project owner; read-only sessions still use root
    inside the boundary and need a root-owned session dir (or dev-mode other-write).
    """
    if container_user == "0:0":
        _prepare_session_dir_for_root_container(session_dir)
        return
    prepare_path_for_project_owner_access(project_dir, session_dir)


def _prepare_session_dir_for_root_container(session_dir: Path) -> None:
    """Session dir for read-only sandboxes running as container root."""
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    if os.geteuid() == 0:
        try:
            os.chown(session_dir, 0, 0)
            os.chmod(session_dir, 0o700)
            for entry in session_dir.iterdir():
                try:
                    os.chown(entry, 0, 0)
                except OSError:
                    pass
        except OSError:
            pass
        return
    try:
        mode = session_dir.stat().st_mode
        os.chmod(session_dir, stat.S_IMODE(mode) | stat.S_IWOTH)
    except OSError:
        pass


def restore_session_dir_project_owner(project_dir: Path, session_dir: Path) -> None:
    """Return session files to the project owner after a sandbox run (root service only)."""
    if os.geteuid() == 0:
        try:
            uid, gid = project_owner_ids(project_dir)
        except OSError:
            return
        try:
            for root, dirs, files in os.walk(session_dir, topdown=False):
                root_path = Path(root)
                for name in (*files, *dirs):
                    try:
                        os.chown(root_path / name, uid, gid)
                    except OSError:
                        pass
            os.chown(session_dir, uid, gid)
            os.chmod(session_dir, 0o2770)
        except OSError:
            pass
        return
    try:
        for entry in session_dir.iterdir():
            if entry.is_dir():
                os.chmod(entry, 0o777)
            else:
                os.chmod(entry, 0o666)
        os.chmod(session_dir, 0o777)
    except OSError:
        pass


def _basename_lower(name: str) -> str:
    return Path(name).name.lower()


def primary_executable_basename(
    *,
    execution_kind: str,
    command: Optional[str],
    argv: Optional[list[str]],
    segments: tuple[str, ...],
) -> str:
    """Return the leading executable basename for identity resolution."""
    if execution_kind == "argv" and argv:
        return _basename_lower(str(argv[0]))
    if segments:
        from mcp_terminal.services.host_shell_scanner import segment_executable_name

        exe = segment_executable_name(segments[0])
        if exe:
            return exe.lower()
    if command and command.strip():
        from mcp_terminal.services.host_shell_scanner import segment_executable_name

        exe = segment_executable_name(command.strip())
        if exe:
            return exe.lower()
    return "bash"


def resolve_host_identity(
    *,
    project_dir: Path,
    config: HostExecutionConfig,
    execution_kind: str,
    command: Optional[str],
    argv: Optional[list[str]],
    segments: tuple[str, ...] = (),
) -> HostRunIdentity:
    """Resolve sudo target user/group for a validated host execution request."""
    primary = primary_executable_basename(
        execution_kind=execution_kind,
        command=command,
        argv=argv,
        segments=segments,
    )

    override = config.sudo_overrides.get(primary)
    if override is not None and len(segments) <= 1:
        as_user = override["as_user"]
        group = override.get("group")
        return HostRunIdentity(
            run_as_mode="sudo_override",
            sudo_user=as_user,
            sudo_group=group,
            effective_uid=None,
            effective_gid=None,
            primary_basename=primary,
        )

    uid, gid = project_owner_ids(project_dir)
    return HostRunIdentity(
        run_as_mode="project_owner",
        sudo_user=project_owner_login(project_dir),
        sudo_group=None,
        effective_uid=uid,
        effective_gid=gid,
        primary_basename=primary,
    )


def resolve_command_path(basename: str, config: HostExecutionConfig) -> Optional[str]:
    """Return configured absolute path for an allowlisted basename, if any."""
    return config.command_paths.get(basename.lower())


def _sudo_group_for_container(group: Optional[str]) -> Optional[str]:
    """Return a group name for ``sudo -g`` only when resolvable in this namespace.

    Host numeric gids (e.g. project owner gid 134) are not valid inside the
    service container and must not be passed to sudo.
    """
    if not group or group.isdigit():
        return None
    try:
        grp.getgrnam(group)
    except KeyError:
        return None
    return group


def _sudo_user_for_container(login: str) -> str:
    """Return ``sudo -u`` target when *login* is resolvable in this namespace."""
    if login.isdigit():
        return login
    try:
        pwd.getpwnam(login)
    except KeyError:
        return login
    return login


def build_sudo_argv(
    identity: HostRunIdentity,
    *,
    inner_argv: list[str],
) -> list[str]:
    """Build ``sudo -n -u … [-g …] -- …`` argv for a host execution."""
    sudo_argv = ["/usr/bin/sudo", "-n", "-u", _sudo_user_for_container(identity.sudo_user)]
    sudo_group = _sudo_group_for_container(identity.sudo_group)
    if sudo_group:
        sudo_argv.extend(["-g", sudo_group])
    sudo_argv.append("--")
    sudo_argv.extend(inner_argv)
    return sudo_argv


def segments_for_request(
    *,
    execution_kind: str,
    command: Optional[str],
    argv: Optional[list[str]],
    allowed_commands: FrozenSet[str],
) -> tuple[str, ...]:
    """Return shell segments used for identity resolution (empty for argv)."""
    if execution_kind == "argv":
        return ()
    if not command or not command.strip():
        return ()
    from mcp_terminal.services.host_execution_config import validate_host_shell_command

    result = validate_host_shell_command(command.strip(), allowed_commands)
    return result.segments
