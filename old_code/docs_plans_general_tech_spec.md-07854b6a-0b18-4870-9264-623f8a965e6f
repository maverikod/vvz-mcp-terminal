<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Technical Specification: `mcp_terminal` Sandbox Execution Server

## 1. Purpose

`mcp_terminal` is a standalone MCP/OpenAPI-compatible server that provides controlled terminal execution for language models inside isolated containers.

The server allows a model to reference a registered project by `project_id` and execute commands inside a sandbox container where that project's directory is mounted at a fixed workspace path.

The primary goal is to let models run project-local tools, tests, linters, package managers, and diagnostics without giving them direct access to the host filesystem or host shell.

## 2. Non-goals

The server must not become a general-purpose remote shell for the host machine.

The server must not accept arbitrary host paths from the model.

The server must not expose Docker socket access, host root filesystem access, or privileged container execution.

The server must not replace `code-analysis-server`. It is a separate high-risk execution service with a narrower responsibility: sandboxed terminal execution.

## 3. High-level Architecture

```text
LLM / MCP client
  -> MCP proxy
    -> mcp_terminal server
      -> project registry lookup by project_id
      -> policy validation
      -> sandbox container runtime
        -> /workspace mounted from the resolved project directory
        -> command executes inside /workspace
      -> captured stdout/stderr/exit_code returned to caller
```

`code-analysis-server` remains responsible for code analysis and project metadata operations. `mcp_terminal` may query a trusted project registry or a dedicated read-only project lookup interface, but must not depend on direct user-provided paths.

## 4. Trust Boundaries

### 4.1 Trusted components

- `mcp_terminal` service code.
- Project registry used to resolve `project_id` into a project root.
- Server-side policy configuration.
- Container image allowlist.

### 4.2 Untrusted inputs

- Command arguments from the model.
- Working directory values from the model.
- Environment variable requests from the model.
- Network mode requests from the model.
- Write-mode requests from the model.
- Any file content inside the mounted project.

### 4.3 Sensitive host resources

The sandbox must never expose:

- host `/`;
- host home directories except the specific resolved project root;
- `.ssh`, cloud credentials, tokens, private keys;
- `/var/run/docker.sock`;
- host `/etc`, `/proc`, `/sys`, `/dev` beyond the container runtime defaults;
- parent watch directories as a whole;
- unrelated project directories.

## 5. Core Security Principle

The model receives a controlled project sandbox, not a host terminal.

The model must only be able to affect the resolved project directory according to the selected access mode and must not be able to escape to the host or other projects.

## 6. Project Discovery and Resolution

The API must accept `project_id`, not a host path.

Example input:

```json
{
  "project_id": "0b39f01f-55b4-41de-bb1e-732cc248ab3b"
}
```

Forbidden input pattern:

```json
{
  "path": "/home/user/projects/some_project"
}
```

### 6.1 Configured projects root

The server configuration must contain a section that defines the host directory containing project subdirectories.

Example configuration:

```yaml
projects:
  root_dir: /home/vasilyvz/projects/tools
  marker_file: projectid
  marker_format: json
  require_uuid4_id: true
  allow_nested_projects: false
```

Only direct subdirectories of `projects.root_dir` are candidates by default.

A candidate directory is considered a project only when it contains the application marker file configured by `projects.marker_file`. The default marker file name is `projectid`.

The marker file must be JSON. The minimum required shape is:

```json
{
  "id": "<uuid4>",
  "description": "<human-readable project description>"
}
```

The value of `id` is the project identifier accepted by the API as `project_id`. The directory name is not the project identity; it is only the host-side location under `projects.root_dir`.

### 6.2 Discovery rules

On startup and on explicit refresh, the server scans `projects.root_dir` and builds a project registry from valid marker files.

Discovery must reject:

- files directly inside `projects.root_dir`;
- directories without the marker file;
- marker files that are not valid JSON;
- marker files without `id`;
- marker files whose `id` is not a UUID4 when `require_uuid4_id` is enabled;
- duplicate project ids;
- project directories that resolve outside `projects.root_dir`;
- nested project markers when `allow_nested_projects` is false.

If duplicates are found, all conflicting projects must be disabled until the operator fixes the conflict.

### 6.3 Runtime resolution

At command execution time, the server resolves `project_id` through the registry created from marker files.

Before mounting, the server must perform canonical path checks:

