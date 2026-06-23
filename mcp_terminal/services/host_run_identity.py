"""
Project directory ownership helpers for sandbox and session state.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import pwd
import stat
from pathlib import Path


def project_owner_ids(project_dir: Path) -> tuple[int, int]:
    """Return ``(uid, gid)`` for the host project directory owner."""
    st = os.stat(project_dir.resolve(), follow_symlinks=True)
    return st.st_uid, st.st_gid


def project_owner_login(project_dir: Path) -> str:
    """Return the project owner account name; falls back to numeric uid string."""
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
    """Make *path* owned by the project directory owner (requires root on the host)."""
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
    """Legacy helper: temporarily open the project tree for root-in-container writes."""
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
    """Deprecated alias for :func:`prepare_workspace_tree_for_sandbox_write`."""
    prepare_workspace_tree_for_sandbox_write(project_dir)


def prepare_session_dir_for_sandbox(
    project_dir: Path,
    session_dir: Path,
    *,
    container_user: str,
) -> None:
    """Make *session_dir* writable by the sandbox container process."""
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
