# MCP Terminal — Agent And Operator Guide

## Purpose

MCP Terminal provides project-scoped terminal access through MCP Proxy. Normal
work runs inside Docker sandbox containers with a project mounted at
`/workspace`. A separate, explicitly enabled `terminal_host_exec` path can run
allowlisted commands on the real host via SSH.

Use this guide as the full reference for the MCP server. For exact schemas, call
`help(command="<command_name>")`.

## Installed Package

The Debian package is `mcp-terminal-docker`.

Host-side package commands:

| Command | Role |
|---------|------|
| `mcp-terminal-docker status` | Show service status |
| `mcp-terminal-docker recreate` | Recreate the service container after config changes |
| `mcp-terminal-docker info` | Same summary as `mcp-terminal-info` |
| `mcp-terminal-info` | Host integration summary |
| `mcp-terminal-preflight` | Validate config, TLS, Docker, and adapter imports |

Host-side documentation:

| Document | Role |
|----------|------|
| `man mcp-terminal-docker` | Service wrapper commands |
| `man mcp-terminal-info` | Host integration summary command |
| `man mcp-terminal-preflight` | Preflight command |
| `man mcp-terminal-config` | Config file reference |
| `info mcp-terminal-docker` | GNU info manual |
| `/usr/share/doc/mcp-terminal-docker/MCP_TERMINAL_INFO.md` | This MCP guide |

## Architecture

The service container exposes an HTTPS MCP adapter and registers itself in MCP
Proxy. It reads `/etc/mcp-terminal/term_server.json`, discovers projects from
configured watch directories, and manages `.terminals/<session_id>/` state under
each project.

Sandbox execution and host execution are intentionally separate:

| Target | Command | Boundary |
|--------|---------|----------|
| Sandbox | `terminal_run` | Docker container, read-only root, dropped capabilities |
| Sandbox PTY | `terminal_attach` / `terminal_send` / `terminal_read_shell` | Existing kept sandbox container |
| Real host | `terminal_host_exec` | SSH to allowlisted host user and command set |

## Registered Commands

| Command | Role |
|---------|------|
| `info` | This guide |
| `terminal_sessions` | List terminal sessions for a project |
| `terminal_session_create` | Create or reopen a project/session terminal state |
| `terminal_get_session_bootstrap` | Read runtime image bootstrap state |
| `terminal_run` | Run an async command in the sandbox |
| `terminal_attach` | Attach a PTY to a kept sandbox container |
| `terminal_send` | Send input to an interactive PTY |
| `terminal_read_shell` | Read incremental PTY output |
| `terminal_resize` | Resize an interactive PTY |
| `terminal_detach` | Stop and detach the PTY |
| `terminal_host_exec` | Run an allowlisted command on the real host via SSH |
| `terminal_list` | List command history for a session |
| `terminal_list_watch` | List discovered watch directories and projects |
| `terminal_registry_refresh` | Rebuild the in-memory project registry |
| `terminal_get` | Read one command history record |
| `terminal_read` | Read stdout or stderr bytes for a command |
| `terminal_search_commands` | Search command history |
| `terminal_search_output` | Search command output |
| `terminal_tail` | Tail stdout or stderr lines |
| `terminal_stat` | Return output file sizes |
| `terminal_delete` | Delete a terminal session and container |
| `terminal_get_status` | Poll async command status |
| `terminal_kill` | Kill a running sandbox command |
| `terminal_purge_sessions` | Admin purge of session directories |

## Standard Workflow

Create a real Code Analysis Server session first, then use the same UUID for
MCP Terminal:

```text
code-analysis-server.session_create -> session_id
mcp-terminal.terminal_session_create(project_id, session_id)
mcp-terminal.terminal_run(...)
mcp-terminal.terminal_get_status(...)
mcp-terminal.terminal_read(...)
mcp-terminal.terminal_delete(...)
code-analysis-server.session_delete(...)
```

`terminal_session_create` validates the Code Analysis Server session and
registers a subordinate link. Random UUIDs fail with `CLIENT_SESSION_NOT_FOUND`.

## Sandbox Execution

`terminal_run` is asynchronous. It returns `job_id`, `seq`, and output file
names immediately. Poll `terminal_get_status` until terminal status is final,
then read output with `terminal_read` or `terminal_tail`.

Sandbox write modes are enforced in code by `SandboxPolicy` plus the session
writer lock:

| Mode | `/workspace` | Writes go to | Who can use it |
|------|--------------|--------------|----------------|
| `read_only` | read-only | `/tmp`, `/scratch`, `/session-state` | any session |
| `workspace_write` | read-write | project tree plus scratch paths | only the single writer session for a project |
| `scratch_write` | read-only | `/scratch` and temp paths | any session |

