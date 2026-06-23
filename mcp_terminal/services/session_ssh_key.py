"""
Ephemeral SSH key pair lifecycle per terminal session.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Set

from mcp_terminal.services.host_execution_config import get_host_execution_config

_logger = logging.getLogger(__name__)

SESSION_KEY_DIRNAME = ".ssh"
SESSION_KEY_FILENAME = "session_ed25519"
SESSION_KEY_PUB_SUFFIX = ".pub"
SESSION_KEY_MARKER_PREFIX = "mcp-term-session="

_SESSION_ID_IN_MARKER = re.compile(r"mcp-term-session=([0-9a-fA-F-]{36})")


def session_key_paths(session_dir: Path) -> tuple[Path, Path]:
    """Return (private_key_path, public_key_path) under the session directory."""
    key_dir = session_dir / SESSION_KEY_DIRNAME
    private = key_dir / SESSION_KEY_FILENAME
    public = key_dir / f"{SESSION_KEY_FILENAME}{SESSION_KEY_PUB_SUFFIX}"
    return private, public


def session_key_marker(session_id: str) -> str:
    ttl = datetime.now(timezone.utc).isoformat()
    return f"{SESSION_KEY_MARKER_PREFIX}{session_id} ttl={ttl}"


def generate_session_keypair(session_dir: Path, session_id: str) -> tuple[Path, Path]:
    """Generate ed25519 key pair; return (private, public) paths."""
    key_dir = session_dir / SESSION_KEY_DIRNAME
    key_dir.mkdir(mode=0o700, exist_ok=True)
    private, public = session_key_paths(session_dir)
    comment = session_key_marker(session_id)
    subprocess.run(  # noqa: S603
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(private),
            "-N",
            "",
            "-C",
            comment,
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    private.chmod(0o600)
    public.chmod(0o644)
    return private, public


def read_public_key_line(session_dir: Path) -> Optional[str]:
    _, public = session_key_paths(session_dir)
    if not public.is_file():
        return None
    line = public.read_text(encoding="utf-8").strip()
    return line or None


def _run_key_manager(
    action: str,
    *,
    target_user: str,
    session_id: str,
    public_key_line: Optional[str] = None,
) -> bool:
    he = get_host_execution_config()
    if he.ssh is None:
        return False
    script = he.ssh.key_manager_script
    if not Path(script).is_file():
        _logger.warning("key manager script missing: %s", script)
        return False
    cmd = [script, action, target_user, session_id]
    if action == "add":
        if not public_key_line:
            return False
        cmd.append(public_key_line)
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            check=False,
            capture_output=True,
            timeout=30,
            text=True,
        )
        if proc.returncode != 0:
            _logger.warning(
                "key manager %s failed for session=%s user=%s: %s",
                action,
                session_id,
                target_user,
                proc.stderr.strip(),
            )
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        _logger.warning("key manager %s error: %s", action, exc)
        return False


def register_public_key(session_id: str, public_key_line: str, target_users: Iterable[str]) -> None:
    for user in target_users:
        _run_key_manager("add", target_user=user, session_id=session_id, public_key_line=public_key_line)


def revoke_session_keys(session_id: str, target_users: Iterable[str]) -> None:
    for user in target_users:
        _run_key_manager("remove", target_user=user, session_id=session_id)


def remove_session_key_files(session_dir: Path) -> None:
    private, public = session_key_paths(session_dir)
    for path in (private, public):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    key_dir = session_dir / SESSION_KEY_DIRNAME
    try:
        if key_dir.is_dir() and not any(key_dir.iterdir()):
            key_dir.rmdir()
    except OSError:
        pass


def provision_session_ssh_keys(session_dir: Path, session_id: str) -> None:
    """Generate keys and register public key on host target users when host execution enabled."""
    he = get_host_execution_config()
    if not he.enabled or not he.ssh_ready():
        return
    private, _public = session_key_paths(session_dir)
    if private.is_file():
        return
    generate_session_keypair(session_dir, session_id)
    pub_line = read_public_key_line(session_dir)
    if pub_line:
        register_public_key(session_id, pub_line, he.ssh.target_users)


def teardown_session_ssh_keys(session_dir: Path, session_id: str) -> None:
    """Revoke host keys and delete local key material."""
    he = get_host_execution_config()
    if he.ssh is not None and he.ssh.target_users:
        revoke_session_keys(session_id, he.ssh.target_users)
    remove_session_key_files(session_dir)


def reap_orphaned_keys(live_session_ids: Set[str]) -> None:
    """Remove authorized_keys entries whose session_id is not in live_session_ids."""
    he = get_host_execution_config()
    if not he.enabled or he.ssh is None or not he.ssh.target_users:
        return
    script = he.ssh.key_manager_script
    if not Path(script).is_file():
        return
    live_csv = ",".join(sorted(live_session_ids))
    for user in he.ssh.target_users:
        try:
            subprocess.run(  # noqa: S603
                [script, "reap", user, live_csv],
                check=False,
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _logger.warning("key reaper failed for user=%s: %s", user, exc)


def extract_session_id_from_marker(comment: str) -> Optional[str]:
    match = _SESSION_ID_IN_MARKER.search(comment)
    if not match:
        return None
    return match.group(1)