```text
real_projects_root = realpath(config.projects.root_dir)
real_project_path = realpath(project.root)

real_project_path must be a direct child of real_projects_root
unless allow_nested_projects is explicitly enabled.
```

The check must reject:

- missing projects;
- deleted or disabled projects;
- paused projects if policy forbids execution;
- paths outside `projects.root_dir`;
- symlink escapes;
- relative path traversal;
- project roots that are files instead of directories.

## 7. Container Mount Model

The project root is mounted at a fixed path:

```text
/workspace
```

The caller must not be able to choose the container mount path.

Supported mount modes:

| Mode | Project mount | Additional storage | Intended use |
|------|---------------|--------------------|--------------|
| `read_only` | `/workspace:ro` | `/scratch:rw` tmpfs or disposable volume | inspection, tests that do not write, grep, static checks |
| `workspace_write` | `/workspace:rw` | `/scratch:rw` | code generation, formatting, test fixture updates |
| `scratch_write` | `/workspace:ro` | `/scratch:rw` | package download, build attempts, temporary artifacts |

Default mode: `read_only`.

`workspace_write` must be explicit in the request and recorded in audit logs.

## 8. Container Runtime Security Profile

Every execution container must use a restricted runtime profile.

Minimum required settings:

```text
--user <non_root_uid>:<non_root_gid>
--workdir /workspace
--cap-drop ALL
--security-opt no-new-privileges
--read-only
--tmpfs /tmp
--pids-limit <configured_limit>
--memory <configured_limit>
--cpus <configured_limit>
--network none by default
```

The implementation should also support:

- seccomp profile configuration;
- AppArmor or SELinux profile configuration where available;
- container root filesystem read-only mode;
- resource quotas per run and per caller;
- execution timeout;
- output truncation limits;
- maximum concurrent containers.

The service must never run privileged containers.

Forbidden runtime options:

```text
--privileged
--pid host
--network host
--ipc host
--uts host
--cap-add SYS_ADMIN
-v /:/host
-v /var/run/docker.sock:/var/run/docker.sock
```

## 9. Network Policy

Default network mode for ordinary command execution must be:

```text
network: none
```

However, practical Python work requires dependency installation. The server therefore must support a controlled network mode for package registries:

| Mode | Meaning | MVP status |
|------|---------|------------|
| `none` | No network access. Default for tests, linters, formatters, static checks, and local commands. | Required |
| `package_registry` | Egress allowed only to configured package indexes and related TLS/DNS endpoints needed for package installation. | Required |
| `restricted` | General allowlisted egress to configured domains. | Optional after MVP |
| `open` | Full outbound network. | Forbidden in MVP |

`pip install`, `pip download`, `pip-audit`, and similar dependency commands must run with `network: package_registry` unless all dependencies are already available from a local cache or wheelhouse.

`package_registry` must be policy-controlled. The server configuration should define allowlisted registries, for example:

```yaml
network:
  modes:
    package_registry:
      allow_dns: true
      allow_tls: true
      allowed_hosts:
        - pypi.org
        - files.pythonhosted.org
      allowed_ports: [443]
```

Network mode must be part of the request and audit record.

`open` network must not be available in the initial MVP.

## 10. Command Execution Model

The MVP should support atomic, non-interactive command execution.

The command must be represented as an argv array by default:

```json
{
  "cmd": ["pytest", "-q"]
}
```

The default mode must not use a shell.

Shell execution is riskier and must be a separate explicit mode if added later:

```json
{
  "shell": true,
  "command": "pytest -q"
}
```

For MVP, shell mode should be disabled.

## 11. Working Directory Policy

`cwd` must be relative to `/workspace`.

Valid examples:

```text
.
tests
mcp_terminal/commands
```

Invalid examples:

```text
/
/etc
../other_project
/workspace/../..
```

The server must normalize and validate `cwd` before execution.

The resolved container working directory must remain inside `/workspace`.

## 12. Environment Policy

The server may provide a minimal default environment:

```text
HOME=/tmp/home
PWD=/workspace
TMPDIR=/tmp
PATH=<image-default-safe-path>
```

The model must not be allowed to inject arbitrary host environment variables.

Optional request-level environment variables may be supported later through an allowlist.

Forbidden by default:

- host secrets;
- SSH agent sockets;
- cloud credentials;
- Docker credentials;
- package registry tokens.

## 13. Container Image Policy

The caller must not provide arbitrary image names.

