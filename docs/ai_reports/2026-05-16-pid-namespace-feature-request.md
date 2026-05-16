# Feature Request: pid_namespace config option for terminal containers

**Date:** 2026-05-16
**Reporter:** Claude
**Type:** Feature Request
**Project:** mcp_terminal (`0b39f01f-55b4-41de-bb1e-732cc248ab3b`)

## Problem

When a project's server process runs on the host (e.g. `casmgr` at
`pid=145773`), the mcp-terminal container cannot see or signal that
process. Each `terminal_run` executes inside an isolated Docker container
with its own PID namespace. The host process is invisible:

```bash
# Inside container
$ casmgr status
bash: casmgr: command not found   # shebang points to host path

$ python -m code_analysis.cli.server_manager_cli --config config.json status
stopped (stale pidfile)            # host PID not visible in container
```

This makes it impossible to restart/stop a host-side server from the
terminal, which was an explicit design goal.

## Context: mixed deployment topology

Projects are deployed in two modes:

- **Host mode** (dev/debug): server runs directly on the host. Terminal
  container cannot manage it without `--pid=host`.
- **Container mode** (production): server runs inside its own container.
  PID isolation is correct and desired.

A single config flag is enough to cover both cases without changing
the security model for production deployments.

## Proposed solution

Add a `pid_namespace` field to `ContainerSpec` and expose it through
the session config. Two values:

- `"container"` (default) — current behaviour, full PID isolation.
- `"host"` — passes `--pid=host` to `docker run`, container sees all
  host processes.

### Security note

`--pid=host` grants the container read access to `/proc/<pid>/` of all
host processes (environ, open files) and the ability to send signals
to host processes. This is acceptable on a single-user dev machine and
explicit opt-in only. Production deployments keep the default
`"container"` and are unaffected.

## Implementation plan

### 1. `mcp_terminal/services/sandbox_policy.py`

Add `pid_namespace` field to `PolicyConfig`:

```python
@dataclass
class PolicyConfig:
    ...existing fields...
    pid_namespace: str = "container"  # "host" | "container"
```

### 2. `mcp_terminal/services/container_runner.py`

Add field to `ContainerSpec`:

```python
@dataclass
class ContainerSpec:
    ...existing fields...
    pid_namespace: str = "container"  # "host" | "container"
```

In `ContainerRunner.build_cmd` add after security flags:

```python
if spec.pid_namespace == "host":
    cmd.append("--pid=host")
```

### 3. `mcp_terminal/services/session_container.py`

In `_build_start_cmd` (keep_container / long-idle path) apply the same
condition:

```python
if spec.pid_namespace == "host":
    cmd.append("--pid=host")
```

### 4. `mcp_terminal/term_server.defaults.json`

Add to sandbox/container defaults section:

```json
"pid_namespace": "container"
```

### 5. `mcp_terminal/commands/terminal_session_create_command.py`

Accept `pid_namespace` as an optional session-create parameter
(alongside `image_profile`). Validate it is one of
`{"host", "container"}`. Pass through to `ContainerSpec`.

### 6. Validation

In `SandboxPolicy` or config validator: if `pid_namespace == "host"`,
emit a warning log entry:

```
WARNING: pid_namespace=host grants container access to host PID
namespace. Use only in development/debug environments.
```

## Expected lifecycle after fix

```
# Dev session with pid_namespace=host
terminal_session_create(project_id=..., pid_namespace="host")
terminal_run("casmgr --config config.json status")
# → running pid=145773

terminal_run("casmgr --config config.json restart")
# → server restarted on host
```

## Files to modify

| File | Change |
|------|--------|
| `mcp_terminal/services/sandbox_policy.py` | Add `pid_namespace` to `PolicyConfig` |
| `mcp_terminal/services/container_runner.py` | Add field to `ContainerSpec`; apply in `build_cmd` |
| `mcp_terminal/services/session_container.py` | Apply in `_build_start_cmd` |
| `mcp_terminal/term_server.defaults.json` | Add default value |
| `mcp_terminal/commands/terminal_session_create_command.py` | Accept as parameter |
| `mcp_terminal/config/config_validator.py` | Validate allowed values |
