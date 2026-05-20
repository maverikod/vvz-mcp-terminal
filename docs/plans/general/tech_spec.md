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
      -> terminal_run queues a terminal command
        -> worker starts sandbox container
          -> /workspace mounted from the resolved project directory
          -> command executes inside /workspace
          -> stdout redirected to .terminals/<session_id>/NNNNNN.stdout.log
          -> stderr redirected to .terminals/<session_id>/NNNNNN.stderr.log
        -> worker writes metadata and updates queue state
      -> caller reads output via terminal_read / terminal_search_output / terminal_tail
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
  require_uuid4_id: true
  allow_nested_projects: false
```

Only direct subdirectories of `projects.root_dir` are candidates by default.

A candidate directory is considered a project only when it contains the standard code-project marker file named `projectid`.

`projectid` is a fixed project standard. It must not be renamed, made configurable, migrated, rewritten, or otherwise modified by `mcp_terminal`. The server may only read it.

The `projectid` marker file must be JSON. The minimum required shape is:

```json
{
  "id": "<uuid4>",
  "description": "<human-readable project description>"
}
```

The value of `id` is the project identifier accepted by the API as `project_id`. The directory name is not the project identity; it is only the host-side location under `projects.root_dir`.

### 6.2 Discovery rules

On startup and on explicit refresh, the server scans `projects.root_dir` and builds a project registry from valid `projectid` marker files.

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

`terminal_run` supports two explicit execution kinds:

| Kind | Description | Use case |
|------|-------------|----------|
| `argv` | Executes a command as an argv array without a shell. | Simple commands: `pytest -q`, `black .`, `mypy .` |
| `shell` | Runs the command string through an allowlisted shell (`bash -lc`) inside the sandbox. | Pipelines and shell composition: `grep "text" file.txt \| more` |

`session_id` is required in every `terminal_run` request. It must be a UUID4 and must refer to an existing session. `terminal_run` must not create a session implicitly.

If `execution_kind` is omitted, the server must reject the request with `INVALID_COMMAND`.

`shell` execution is required for pipelines and shell composition. `argv` is preferred for simple commands because it avoids shell injection risk. Both modes are audited.

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

`history.jsonl` contains one JSON object per command.

Shell execution example:

```json
{
  "seq": 1,
  "job_id": "terminal_...",
  "project_id": "...",
  "session_id": "<uuid4>",
  "timestamp": "2026-05-15T12:34:56Z",
  "execution_kind": "shell",
  "command": "grep \"some text\" file.txt | more",
  "argv": null,
  "resolved_argv": ["bash", "-lc", "grep \"some text\" file.txt | more"],
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

Argv execution example:

```json
{
  "seq": 2,
  "job_id": "terminal_...",
  "project_id": "...",
  "session_id": "<uuid4>",
  "timestamp": "2026-05-15T12:35:10Z",
  "execution_kind": "argv",
  "command": null,
  "argv": ["pytest", "-q"],
  "resolved_argv": ["pytest", "-q"],
  "cwd": ".",
  "mode": "read_only",
  "network": "none",
  "image_profile": "python_dev_3_12",
  "status": "completed",
  "exit_code": 0,
  "timed_out": false,
  "stdout_file": "000002.stdout.log",
  "stderr_file": "000002.stderr.log"
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
| `INVALID_COMMAND` | Command request is empty or contains invalid shell/argv execution fields. |
| `INVALID_SESSION` | `session_id` is missing, not a UUID4, or does not exist. |
| `IMAGE_PROFILE_NOT_ALLOWED` | Requested image profile is not allowlisted. |
| `MODE_NOT_ALLOWED` | Requested mount/write mode is forbidden by policy. |
| `NETWORK_MODE_NOT_ALLOWED` | Requested network mode is forbidden. |
| `TIMEOUT_EXCEEDED` | Command exceeded timeout. |
| `OUTPUT_LIMIT_EXCEEDED` | Output was truncated. |
| `CONTAINER_CREATE_FAILED` | Runtime failed to create container. |
| `CONTAINER_EXEC_FAILED` | Runtime failed to execute command. |
| `CONTAINER_CLEANUP_FAILED` | Container cleanup failed after execution. |

## 19. Safety Invariants

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

## 20. Queue Result Semantics

Queue job completion and terminal command success are distinct states.

A queue job reaches `completed` (progress=100) when the worker executed the full lifecycle and wrote metadata.
This does not mean the terminal command succeeded.

Terminal command success requires all of:

- queue status is `completed`;
- `exit_code == 0`;
- `timed_out == false`.

`terminal_get_status` must expose both the queue job status and the nested terminal command result.
Callers must not treat `queue completed` as `command success` without inspecting `exit_code` and `timed_out`.

## 21. MVP Acceptance Criteria

The MVP is complete only when all items are true:

- `terminal_run` appears in MCP `help`.
- `terminal_run` rejects unknown `project_id`.
- `terminal_run` rejects direct host path input.
- `terminal_run` rejects missing or invalid `session_id`.
- `terminal_run` queues a terminal command for an existing session and returns `job_id`, `seq`, and output file names.
- `terminal_run` supports both `shell` and `argv` execution kinds.
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
- Result can be verified through `terminal_get_status` plus `terminal_read` / `terminal_search_output`.

## 22. Current Code State and Required Structural Refactor

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
  terminal_stat_command.py
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

## 23. Implementation Phases

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
- Implement `terminal_stat` for lightweight command/session metadata and output size statistics.
- Implement `terminal_get_status` as a terminal-aware wrapper over queue state plus command metadata.
- Implement `terminal_delete` for session deletion by `session_id`, optionally scoped by `project_id`, with running-session deletion allowed only through an explicit force flag.
- Do not expose short public MCP aliases such as `list`, `delete`, `grep`, `tail`, `head`, or `stat` in MVP because they can be confused with commands executed inside the sandbox container.

### Phase 6: Container isolation

- Implement sandbox policy validation.
- Implement container creation with fixed `/workspace` mount.
- Enforce non-root user, no Docker socket, no privileged mode, resource limits, and network policy.
- Ensure stdout/stderr redirection to files is the only output path for command execution.

## 24. Testing Strategy

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
- `terminal_delete` rejects running sessions unless explicit force is provided.
- `terminal_get` requires exact `project_id + session_id + seq`.
- `terminal_stat` returns command/session metadata without reading full output files.
- `terminal_search_commands` searches command metadata only.
- `terminal_search_output` searches stdout/stderr files only.
- Output reader rejects invalid stream names and path traversal.
- Regex search enforces match limits.

### Integration tests

- `mcp-terminal` appears in proxy server list.
- MCP `help` shows `terminal_sessions`, `terminal_session_create`, `terminal_run`, `terminal_list`, `terminal_get`, `terminal_read`, `terminal_search_commands`, `terminal_search_output`, `terminal_tail`, `terminal_stat`, `terminal_delete`, and `terminal_get_status`.
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
- `terminal_stat` returns command/session metadata and output sizes without loading full output files.
- `terminal_delete` removes the requested session directory and verifies it is gone by a separate `terminal_sessions` / `terminal_list` read command.
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

## 25. Operational Defaults

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
    default_tail_lines: 100
    max_tail_lines: 5000
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

## 26. Final Decisions

The following decisions are binding for decomposition and implementation:

1. The project marker filename is fixed: `projectid`. It is not configurable and must only be read by `mcp_terminal`.
2. `terminal_run` supports both explicit execution kinds: `shell` and `argv`.
3. `terminal_run` must not create sessions implicitly. It requires an existing UUID4 `session_id` and must validate it.
4. Session TTL is based on `last_activity_at`. Activity includes session creation, command start, command finish, output read, output search, and explicit metadata access.
5. Expired `completed`, `failed`, and `stopped` sessions may be deleted after TTL.
6. Running sessions may be deleted only when the request contains an explicit force flag.
7. `.terminals/<session_id>/` is stored inside the project directory. The service must ensure `.terminals/` is ignored by Git.
8. `terminal_stat` is included in MVP as a lightweight metadata/statistics command.
9. Rootless Docker or Podman is recommended for deployment hardening but is not required for MVP unless the target environment already mandates it.

## 27. Initial Recommendation

Implement the current adapter skeleton as a queue-only, session-scoped terminal service:

- preserve existing adapter server startup and config reader;
- add terminal commands via `register_custom_commands_hook`;
- implement config generator/validator as overlays over adapter tools;
- use `project_id + session_id` for every session-scoped operation;
- store per-session state in `.terminals/<session_id>/`;
- store stdout and stderr in separate per-command files with sequence-based names;
- expose history through `terminal_list`;
- expose output through `terminal_read` / `terminal_search_output`, not queue result payloads;
- enforce TTL cleanup from config;
- keep actual container execution inside queue jobs only;
- validate completion through MCP calls, queue status, and read-back of generated files.
## 28. Execution Targets

This section introduces the **execution target axis** as a first-class concept of the system. Sections 1–27 above describe the original sandbox model. Real implementation has since added a second target (`host`) and reserved a third (`attached`) for future work. This section defines the axis, the targets, their isolation properties, and the matrix of which sections of this specification apply to which target.

The execution target axis is orthogonal to session identity. A single `(project_id, session_id)` pair may, over its lifetime, accept commands directed at different targets. The target is selected per `terminal_run*` invocation through the choice of MCP command, not through session creation.

### 28.1 Target axis

The system supports three execution targets:

| target_kind | Status | MCP command | Isolation |
|-------------|--------|-------------|-----------|
| `sandbox`   | Required, default product mode. | `terminal_run` | Per-session Docker container with fixed `/workspace` mount, runtime security profile of §8, network policy of §9. |
| `host`      | Required, gated by config. Transitional. Scheduled for removal once `code-analysis-server` and `mcp_terminal` themselves run inside containers. | `terminal_run_host` | None at the container level. Defense-in-depth via host-side allowlist (`terminal.host_execution.allowed_commands`), hard-forbidden executables, and forbidden-pattern scanning over command text, redirect targets, here-strings, and heredoc bodies. |
| `attached`  | Reserved for future implementation. Not exposed in MCP `help`. Not validated by any policy yet. | (planned) `terminal_run_attached` | Will be `docker exec` into a pre-existing running container chosen from a server-side allowlist of infrastructure containers. The container itself is not owned by `mcp_terminal`; its runtime profile is determined by its owner. |

The `sandbox` target is the original system as described in §§3–17 of this specification. The `host` and `attached` targets are extensions on the execution axis. They share session storage (§14.1), command sequencing (§14, §15), output store, audit (§17), and error contract (§18), but each carries its own validation policy and execution lifecycle.

### 28.2 Applicability matrix of existing sections

The table below indicates which sections of §§1–27 apply to which target. Sections marked `sandbox-only` describe sandbox container semantics and do not constrain `host` or `attached` execution. Sections marked `all` constrain every target.

| Section | Topic | Applies to |
|---------|-------|------------|
| §1  Purpose                                | `sandbox` is the primary purpose; `host` and `attached` are auxiliary. | all (interpreted) |
| §2  Non-goals                              | The non-goal "must not become a general-purpose remote shell" still binds; `host` is a narrow, config-gated exception with its own allowlist, not a general remote shell. | all |
| §3  High-level Architecture                | Describes sandbox flow; `host` flow bypasses ContainerRuntime; `attached` flow will use `docker exec` instead of `docker run`. | sandbox (canonical), reinterpreted for others |
| §4.1 Trusted components                    | Project registry, server-side policy config, container image allowlist — all still trusted. Add: host-execution config (allowlist + enabled flag). | all |
| §4.2 Untrusted inputs                      | Holds for every target: command text, cwd, env requests, network requests, write-mode requests, file contents are untrusted regardless of target. | all |
| §4.3 Sensitive host resources              | The list of resources the sandbox must not expose remains in force for `sandbox`. For `host`, those resources are reachable in principle because the process runs on the host; the host-execution policy protects them via allowlist + forbidden patterns + hard-forbidden executables, not via container isolation. For `attached`, depends on the chosen container's own isolation. | sandbox (literal), host (by policy), attached (by container owner) |
| §5  Core Security Principle                | "Controlled project sandbox, not host terminal" remains the design intent. `host` is a documented, gated exception under operator-curated allowlist. | all (interpreted) |
| §6  Project Discovery and Resolution       | `project_id` resolution and registry are shared across all targets. `host` and `attached` use the same `ProjectRegistry`. | all |
| §7  Container Mount Model                  | `/workspace` mount, mount modes (read_only / workspace_write / scratch_write) — only sandbox. `host` operates directly on the host project tree at its real path; there is no `/workspace`. `attached` does not own the container, so it does not control mounts. | sandbox-only |
| §8  Container Runtime Security Profile     | Capability drop, no-new-privileges, read-only rootfs, tmpfs, resource limits, network none default — all sandbox semantics. | sandbox-only |
| §9  Network Policy                         | `network: none` / `network: package_registry` parameters belong to sandbox. `host` runs with the host's own network. `attached` inherits the attached container's network. | sandbox-only |
| §10 Command Execution Model                | Two execution kinds, `shell` and `argv`, apply to every target. The validation that follows differs per target. | all |
| §11 Working Directory Policy               | `cwd` must be project-relative for all targets. For `sandbox`, it resolves under `/workspace`. For `host`, it resolves under the project root on the host. For `attached`, it resolves under whatever workdir the attached container exposes. Absolute paths and `..` are rejected universally. | all |
| §12 Environment Policy                     | Minimal environment, no host-secret injection. Applies universally. Specifics differ: `host` PATH may be augmented by `use_venv` per session config; `sandbox` PATH comes from the image. | all (interpreted) |
| §13 Container Image Policy                 | Image profiles, allowlist, default user — sandbox only. `host` has no image; `attached` does not control the image. | sandbox-only |
| §14 API Commands                           | Session storage (§14.1) and reader commands (§14.4–§14.12) are shared. The execution commands diverge per target: `terminal_run` (sandbox), `terminal_run_host` (host), planned `terminal_run_attached` (attached). | all (with target-specific runners) |
| §15 Execution Lifecycle                    | The 12-step lifecycle in §15 is the sandbox lifecycle. `host` follows an analogous but shorter lifecycle without container start/stop steps. `attached` lifecycle will add a step to resolve the target container by allowlisted label/name instead of creating one. | all (with per-target shape) |
| §16 Configuration, TTL, Generator, Validator | Shared. New sections `terminal.host_execution` and (future) `terminal.attached_execution` are governed by the same generator/validator overlay pattern. | all |
| §17 Audit Requirements                     | Every target produces audit records. Field `execution_target` is mandatory and is one of `sandbox`, `host`, `attached`. Audit content per target is described in §28.6. | all |
| §18 Error Model                            | Shared. Sandbox-specific codes from §18 plus host-specific codes (see §28.5) plus future attached-specific codes form one contract. | all |
| §19 Safety Invariants                      | Invariants 1–17 of §19 were written for sandbox. §28.7 retags each invariant with applicable targets and adds host-specific invariants. | sandbox-tagged, host extends |
| §20 Queue Result Semantics                 | Identical across targets. Queue completion ≠ command success regardless of target. | all |
| §21 MVP Acceptance Criteria                | Sandbox MVP criteria are still valid. `host` adds its own acceptance criteria; see §28.8. | sandbox-tagged, host extends |
| §22 Current Code State and Required Structural Refactor | Updated facts: §28.10 reflects what is actually implemented today, including `terminal_run_host`, `terminal_kill`, `terminal_purge_sessions`, `terminal_get_session_bootstrap`, `terminal_list_watch`. | sandbox + host (current) |
| §23 Implementation Phases                  | Phases for sandbox apply. Host-execution implementation is already underway and not phased separately in this specification. | sandbox (literal), host (already underway) |
| §24 Testing Strategy                       | Sandbox tests still apply. Host-execution adds its own test set; see §28.9. | sandbox + host extends |
| §25 Operational Defaults                   | The defaults block applies to sandbox. `terminal.host_execution` defaults are defined in §28.4. | sandbox + host extends |
| §26 Final Decisions                        | Decisions remain. §28.2.x adds new binding decisions for the execution-target axis. | all |
| §27 Initial Recommendation                 | Sandbox-focused, remains valid. Host recommendation is in §28.10. | sandbox + host extends |

### 28.3 Target `sandbox` (canonical)

The `sandbox` target is described in full by §§3–17 above. No changes. Every `terminal_run` invocation produces a job whose `execution_target` is `sandbox`.

### 28.4 Target `host`

The `host` target executes commands directly on the host filesystem and host process namespace, without Docker, for a registered project. It is intended for operator-curated maintenance tasks: restarting host-resident services (`code-analysis-server`, `mcp_terminal` itself during development), running host-side diagnostic tools that cannot meaningfully run inside the sandbox, and similar scoped operations.

#### 28.4.1 Gate

The target is **disabled by default**. It is enabled only when both of the following are true in `term_server.json`:

- `terminal.host_execution.enabled` is `true`.
- `terminal.host_execution.allowed_commands` is a non-empty list of executable basenames.

If the feature is disabled or the allowlist is empty, `terminal_run_host` rejects every request with `HOST_EXECUTION_DISABLED` before queueing. The validator emits a warning at server startup when `enabled` is `true` but `allowed_commands` is empty.

#### 28.4.2 Authorization model

Authorization is **static, config-driven, allowlist-based**. There is no per-request operator confirmation, no runtime acl, no caller identity check. The trusted operator expresses intent by editing `term_server.json` before starting the server. Any client (including a language model) that can call MCP on the server can invoke any allowlisted command. The security boundary is the contents of `allowed_commands` plus the hard-forbidden list, not the caller.

This is a deliberate choice. `host` is intended as a development-time and operator-curated channel. Tighter authorization (per-caller, per-command) is out of scope for this specification.

#### 28.4.3 Configuration

```yaml
terminal:
  host_execution:
    enabled: false
    allowed_commands: []   # basenames only, e.g. ["casmgr", "pytest", "git", "systemctl"]
```

- `enabled` (bool, default `false`): master switch.
- `allowed_commands` (list[str], default `[]`): basenames of executables the host channel may invoke. Comparison is case-insensitive on basename only. Paths are not accepted in this list.

The generated default config produced by the terminal config CLI contains this section with `enabled: false` and an empty allowlist. The validator rejects non-list `allowed_commands` and emits the empty-allowlist warning described above.

#### 28.4.4 Validation policy (`HostExecutionPolicy`)

For every `terminal_run_host` request, the policy applies the following checks in order, before the request is queued:

1. **Gate**: `enabled=true` and `allowed_commands` non-empty, else `HOST_EXECUTION_DISABLED`.
2. **Session existence**: `(project_id, session_id)` resolves to an existing session, else `INVALID_SESSION`.
3. **Project resolution**: `project_id` resolves through `ProjectRegistry`, else `PROJECT_NOT_FOUND`.
4. **cwd well-formedness**: `cwd` (if provided) is project-relative, no absolute path, no `..`, no invalid characters, else `INVALID_CWD`.
5. **Shape**: `execution_kind ∈ {shell, argv}`; `command` is required when `shell`; `argv` non-empty list when `argv`, else `INVALID_COMMAND`.
6. **Command decomposition (shell)**: for `execution_kind=shell`, the command string is decomposed into segments along `&&`, `||`, `;`, `|`. Each segment's leading executable is extracted.
7. **Allowlist (argv and shell-segments)**: each leading executable basename must be present (case-insensitive) in `allowed_commands`. The validator must use basename comparison only; absolute paths and relative paths in the request are not bypasses but explicit failures (`HOST_COMMAND_NOT_ALLOWED`).
8. **Hard-forbidden executables**: regardless of allowlist content, a fixed set of executables is always rejected: `docker`, `podman`, `kubectl`, `helm`, `sudo`, `su`, `mount`, `umount`, `iptables`, `nft`, `ip`, `ifconfig`, `tcpdump`, `nmap`, `socat`, `nc`, `netcat`. Match is by basename, case-insensitive. Failure code: `HOST_FORBIDDEN_COMMAND`.
9. **Forbidden patterns (shell only)**: the policy scans the command string, redirection targets, here-string operands, and heredoc bodies for forbidden substrings such as `--pid=host`, `/var/run/docker.sock`, command substitution `$(...)`, backtick substitution, and the same hard-forbidden executable names when they appear in non-leading positions. Match: `HOST_FORBIDDEN_COMMAND`.
10. **Forbidden patterns (argv)**: same forbidden-substring scan over each argv element.

The policy never queues a request that fails any check. Audit (§28.6) is recorded both for rejected and accepted requests.

#### 28.4.5 Working directory and venv

`cwd` is resolved relative to the host-side project root obtained from `ProjectRegistry`. If `cwd` is omitted, the policy uses the `cwd` field stored in `.terminals/<session_id>/shell_state.json` from the previous command of the session (sandbox or host).

`use_venv` semantics:

- omitted: use session default written at `terminal_session_create` time;
- `true`: prepend `<project_root>/.venv/bin` to PATH on the host before invocation; do not source `activate`;
- `false`: use system PATH only.

The shell_state.json `cwd` field is updated after a successful host command in the same way as after a sandbox command. Sandbox and host commands within the same session see each other's cwd transitions.

#### 28.4.6 Lifecycle (host job)

For each `terminal_run_host`:

1. Validate request shape.
2. Apply `HostExecutionPolicy` (§28.4.4).
3. Resolve `project_id` and `session_id`.
4. Allocate the next session-local sequence number.
5. Create `NNNNNN.meta.json`, `NNNNNN.stdout.log`, `NNNNNN.stderr.log`.
6. Append the pending record to `history.jsonl`.
7. Add a `TerminalHostExecutionJob` to the queue. The job carries `(project_id, session_id, seq, execution_kind, command|argv, cwd_resolved_on_host, timeout_seconds, use_venv_resolved)`.
8. Return `job_id`, `seq`, and output file names with `execution_target: host`.
9. Worker runs the command directly on the host (no container), redirecting stdout/stderr to the per-seq files.
10. Worker updates `NNNNNN.meta.json` with `exit_code`, `timed_out`, and `execution_target: host` on completion, failure, stop, or timeout.
11. Worker writes the audit record (§28.6).

The lifecycle has no container start, no container stop, no mount step.

### 28.5 Target `attached` (future)

This subsection reserves the `attached` target for future implementation. It is included here so the execution-target axis is semantically complete in the machine-readable specification and so future tactical decomposition can begin from a defined surface.

Intent: run commands inside a long-running container that `mcp_terminal` did not create — typically an infrastructure container of the surrounding deployment, such as the embedding service, the chunking service, or the proxy itself — for maintenance and diagnostic purposes.

The runtime mechanism will be `docker exec` against the target container, not `docker run` of a new container. `mcp_terminal` will not own the runtime profile, mounts, network, or image of the attached container.

This target is **not implemented**. The following is planning material only:

- The MCP command name is planned as `terminal_run_attached` and is not yet exposed.
- Configuration is planned as a `terminal.attached_execution` section with `enabled: false` default and a list of allowlisted targets, each carrying at minimum: `attached_target_id` (logical name used by the model), `container_match` (label or name selector), `allowed_commands` (target-local allowlist).
- Authorization model parallels `host`: static, config-driven, allowlist-based.
- The selected container is identified server-side by allowlisted label/name. The model never supplies a container id.
- Audit records carry `execution_target: attached` and the resolved `attached_target_id`.

Until implementation begins, no operational behavior is defined here.

### 28.6 Audit (extension of §17)

Every audit record produced by any target must additionally include:

- `execution_target` (string): one of `sandbox`, `host`, `attached`.
- For `host`: `resolved_cwd_on_host` (redacted to project-relative form), `use_venv_resolved`, `allowed_commands_snapshot_hash` (hash of the active allowlist at decision time).
- For `attached` (future): `attached_target_id`, `container_match`, `resolved_container_id` (redacted or hashed).

For rejected requests, the audit record must additionally include the policy code that caused rejection (`HOST_EXECUTION_DISABLED`, `HOST_COMMAND_NOT_ALLOWED`, `HOST_FORBIDDEN_COMMAND`, or a sandbox-side code).

### 28.7 Safety Invariants by target

This subsection tags invariants of §19 with their applicable target set and adds host-specific invariants.

| Invariant (§19 numbering) | Statement summary | Applies to |
|---------------------------|-------------------|------------|
| 1  | A model cannot provide a host path instead of `project_id`. | all |
| 2  | A model cannot select arbitrary mount points. | sandbox; host (no mounts); attached (no mounts owned) |
| 3  | A model cannot mount parent watch directories. | sandbox |
| 4  | A model cannot escape `/workspace` via cwd. | sandbox |
| 5  | A model cannot escape via symlinks in cwd. | sandbox |
| 6  | A model cannot enable host networking. | sandbox; host inherits host network by definition (out of scope) |
| 7  | A model cannot add Linux capabilities. | sandbox |
| 8  | A model cannot run privileged containers. | sandbox |
| 9  | A model cannot access Docker socket. | sandbox; host (via forbidden-pattern scan); attached (n/a, but `mcp_terminal` itself needs socket access for exec — see H-5) |
| 10 | A model cannot access unrelated projects. | all |
| 11 | Read-only mode prevents writes to `/workspace`. | sandbox |
| 12 | Scratch mode permits writes to `/scratch` but not `/workspace`. | sandbox |
| 13 | Write mode allows writes only in the mounted project. | sandbox |
| 14 | Timeout terminates long-running commands. | all |
| 15 | Output limits truncate large output safely. | all |
| 16 | Container cleanup happens after success, failure, and timeout. | sandbox |
| 17 | Audit record is created for success and failure. | all |

Host-specific invariants (must be covered by tests when `terminal.host_execution.enabled` is true):

- **H-1** Disabled gate rejects all `terminal_run_host` requests with `HOST_EXECUTION_DISABLED` and never queues a job.
- **H-2** Empty allowlist with `enabled=true` produces a startup warning and rejects every `terminal_run_host` request with `HOST_EXECUTION_DISABLED`.
- **H-3** Hard-forbidden executables are rejected even when listed in `allowed_commands`.
- **H-4** Forbidden patterns are rejected in command text, redirection targets, here-string operands, and heredoc bodies.
- **H-5** `docker`, `podman`, `kubectl`, `helm`, `sudo`, `su` are not invocable from `terminal_run_host` regardless of allowlist or path manipulation.
- **H-6** Absolute or `..`-bearing `cwd` is rejected before the host process is spawned.
- **H-7** Host commands cannot read or modify files outside the resolved project root through cwd manipulation alone; symlink escape and traversal are bounded by cwd validation.
- **H-8** A successful host command updates `shell_state.json` cwd; a failed host command does not corrupt `shell_state.json`.
- **H-9** Audit record is produced for every rejected and accepted host request, including the allowlist-snapshot identifier.
- **H-10** `terminal_run_host` and `terminal_run` share the same session and sequence space; sequences are monotonic across both.
- **H-11** The job timeout terminates a runaway host process; `timed_out=true` is recorded.

### 28.8 MVP Acceptance Criteria (host extension to §21)

In addition to §21 sandbox MVP criteria, the host target is feature-complete when:

- `terminal_run_host` appears in MCP `help`.
- `terminal_run_host` rejects every request when `terminal.host_execution.enabled` is `false`.
- `terminal_run_host` rejects every request when `allowed_commands` is empty even if `enabled=true`.
- `terminal_run_host` accepts an allowlisted basename via `argv`.
- `terminal_run_host` accepts a chain of allowlisted segments via `shell`.
- `terminal_run_host` rejects any chain containing a non-allowlisted segment.
- `terminal_run_host` rejects any hard-forbidden executable regardless of allowlist.
- `terminal_run_host` rejects forbidden patterns in command, redirect, here-string, and heredoc.
- `terminal_run_host` writes stdout and stderr to per-seq files identical in shape to sandbox output.
- `terminal_get_status` returns `execution_target: host` after a host command completes.
- Audit record for a host command contains all fields enumerated in §28.6.
- Server startup logs a warning when `enabled=true` and `allowed_commands` is empty.
- A timeout terminates the host process and produces `timed_out=true` in the meta.

### 28.9 Testing Strategy (host extension to §24)

Unit tests, in addition to §24:

- Validator accepts and rejects each item of H-1..H-7 deterministically.
- Decomposer correctly splits `&&`, `||`, `;`, `|` and identifies the leading executable of each segment.
- Forbidden-pattern scanner detects each forbidden substring in command, redirect target, here-string operand, and heredoc body.
- Hard-forbidden executable list takes precedence over allowlist.
- Basename comparison is case-insensitive.
- Absolute path in `argv[0]` is rejected as `HOST_COMMAND_NOT_ALLOWED`, not silently stripped.

Integration tests, in addition to §24:

- `terminal_run_host` returns `HOST_EXECUTION_DISABLED` when `enabled=false`.
- `terminal_run_host` returns `HOST_EXECUTION_DISABLED` when `allowed_commands=[]`.
- A successful `terminal_run_host` followed by `terminal_get_status` shows `execution_target: host`.
- `terminal_run` and `terminal_run_host` interleaved in one session produce a monotonic sequence and a consistent `shell_state.json` cwd.
- An attempt to invoke `docker` via `terminal_run_host` is rejected even after adding `docker` to `allowed_commands` (H-5).
- A host command exceeding `timeout_seconds` is killed and reported as timed-out.
- Audit record for a host command contains `execution_target: host` and the allowlist-snapshot identifier.

### 28.10 Current Code State (extension to §22)

As of this revision, the implementation has extended §22 with the following components that must be preserved and remain part of the system:

Existing code, beyond §22:

```text
mcp_terminal/commands/terminal_run_host_command.py
mcp_terminal/commands/terminal_run_host_metadata.py
mcp_terminal/commands/terminal_run_host_schema.py
mcp_terminal/commands/terminal_kill_command.py
mcp_terminal/commands/terminal_get_session_bootstrap_command.py
mcp_terminal/commands/terminal_list_watch_command.py
mcp_terminal/commands/terminal_purge_sessions_command.py
mcp_terminal/commands/terminal_purge_sessions_metadata.py
mcp_terminal/commands/terminal_purge_sessions_schema.py
mcp_terminal/commands/session_resolve.py

mcp_terminal/config/host_execution_schema.py
mcp_terminal/config/terminal_admin_schema.py
mcp_terminal/config/terminal_defaults_schema.py
mcp_terminal/config/create_config.py

mcp_terminal/services/host_execution_config.py
mcp_terminal/services/host_run_service.py
mcp_terminal/services/host_session_executor.py
mcp_terminal/services/docker_hosts.py
mcp_terminal/services/session_container.py
mcp_terminal/services/session_bootstrap.py
mcp_terminal/services/session_ids.py
mcp_terminal/services/project_registry_refresh.py
mcp_terminal/services/project_roots.py
mcp_terminal/services/project_runtime_image.py
mcp_terminal/services/pid_namespace.py
mcp_terminal/services/running_terminal_jobs.py
mcp_terminal/services/shell_state.py
mcp_terminal/services/terminal_admin_config.py
mcp_terminal/services/terminal_container_purge.py
mcp_terminal/services/terminal_defaults.py
mcp_terminal/services/venv_activation.py

mcp_terminal/jobs/terminal_host_execution_job.py
mcp_terminal/jobs/session_bootstrap_job.py

mcp_terminal/code_analysis_watch.py
mcp_terminal/cli_sessions_purge.py
mcp_terminal/runtime_context.py
mcp_terminal/repo_venv.py
```

MCP commands exposed today (per live `help` of the running `mcp-terminal` server) extend §22 with:

- `terminal_run_host` (host target; this section)
- `terminal_kill` (SIGKILL to a pending sandbox command's docker run client process)
- `terminal_get_session_bootstrap` (status of optional Python env bootstrap queued at session create)
- `terminal_list_watch` (read-only snapshot of project registry by watch anchor)
- `terminal_purge_sessions` (admin: remove all `.terminals` session dirs under watch anchors; gated by `terminal.admin.allow_purge_sessions`)

`docker_hosts.py` is not an attached-target component. It is a sandbox helper that copies `/etc/hosts` Docker-bridge mappings (172.16.0.0/12) into the sandbox container via `docker run --add-host`, so that names of sibling infrastructure containers (proxy, embedding, chunker) resolve from inside the sandbox. Attached-target implementation, when it begins, is a separate work item.

### 28.11 Removal condition for `host`

The `host` target is transitional. It exists because two services currently run on the host: `code-analysis-server` and `mcp_terminal` itself. When both run inside containers, the original motivation for `host` (restart, diagnose, run host-resident tools) is replaced by `attached` against those containers.

This specification does not bind `host` to a calendar date. Removal becomes admissible once **all** of the following hold:

- `code-analysis-server` runs inside a container that is reachable through the `attached` target.
- `mcp_terminal` runs inside a container that is reachable through the `attached` target.
- The functional needs currently served by `host` (restart, diagnostic execution against those containers) are covered by `attached` and by container orchestration controls.

Until that point, `host` remains supported and config-gated as defined above. Once those conditions hold, a future revision of this specification may either remove §28.4 in full or downgrade it to a non-binding compatibility note.

### 28.12 Binding decisions for the execution-target axis

In addition to §26:

1. The execution target axis is a first-class concept of the system. Every execution request belongs to exactly one target.
2. Target is selected by the chosen MCP command, not by a parameter on `terminal_run`. `terminal_run` → `sandbox`, `terminal_run_host` → `host`, future `terminal_run_attached` → `attached`.
3. Session storage, sequence numbering, output store, history file, audit file location, and error contract are shared across targets.
4. Each target carries its own validation policy and execution job class.
5. `sandbox` is always enabled.
6. `host` is off by default and gated by `terminal.host_execution.enabled` plus a non-empty `allowed_commands`.
7. `attached` is reserved, not implemented. No operational behavior is defined for it in this revision beyond the placeholder of §28.5.
8. Authorization for `host` and `attached` is static and config-driven, not per-caller. The trusted operator expresses intent in the server config file.
9. `host` is transitional and is removable under §28.11 conditions.