The server must expose image profiles from an allowlist:

```text
python_dev_3_12
node_dev_20
base_tools
```

Example request:

```json
{
  "image_profile": "python_dev_3_12"
}
```

The policy maps `image_profile` to a concrete server-side image reference.

The image allowlist must define:

- image name and digest or pinned tag;
- default user;
- available tools;
- network policy compatibility;
- maximum timeout.

### 13.1 Baseline tools for `python_dev_3_12`

The default Python image profile must be useful for real Python project work without exposing host-control capabilities.

`venv` support is mandatory. The image must include the OS packages needed for `python -m venv` to work. A Python profile without working `venv` is not acceptable.

Recommended baseline command and package set:

| Group | Tools | Purpose |
|-------|-------|---------|
| Python runtime | `python`, `python3`, `pip`, `python -m venv`, `ensurepip` | Run Python code and create project-local virtual environments. |
| Shell basics | `bash`, `sh`, `env`, `pwd`, `ls`, `cat`, `head`, `tail`, `wc`, `sort`, `uniq`, `xargs`, `tee`, `printf`, `test`, `true`, `false` | Basic diagnostics and command composition. |
| File inspection | `find`, `grep`, `rg`, `sed`, `awk`, `file`, `stat`, `du`, `tree` | Inspect source trees inside `/workspace`. |
| Archives | `tar`, `gzip`, `gunzip`, `zip`, `unzip`, `7z` / `p7zip` | Inspect and unpack common local artifacts, including `.7z` archives. |
| Local databases | `sqlite3` | Inspect project-local SQLite databases without installing extra packages. |
| Version control | `git` | Inspect repository state, diffs, branches, and local history. Network operations remain controlled by network policy. |
| Process diagnostics | `ps`, `pgrep`, `pkill` | Inspect and stop processes inside the sandbox only. |
| Test runner | `pytest`, `pytest-cov`, `coverage` | Run tests and coverage. |
| Formatting | `black`, `isort` | Format Python code and imports. |
| Linting | `flake8`, `ruff` | Static quality checks. `flake8` is the correct spelling; `flask8` is invalid. |
| Typing | `mypy` | Static type checking. |
| Packaging | `build`, `wheel`, `setuptools`, `pip-tools` | Build packages and manage pinned dependency files. |
| Security audit | `bandit`, `pip-audit` | Local code and dependency security checks. Dependency audit may require `network: package_registry`. |
| Dependency inspection | `pipdeptree` | Inspect installed dependency graphs. |
| Optional workflow | `tox`, `nox`, `pre-commit` | Common project automation tools. Include if image size is acceptable. |

The baseline image should also contain CA certificates and TLS support required by `pip` when `network: package_registry` is enabled.

### 13.2 Dependency installation policy

The intended dependency workflow is:

1. Create or reuse a project-local virtual environment under `/workspace/.venv` when write mode is allowed, or under `/scratch/.venv` when the project is read-only.
2. Install dependencies with `pip` only when the request uses `network: package_registry`, unless dependencies are available from an offline wheelhouse/cache.
3. Keep package indexes policy-controlled. The model may not inject arbitrary index URLs unless server policy explicitly allows them.
4. Do not pass host secrets, registry tokens, SSH keys, or cloud credentials into the sandbox by default.

Recommended commands that must work in `python_dev_3_12`:

```text
python -m venv .venv
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
python -m pytest
python -m black --check .
python -m flake8 .
python -m mypy .
python -m ruff check .
```

### 13.3 Tools intentionally excluded from MVP images

The MVP image must not include host-control or container-control tools that make escape attempts easier.

Exclude by default:

```text
docker
podman
kubectl
helm
ssh
scp
sftp
rsync
systemctl
sudo
su
mount
umount
iptables
nft
ip
ifconfig
tcpdump
nmap
socat
nc
netcat
```

Compilers and native build tools such as `gcc`, `g++`, `make`, and `cmake` should be excluded from the default `python_dev_3_12` profile to reduce attack surface. If native extension builds are required, create a separate `python_build_3_12` image profile with stricter resource limits and the same filesystem/network isolation.

### 13.4 Command policy layer

The runtime should support command policy in addition to image contents.

For MVP, the recommended default is:

- allow execution of installed baseline tools;
- deny direct execution of excluded tools even if accidentally present in the image;
- deny absolute executable paths outside the safe `PATH`;
- deny commands containing empty argv or NUL bytes;
- record the resolved executable path in the audit record;
- treat package installation as a sensitive operation requiring `network: package_registry`.

