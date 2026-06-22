"""Tests for host run identity resolution."""

from __future__ import annotations

import os
import pwd
import stat
from pathlib import Path

import pytest

from mcp_terminal.services.host_execution_config import HostExecutionConfig
from mcp_terminal.services.host_run_identity import (
    HostRunIdentity,
    build_sudo_argv,
    prepare_path_for_project_owner_access,
    prepare_session_dir_for_sandbox,
    prepare_workspace_tree_for_sandbox_write,
    project_owner_ids,
    project_owner_login,
    project_owner_user_spec,
    restore_workspace_tree_project_owner,
    resolve_host_identity,
)


def test_project_owner_ids_match_stat(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    uid, gid = project_owner_ids(project)
    st = os.stat(project)
    assert uid == st.st_uid
    assert gid == st.st_gid


def test_resolve_host_identity_project_owner(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"git"}),
        sudo_overrides={},
    )
    identity = resolve_host_identity(
        project_dir=project,
        config=cfg,
        execution_kind="shell",
        command="git status",
        argv=None,
        segments=("git status",),
    )
    uid, gid = project_owner_ids(project)
    assert identity.run_as_mode == "project_owner"
    assert identity.sudo_user == project_owner_login(project)
    assert identity.sudo_group is None
    assert identity.effective_uid == uid
    assert identity.effective_gid == gid


def test_project_owner_login_uses_passwd_name(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    assert project_owner_login(project) == pwd.getpwuid(os.getuid()).pw_name


def test_resolve_host_identity_sudo_override(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"casmgr"}),
        sudo_overrides={"casmgr": {"as_user": "casuser", "group": "casgrp"}},
    )
    identity = resolve_host_identity(
        project_dir=project,
        config=cfg,
        execution_kind="shell",
        command="casmgr status",
        argv=None,
        segments=("casmgr status",),
    )
    assert identity.run_as_mode == "sudo_override"
    assert identity.sudo_user == "casuser"
    assert identity.sudo_group == "casgrp"


def test_resolve_host_identity_root_mode(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"docker"}),
        run_as_default="root",
        sudo_overrides={},
    )
    identity = resolve_host_identity(
        project_dir=project,
        config=cfg,
        execution_kind="shell",
        command="docker ps",
        argv=None,
        segments=("docker ps",),
    )
    assert identity.run_as_mode == "root"
    assert identity.sudo_user == "root"
    assert identity.effective_uid == 0
    assert identity.effective_gid == 0


def test_resolve_host_identity_sudo_override_beats_root_default(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"casmgr"}),
        run_as_default="root",
        sudo_overrides={"casmgr": {"as_user": "casuser", "group": "casgrp"}},
    )
    identity = resolve_host_identity(
        project_dir=project,
        config=cfg,
        execution_kind="shell",
        command="casmgr status",
        argv=None,
        segments=("casmgr status",),
    )
    assert identity.run_as_mode == "sudo_override"
    assert identity.sudo_user == "casuser"