If `mode` is omitted, `terminal_run` uses `workspace_write` only for a session
whose `terminal_session_create` result has `workspace_write: true`; all other
sessions run `read_only`. A non-writer session that requests `workspace_write`
fails with `WORKSPACE_WRITE_NOT_ALLOWED`.

Minimal example:

```json
{
  "project_id": "<project-uuid>",
  "session_id": "<ca-session-uuid>",
  "execution_kind": "argv",
  "argv": ["python", "--version"],
  "image_profile": "python_dev_3_12",
  "mode": "read_only",
  "network": "none",
  "keep_container": false,
  "use_venv": false
}
```

The sandbox image profiles are:

| Profile | Use |
|---------|-----|
| `python_dev_3_12` | Python diagnostics, tests, linting, typing |
| `node_dev_20` | Node projects and basic CLI work |
| `base_tools` | Generic shell utilities |

The Python profile includes common diagnostics such as `ruff`, `pytest`,
`pytest-cov`, `coverage`, `mypy`, `flake8`, `black`, `isort`, `pylint`,
`bandit`, `vulture`, and `radon`.

## Interactive PTY Workflow

Interactive shells attach only to an already running kept sandbox container.
Start the container with `terminal_run(..., keep_container=true)`, then attach:

```text
terminal_run(..., keep_container=true)
terminal_attach(project_id, session_id, command="bash")
terminal_send(shell_id, "python\n")
terminal_read_shell(shell_id, offset=0)
terminal_detach(shell_id)
terminal_delete(project_id, session_id)
```

The PTY can drive shells, Python REPLs, debuggers, and tools that need prompts.
It does not create a new host execution path and does not accept arbitrary
container names.

## Host Execution

`terminal_host_exec` is separate from sandbox execution. It runs an allowlisted
command on the real host through SSH. It is disabled unless
`terminal.host_execution.enabled` and SSH settings are configured.

Sessionless example:

```json
{
  "execution_kind": "argv",
  "argv": ["hostname"],
  "cwd": "/root",
  "timeout_seconds": 30
}
```

The response includes `host_run_id`. Use that id for status and output:

```text
terminal_get_status(host_run_id, seq)
terminal_read(host_run_id, seq, stream="stdout", max_bytes=4096)
```

Do not pass your own `host_run_id` to `terminal_host_exec`; it is generated by
the server.

## Output And Status

Every command has a session-local `seq`. Output is stored as:

```text
.terminals/<session_id>/NNNNNN.stdout.log
.terminals/<session_id>/NNNNNN.stderr.log
.terminals/<session_id>/NNNNNN.meta.json
```

Use:

| Command | Use |
|---------|-----|
| `terminal_get_status` | Queue state, terminal state, exit code |
| `terminal_read` | Byte-offset reads; parameter is `max_bytes` |
| `terminal_tail` | Last N lines |
| `terminal_stat` | Output sizes and file names |

Queue completion does not imply command success. Always check
`terminal_status`, `exit_code`, and `timed_out`.

## Security Model

Sandbox containers use a fixed image allowlist, project-root bind mounts, a
read-only root filesystem, dropped capabilities, `no-new-privileges`, resource
limits, and controlled network modes.

Host execution is intentionally narrower and should remain disabled by default.
It uses command allowlists, forbidden-pattern checks, key guards, target-user
validation, and pinned SSH host keys.

## Operational Checks

After deployment or config changes:

```text
dpkg-query -W mcp-terminal-docker
systemctl is-active mcp-terminal-docker.service
docker ps
curl -sk https://127.0.0.1:3011/health
mcp-terminal-preflight
```

Proxy-backed validation should also call the downstream server through MCP
Proxy, not only `/health`:

```text
list_servers -> mcp-terminal
call_server(server_id="mcp-terminal", command="help")
terminal_run -> terminal_get_status -> terminal_read
terminal_host_exec -> terminal_get_status -> terminal_read
```

## Common Errors

| Error | Meaning | Fix |
|-------|---------|-----|
| `CLIENT_SESSION_NOT_FOUND` | session_id is not a Code Analysis Server session | Call `session_create` first |
| `INVALID_SESSION` | Terminal session does not exist | Call `terminal_session_create` |
| `WORKSPACE_WRITE_NOT_ALLOWED` | Another session holds the writer slot | Reuse/delete the writer session |
| `INVALID_CWD` | cwd is absolute or escapes the project | Use project-relative cwd |
| `IMAGE_PROFILE_NOT_ALLOWED` | Unknown sandbox image profile | Use an allowlisted profile |
| `HOST_EXECUTION_DISABLED` | Host execution config is incomplete or disabled | Use sandbox or enable host exec deliberately |
| `HOST_COMMAND_NOT_ALLOWED` | Command basename is not allowlisted | Use an allowed command |

## Cleanup

Close interactive PTYs with `terminal_detach`. Remove terminal sessions with
`terminal_delete`. If a Code Analysis Server session was created only for a
terminal test, delete it with `session_delete`.