## 14. API Commands

Terminal execution is queue-only and session-scoped. A terminal session is identified by the pair `project_id` + `session_id`, where `session_id` is a UUID4 value.

Each project may have multiple terminal sessions. Each session stores command history and command output files under the project-local `.terminals/<session_id>/` directory.

### 14.1 Session storage layout

For every terminal session, the server stores files under:

```text
.terminals/<session_id>/
```

The directory must contain an append-only command index and per-command output files:

```text
.terminals/<session_id>/
  history.jsonl
  000001.meta.json
  000001.stdout.log
  000001.stderr.log
  000002.meta.json
  000002.stdout.log
  000002.stderr.log
```

The command sequence number is session-local and monotonically increasing. File names use a zero-padded decimal sequence number.

`stdout` and `stderr` must be stored in separate files. A separate combined output file is not required for MVP.

`history.jsonl` contains one JSON object per command:

```json
{
  "seq": 1,
  "job_id": "terminal_...",
  "project_id": "...",
  "session_id": "<uuid4>",
  "timestamp": "2026-05-15T12:34:56Z",
  "cmd_display": "grep \"some text\" file.txt | more",
  "cmd": ["bash", "-lc", "grep \"some text\" file.txt | more"],
  "cwd": ".",
  "mode": "read_only",
  "network": "none",
  "image_profile": "python_dev_3_12",
  "status": "completed",
  "exit_code": 0,
  "timed_out": false,
  "stdout_file": "000001.stdout.log",
  "stderr_file": "000001.stderr.log"
}
```

### 14.2 `terminal_session_create`

Creates a new terminal session for a project and returns `session_id`.

Request:

```json
{
  "project_id": "<uuid4>",
  "image_profile": "python_dev_3_12",
  "mode": "read_only",
  "network": "none"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "project_id": "<uuid4>",
    "session_id": "<uuid4>",
    "session_dir": ".terminals/<session_id>/"
  }
}
```

### 14.3 `terminal_run`

Queues a command for execution inside an existing terminal session. It must not execute the command synchronously in the request handler.

The command may be either argv-style or shell-style. Shell-style is required for pipelines such as `grep "some text" file.txt | more`; when shell-style is used, the server must run it through an allowlisted shell such as `bash -lc` inside the sandbox.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "command": "grep \"some text\" file.txt | more",
  "cwd": ".",
  "timeout_seconds": 300,
  "mode": "read_only",
  "network": "none"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "project_id": "<uuid4>",
    "session_id": "<uuid4>",
    "seq": 25,
    "job_id": "terminal_...",
    "status": "pending",
    "stdout_file": "000025.stdout.log",
    "stderr_file": "000025.stderr.log",
    "meta_file": "000025.meta.json"
  }
}
```

### 14.4 `terminal_list`

Returns recent commands for a specific terminal session, similar to `bash history`.

The `terminal_` prefix is required for all public MCP commands to avoid ambiguity with commands executed inside the sandbox container, such as `grep`, `tail`, `head`, or `stat`.

Default output order is descending by launch timestamp. Default limit is 25.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "limit": 25
}
```

Response columns:

```text
timestamp | seq | status | exit_code | command
```

### 14.5 `terminal_get`

Returns metadata for one command by exact session-local command sequence number.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "seq": 25
}
```

The response must include timestamp, `seq`, `job_id`, command display string, cwd, status, exit code, timeout flag, stdout/stderr file names, and stdout/stderr byte sizes.

### 14.6 `terminal_read`

Reads command output by session-local command sequence number. The caller selects `stdout` or `stderr`.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "seq": 25,
  "stream": "stdout",
  "offset": 0,
  "max_bytes": 65536
}
```

### 14.7 `terminal_search_commands`

Searches command history by regular expression. This command searches command metadata, not command output files.

Searchable fields should include `cmd_display`, `cwd`, `status`, `exit_code`, and timestamp fields.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "pattern": "pytest|mypy|ruff",
  "limit": 25
}
```

### 14.8 `terminal_search_output`

Searches command output files by regular expression.

The search may be scoped to one command sequence number and one stream, or to both streams when `stream` is omitted. If `seq` is omitted, the search is scoped to recent commands in the session using `limit_commands`.

Request for one command:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "seq": 25,
  "stream": "stderr",
  "pattern": "ERROR|Traceback",
  "max_matches": 50
}
```