def test_project_owner_user_spec_matches_stat(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    uid, gid = project_owner_ids(project)
    assert project_owner_user_spec(project) == f"{uid}:{gid}"


def test_prepare_path_for_project_owner_access_group_writable(tmp_path: Path) -> None:
    if os.geteuid() != 0:
        pytest.skip("prepare_path_for_project_owner_access chown requires root")
    project = tmp_path / "proj"
    project.mkdir()
    os.chown(project, os.getuid(), os.getgid())
    target = project / ".terminals" / "sess"
    prepare_path_for_project_owner_access(project, target)
    assert target.is_dir()
    assert target.stat().st_uid == project.stat().st_uid
    assert stat.S_IMODE(target.stat().st_mode) == 0o2770


def test_build_sudo_argv_project_owner_uses_login_name() -> None:
    identity = HostRunIdentity(
        run_as_mode="project_owner",
        sudo_user="casuser",
        sudo_group=None,
        effective_uid=130,
        effective_gid=134,
        primary_basename="git",
    )
    argv = build_sudo_argv(identity, inner_argv=["/bin/bash", "/tmp/run.sh"])
    assert argv == ["/usr/bin/sudo", "-n", "-u", "casuser", "--", "/bin/bash", "/tmp/run.sh"]


def test_build_sudo_argv_project_owner_omits_numeric_group() -> None:
    identity = HostRunIdentity(
        run_as_mode="project_owner",
        sudo_user="1000",
        sudo_group=None,
        effective_uid=1000,
        effective_gid=1000,
        primary_basename="git",
    )
    argv = build_sudo_argv(identity, inner_argv=["/bin/bash", "/tmp/run.sh"])
    assert argv == ["/usr/bin/sudo", "-n", "-u", "1000", "--", "/bin/bash", "/tmp/run.sh"]


def test_build_sudo_argv_omits_unknown_numeric_group() -> None:
    identity = HostRunIdentity(
        run_as_mode="project_owner",
        sudo_user="130",
        sudo_group="134",
        effective_uid=130,
        effective_gid=134,
        primary_basename="grep",
    )
    argv = build_sudo_argv(identity, inner_argv=["/usr/bin/grep", "x", "file"])
    assert "-g" not in argv
    assert argv[:5] == ["/usr/bin/sudo", "-n", "-u", "130", "--"]


def test_build_sudo_argv_includes_named_group_when_present() -> None:
    identity = HostRunIdentity(
        run_as_mode="sudo_override",
        sudo_user="root",
        sudo_group="root",
        effective_uid=None,
        effective_gid=None,
        primary_basename="true",
    )
    argv = build_sudo_argv(identity, inner_argv=["/usr/bin/true"])
    assert argv[:7] == ["/usr/bin/sudo", "-n", "-u", "root", "-g", "root", "--"]


def test_prepare_session_dir_for_sandbox_uses_project_owner(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    session = project / ".terminals" / "sess"
    uid, gid = project_owner_ids(project)
    prepare_session_dir_for_sandbox(
        project, session, container_user=f"{uid}:{gid}"
    )
    assert session.is_dir()
    assert session.stat().st_uid == project.stat().st_uid
    assert session.stat().st_gid == project.stat().st_gid


def test_prepare_workspace_tree_non_root_opens_nested_other_write(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("non-root dev-mode chmod test")
    project = tmp_path / "proj"
    nested = project / "pkg"
    nested.mkdir(parents=True)
    target = nested / "module.py"
    target.write_text("x", encoding="utf-8")
    os.chmod(project, 0o2770)
    os.chmod(nested, 0o2770)
    os.chmod(target, 0o660)

    prepare_workspace_tree_for_sandbox_write(project)
    assert target.stat().st_mode & stat.S_IWOTH
    assert nested.stat().st_mode & stat.S_IWOTH

    restore_workspace_tree_project_owner(project)
    assert not (target.stat().st_mode & stat.S_IWOTH)
    assert not (nested.stat().st_mode & stat.S_IWOTH)


def test_prepare_workspace_tree_root_chowns_nested_file(tmp_path: Path) -> None:
    if os.geteuid() != 0:
        pytest.skip("root chown tree test")
    project = tmp_path / "proj"
    nested = project / "pkg"
    nested.mkdir(parents=True)
    target = nested / "module.py"
    target.write_text("x", encoding="utf-8")
    uid, gid = os.getuid(), os.getgid()
    os.chown(project, uid, gid)
    os.chown(nested, uid, gid)
    os.chown(target, uid, gid)

    prepare_workspace_tree_for_sandbox_write(project)
    assert target.stat().st_uid == 0
    assert target.stat().st_gid == 0

    restore_workspace_tree_project_owner(project)
    assert target.stat().st_uid == uid
    assert target.stat().st_gid == gid
    assert not (target.stat().st_mode & stat.S_IWOTH)