Request across recent commands:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "stream": "stderr",
  "pattern": "ModuleNotFoundError",
  "limit_commands": 25,
  "max_matches_per_command": 20
}
```

### 14.9 `terminal_tail`

Returns the last lines from a command output file. This is a convenience reader for large outputs.

Request:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>",
  "seq": 25,
  "stream": "stdout",
  "lines": 100
}
```

### 14.10 `terminal_sessions`

Returns terminal sessions for one project.

Request:

```json
{
  "project_id": "<uuid4>",
  "limit": 25
}
```

Response columns:

```text
session_id | created_at | last_command_at | commands_count | status | expires_at
```

### 14.11 `terminal_delete`

Deletes terminal session directories and their command output files.

`session_id` is required. `project_id` is optional:

- when `project_id` is provided, delete only `.terminals/<session_id>/` inside that project;
- when `project_id` is omitted, delete matching session directories across all known projects.

Request with project scope:

```json
{
  "project_id": "<uuid4>",
  "session_id": "<uuid4>"
}
```

Request across projects:

```json
{
  "session_id": "<uuid4>"
}
```

The command must report every deleted or skipped session path using logical project/session identifiers, not raw host paths.

### 14.12 `terminal_get_status`

Returns queue status plus terminal-specific metadata for a command by `project_id`, `session_id`, and `seq`.

The status response must include `job_id`, queue status, terminal status, `exit_code`, `timed_out`, file names, and output byte sizes.

## 15. Execution Lifecycle

MVP lifecycle for `terminal_run`:

1. Validate request schema.
2. Validate semantic constraints.
3. Resolve `project_id` and `session_id`.
4. Allocate the next session-local command sequence number.
5. Create `NNNNNN.meta.json`, `NNNNNN.stdout.log`, and `NNNNNN.stderr.log`.
6. Append the pending command record to `history.jsonl`.
7. Add a terminal execution job to the queue.
8. Return `job_id`, `seq`, and output file names.
9. Worker starts the sandbox container.
10. Worker redirects stdout to `NNNNNN.stdout.log` and stderr to `NNNNNN.stderr.log`.
11. Worker updates metadata and queue state on completion, failure, stop, or timeout.
12. Worker stops and removes the container.

No terminal command may execute a container synchronously in the request handler.

## 16. Configuration, TTL, Generator, and Validator

The server must use the existing `mcp_proxy_adapter` configuration reader. `mcp_terminal` must not reimplement adapter config loading.

The terminal-specific config generator and validator must be overlays around the adapter generator and validator, following the `embed` project pattern:

- generator: call the adapter `SimpleConfigGenerator` first, then merge terminal-specific sections;
- validator: validate with adapter `SimpleConfig` / `SimpleConfigValidator` first, then run terminal-specific validation;
- CLI: expose `generate`, `validate`, and `help` subcommands similar to `embed.cli.config_cli`;
- generated configs must be valid adapter configs plus terminal-specific sections.

Required terminal-specific config sections:

```yaml
terminal:
  sessions:
    ttl_seconds: 86400
    cleanup_interval_seconds: 3600
    max_sessions_per_project: 50
    max_commands_per_session: 1000
  output:
    max_stdout_file_bytes: 100000000
    max_stderr_file_bytes: 100000000
    default_read_bytes: 65536
    max_read_bytes: 262144
  commands:
    default_history_limit: 25
    max_history_limit: 200
  cleanup:
    delete_expired_sessions: true
    delete_running_sessions: false
```

`terminal.sessions.ttl_seconds` is required and must be included in both the config generator defaults and the terminal-specific validator.

The validator must reject:

- missing `terminal.sessions.ttl_seconds`;
- non-positive TTL values;
- non-positive cleanup interval;
- non-positive output read limits;
- `default_history_limit` greater than `max_history_limit`;
- `max_sessions_per_project` less than 1;
- `max_commands_per_session` less than 1.

The server must track forgotten sessions and delete expired session directories according to `terminal.sessions.ttl_seconds`. A session is expired when its last command timestamp or session creation timestamp is older than the configured TTL.

Cleanup must never delete active running jobs unless `terminal.cleanup.delete_running_sessions` is explicitly enabled. The default is false.

## 17. Audit Requirements

Every run must create an audit record containing:

- `run_id`;
- caller identity if available;
- `project_id`;
- `session_id`;
- command sequence number;
- resolved project root hash or redacted path;
- command display string;
- command argv;
- `cwd`;
- `mode`;
- `network`;
- `image_profile`;
- container id;
- start time;
- finish time;
- duration;
- exit code;
- timeout flag;
- stdout/stderr file names and byte sizes;
- policy decision summary;
- error code if failed.

Audit logs must avoid recording secret environment values.

## 18. Error Model

Errors must use stable codes.
Recommended error codes:

| Code | Meaning |
|------|---------|
| `PROJECT_NOT_FOUND` | `project_id` is unknown. |
| `PROJECT_DELETED` | Project is marked deleted. |
| `PROJECT_PAUSED` | Execution blocked by project processing policy. |
| `PROJECT_PATH_OUT_OF_SCOPE` | Canonical path is outside allowed roots. |
| `INVALID_CWD` | `cwd` escapes `/workspace` or is invalid. |
| `INVALID_COMMAND` | `cmd` is empty or contains invalid argv elements. |
| `IMAGE_PROFILE_NOT_ALLOWED` | Requested image profile is not allowlisted. |
| `MODE_NOT_ALLOWED` | Requested mount/write mode is forbidden by policy. |
| `NETWORK_MODE_NOT_ALLOWED` | Requested network mode is forbidden. |
| `TIMEOUT_EXCEEDED` | Command exceeded timeout. |
| `OUTPUT_LIMIT_EXCEEDED` | Output was truncated. |
| `CONTAINER_CREATE_FAILED` | Runtime failed to create container. |
| `CONTAINER_EXEC_FAILED` | Runtime failed to execute command. |
| `CONTAINER_CLEANUP_FAILED` | Container cleanup failed after execution. |

## 18. Safety Invariants

The following invariants must be covered by tests:

1. A model cannot provide a host path instead of `project_id`.
2. A model cannot select arbitrary mount points.
3. A model cannot mount parent watch directories.
4. A model cannot escape `/workspace` via `cwd`.
5. A model cannot escape via symlinks in `cwd`.
6. A model cannot enable host networking.
7. A model cannot add Linux capabilities.
8. A model cannot run privileged containers.
9. A model cannot access Docker socket.
10. A model cannot access unrelated projects.
11. Read-only mode prevents writes to `/workspace`.
12. Scratch mode permits writes to `/scratch` but not `/workspace`.
13. Write mode allows writes only in the mounted project.
14. Timeout terminates long-running commands.
15. Output limits truncate large output safely.
16. Container cleanup happens after success, failure, and timeout.
17. Audit record is created for success and failure.

## 19. MVP Acceptance Criteria

The MVP is complete only when all items are true:

- `terminal_run` appears in MCP `help`.
- `terminal_run` rejects unknown `project_id`.
- `terminal_run` rejects direct host path input.
- `terminal_run` executes `cmd` in a disposable non-root container.
- Project is mounted only at `/workspace`.
- Default mode is `read_only`.
- Default network is `none`.
- Attempts to write in `read_only` mode fail.
- `workspace_write` mode can create a file inside the project when explicitly requested.
- `cwd=..` or absolute host-like paths are rejected.
- Container cannot access `/var/run/docker.sock`.
- Container cannot access files outside the mounted project.
- Timeout works and cleans up the container.
- stdout/stderr are written to sequence-based files, not returned as large inline payloads.
- Every run has an audit record.
- Result can be verified through queue status plus `terminal_read` / `terminal_search_output`.

## 20. Current Code State and Required Structural Refactor

The current `mcp_terminal` codebase already contains a working server skeleton based on `mcp_proxy_adapter`, but it does not yet contain the terminal domain implementation.

Existing code that must be preserved and extended:

```text
mcp_terminal/term_server.py   # adapter-based FastAPI/Hypercorn server startup
mcp_terminal/term_config.py   # adapter SimpleConfig reader and validator entrypoint
mcp_terminal/termgr.py        # start/stop/status process manager
mcp_terminal/paths.py         # repository root helper
tests/test_imports.py         # import smoke test
```

The current server is visible in the proxy and already exposes adapter built-in commands and queue commands. This means the implementation must be an incremental structural extension, not a rewrite.

Missing terminal-specific structure that must be added:

```text
mcp_terminal/commands/
  __init__.py
  terminal_sessions_command.py
  terminal_session_create_command.py
  terminal_run_command.py
  terminal_get_status_command.py
  terminal_list_command.py
  terminal_get_command.py
  terminal_read_command.py
  terminal_search_commands_command.py
  terminal_search_output_command.py
  terminal_tail_command.py
  terminal_delete_command.py

mcp_terminal/jobs/
  __init__.py
  terminal_execution_job.py

mcp_terminal/services/
  __init__.py
  project_registry.py
  session_store.py
  command_history.py
  output_reader.py
  sandbox_policy.py
  container_runner.py
  ttl_cleanup.py

mcp_terminal/config/
  __init__.py
  config_generator.py
  config_validator.py
  config_cli.py
```

`term_server.py` must register terminal custom commands through the adapter hook mechanism, following the `embed` project pattern.

The actual container execution must be implemented as a queue job, not as a public direct command. Do not expose an internal `terminal_execute` command in MCP `help`.

## 21. Implementation Phases

### Phase 1: Preserve and extend the adapter skeleton

- Keep `term_server.py`, `term_config.py`, `termgr.py`, and `paths.py`.
- Add terminal command registration hook to `term_server.py`.
- Verify that existing built-in and queue commands still appear in MCP `help`.
- Add terminal commands to `help` only after their schemas and validators are implemented.

### Phase 2: Config overlay

- Keep using adapter `SimpleConfig` as the reader.
- Implement `mcp_terminal.config.config_generator` as an overlay over adapter `SimpleConfigGenerator`.
- Implement `mcp_terminal.config.config_validator` as an overlay over adapter `SimpleConfig` / `SimpleConfigValidator`.
- Implement `mcp_terminal.config.config_cli` with `generate`, `validate`, and `help` commands, following `embed.cli.config_cli`.
- Add terminal TTL and output parameters to generator defaults and validator checks.

### Phase 3: Project and session services

- Implement project discovery from `projects.root_dir` and `projectid` marker files.
- Implement session directory creation under `.terminals/<session_id>/`.
- Implement command sequence allocation per session.
- Implement `history.jsonl` append and read logic.
- Implement session TTL cleanup with protection for running jobs.

### Phase 4: Queue-only execution

- Implement `TerminalExecutionJob`.
- `terminal_run` must only create metadata/output files, append history, add queue job, and return `job_id` + `seq`.
- The worker must run the container and redirect stdout/stderr to `NNNNNN.stdout.log` and `NNNNNN.stderr.log`.
- The worker must update command metadata and queue state on success, failure, stop, and timeout.

### Phase 5: Reader and navigation commands

- Implement `terminal_sessions` for project session listing.
- Implement `terminal_list` for session command history.
- Implement `terminal_get` for exact command metadata by `seq`.
- Implement `terminal_read` with offset and byte limits.
- Implement `terminal_search_commands` with regex over command history metadata.
- Implement `terminal_search_output` with regex over stdout/stderr files.
- Implement `terminal_tail` for last lines of stdout/stderr.
- Implement `terminal_get_status` as a terminal-aware wrapper over queue state plus command metadata.
- Implement `terminal_delete` for session deletion by `session_id`, optionally scoped by `project_id`.
- Do not expose short public MCP aliases such as `list`, `delete`, `grep`, `tail`, `head`, or `stat` in MVP because they can be confused with commands executed inside the sandbox container.

### Phase 6: Container isolation

- Implement sandbox policy validation.
- Implement container creation with fixed `/workspace` mount.
- Enforce non-root user, no Docker socket, no privileged mode, resource limits, and network policy.
- Ensure stdout/stderr redirection to files is the only output path for command execution.

## 22. Testing Strategy

Tests must include both normal and hostile cases.

### Unit tests

- Config generator produces adapter-valid config plus terminal sections.
- Config validator calls adapter validation first and then terminal-specific checks.
- Missing or invalid `terminal.sessions.ttl_seconds` is rejected.
- Project discovery accepts only valid `projectid` marker files.
- Session ids are UUID4.
- Command sequence allocation is monotonic per session.
- `terminal_list` requires `project_id` and `session_id`.
- `terminal_delete` requires `session_id` and treats `project_id` as optional.
- `terminal_get` requires exact `project_id + session_id + seq`.
- `terminal_search_commands` searches command metadata only.
- `terminal_search_output` searches stdout/stderr files only.
- Output reader rejects invalid stream names and path traversal.
- Regex search enforces match limits.

### Integration tests

- `mcp-terminal` appears in proxy server list.
- MCP `help` shows `terminal_sessions`, `terminal_session_create`, `terminal_run`, `terminal_list`, `terminal_get`, `terminal_read`, `terminal_search_commands`, `terminal_search_output`, `terminal_tail`, `terminal_delete`, and `terminal_get_status`.
- MCP `help` does not expose short aliases such as `list`, `delete`, `grep`, `tail`, `head`, or `stat`.
- `terminal_session_create` creates `.terminals/<session_id>/`.
- `terminal_run` returns `job_id`, `seq`, `stdout_file`, `stderr_file`, and `meta_file`.
- Queue status reaches completed/failed/stopped without masking nested command failure.
- stdout is written only to `NNNNNN.stdout.log`.
- stderr is written only to `NNNNNN.stderr.log`.
- `terminal_list` returns the last 25 commands in descending timestamp order by default.
- `terminal_get` returns metadata for exact `project_id + session_id + seq`.
- `terminal_read` reads by `project_id + session_id + seq + stream`.
- `terminal_search_commands` finds regex matches in command history metadata.
- `terminal_search_output` finds regex matches in stdout/stderr files.
- `terminal_tail` returns last lines from stdout/stderr without loading the whole file.
- `terminal_delete` removes the requested session directory and verifies it is gone by a separate read/list command.

### Security regression tests

- Attempt `cwd=..`.
- Attempt `cwd=/`.
- Attempt reading `/host`.
- Attempt reading `/var/run/docker.sock`.
- Attempt writing outside `/workspace`.
- Attempt symlink escape from project tree.
- Attempt requesting forbidden network mode.
- Attempt requesting arbitrary image.
- Attempt requesting privileged options.
- Attempt deleting a session outside `.terminals`.
- Attempt reading output with path traversal instead of `seq`.

## 23. Operational Defaults

Recommended initial defaults:

```yaml
terminal:
  sessions:
    ttl_seconds: 86400
    cleanup_interval_seconds: 3600
    max_sessions_per_project: 50
    max_commands_per_session: 1000
  output:
    max_stdout_file_bytes: 100000000
    max_stderr_file_bytes: 100000000
    default_read_bytes: 65536
    max_read_bytes: 262144
  commands:
    default_history_limit: 25
    max_history_limit: 200
  cleanup:
    delete_expired_sessions: true
    delete_running_sessions: false
runtime:
  default_image_profile: python_dev_3_12
  default_mode: read_only
  default_network: none
  timeout_seconds: 60
  max_timeout_seconds: 300
  memory: 1g
  cpus: 1.0
  pids_limit: 256
  max_concurrent_runs: 4
  cleanup_always: true
```

## 24. Open Questions

1. Which exact marker filename is final: `projectid` only, or configurable `projects.marker_file`?
2. Should `list` require `project_id` despite `delete` allowing omitted `project_id`? Current recommendation: yes.
3. Should `terminal_session_create` be explicit, or should `terminal_run` create sessions when `session_id` is omitted? Current recommendation: explicit session creation.
4. Should shell-style commands be the only public command format because pipelines are required?
5. Should session TTL be based on session creation time, last command start time, or last command finish time? Current recommendation: last command timestamp, fallback to creation timestamp.
6. Should expired sessions with failed or stopped jobs be deleted immediately after TTL?
7. Should `delete` be allowed to remove sessions with running jobs? Current recommendation: no by default.
8. Should output files live inside project `.terminals` even in read-only mode? Current recommendation: yes, terminal metadata is service-managed project state.
9. How should file ownership be mapped between container user and host user?
10. Is rootless Docker/Podman required for deployment?

## 25. Initial Recommendation

Implement the current adapter skeleton as a queue-only, session-scoped terminal service:

- preserve existing adapter server startup and config reader;
- add terminal commands via `register_custom_commands_hook`;
- implement config generator/validator as overlays over adapter tools;
- use `project_id + session_id` for every session-scoped operation;
- store per-session state in `.terminals/<session_id>/`;
- store stdout and stderr in separate per-command files with sequence-based names;
- expose history through `list`;
- expose output through read/search commands, not queue result payloads;
- enforce TTL cleanup from config;
- keep actual container execution inside queue jobs only;
- validate completion through MCP calls, queue status, and read-back of generated files.