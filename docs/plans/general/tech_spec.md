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
| Archives | `tar`, `gzip`, `gunzip`, `zip`, `unzip` | Inspect and unpack common local artifacts. |
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
- maximum timeout.

## 14. API Commands

### 14.1 `terminal_run`
Runs one command in a disposable sandbox container.

Request schema draft:

```json
{
  "type": "object",
  "properties": {
    "project_id": {
      "type": "string",
      "description": "Registered project UUID. The server resolves it to a project root."
    },
    "cmd": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Command argv array. Shell is not used by default."
    },
    "cwd": {
      "type": "string",
      "default": ".",
      "description": "Relative working directory inside /workspace."
    },
    "mode": {
      "type": "string",
      "enum": ["read_only", "workspace_write", "scratch_write"],
      "default": "read_only"
    },
    "network": {
      "type": "string",
      "enum": ["none", "restricted"],
      "default": "none"
    },
    "image_profile": {
      "type": "string",
      "description": "Allowlisted runtime image profile."
    },
    "timeout_seconds": {
      "type": "integer",
      "default": 60
    },
    "max_output_bytes": {
      "type": "integer",
      "default": 200000
    }
  },
  "required": ["project_id", "cmd"],
  "additionalProperties": false
}
```

Response draft:

```json
{
  "success": true,
  "data": {
    "run_id": "trun_...",
    "project_id": "...",
    "mode": "read_only",
    "network": "none",
    "image_profile": "python_dev_3_12",
    "cwd": ".",
    "exit_code": 0,
    "timed_out": false,
    "stdout": "...",
    "stderr": "...",
    "stdout_truncated": false,
    "stderr_truncated": false,
    "duration_ms": 1234
  }
}
```

### 14.2 `terminal_get_run_status`

Returns status and metadata for a previous run.

This is required for auditability and for queued/asynchronous execution.

### 14.3 `terminal_get_run_logs`

Returns captured stdout/stderr for a previous run, with truncation and pagination support.

### 14.4 Future: `terminal_session_start`

Starts a reusable sandbox session with TTL.

Not part of MVP unless required.

### 14.5 Future: `terminal_session_exec`

Executes a command inside an existing session.

### 14.6 Future: `terminal_session_close`

Stops and removes a reusable session.

## 15. Execution Lifecycle

MVP lifecycle for `terminal_run`:

1. Validate request schema.
2. Validate semantic constraints.
3. Resolve `project_id` to project metadata.
4. Validate project state and canonical path confinement.
5. Select image from allowlist.
6. Build container create request from server-side policy, not from caller-supplied Docker flags.
7. Mount project according to `mode`.
8. Create disposable container.
9. Execute argv command with timeout.
10. Capture stdout/stderr with byte limits.
11. Collect exit code and timing metadata.
12. Stop and remove container.
13. Persist audit record.
14. Return result.

Containers should be single-use for MVP.

## 16. Audit Requirements

Every run must create an audit record containing:

- `run_id`;
- caller identity if available;
- `project_id`;
- resolved project root hash or redacted path;
- full resolved project path in server-only logs if policy allows;
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
- output truncation flags;
- policy decision summary;
- error code if failed.

Audit logs must avoid recording secret environment values.

## 17. Error Model

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
- stdout/stderr are captured and truncated according to limits.
- Every run has an audit record.
- Result can be verified through `terminal_get_run_status` or equivalent read command.

## 20. Recommended Implementation Phases

### Phase 1: Policy and project resolution

- Implement project lookup by `project_id`.
- Implement canonical path validation.
- Implement image profile allowlist.
- Implement request schema and semantic validation.

### Phase 2: Disposable execution

- Implement `terminal_run` using one container per command.
- Enforce non-root user, fixed `/workspace`, resource limits, network none, no capabilities.
- Capture output and exit code.
- Remove container after execution.

### Phase 3: Audit and read commands

- Persist run records.
- Add `terminal_get_run_status`.
- Add `terminal_get_run_logs` with pagination/truncation.

### Phase 4: Test suite

- Add unit tests for validators.
- Add integration tests for container execution.
- Add negative escape tests.
- Add read-only/write-mode tests.

### Phase 5: Optional sessions

Only after disposable execution is stable:

- Add `terminal_session_start`.
- Add TTL and idle cleanup.
- Add per-project/session quotas.
- Add `terminal_session_exec` and `terminal_session_close`.

## 21. Testing Strategy

Tests must include both normal and hostile cases.

### Unit tests

- Schema validation.
- `project_id` validation.
- Canonical path confinement.
- `cwd` normalization.
- image profile allowlist.
- mode/network policy decisions.

### Integration tests

- Run `python --version` in a sandbox.
- Run `pwd` and verify `/workspace`.
- Run `ls` and verify project files visible.
- Verify read-only mount rejects file creation.
- Verify scratch write allows `/scratch` writes.
- Verify timeout kills `sleep`.
- Verify output truncation.

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

## 22. Operational Defaults

Recommended initial defaults:

```yaml
runtime:
  default_image_profile: python_dev_3_12
  default_mode: read_only
  default_network: none
  timeout_seconds: 60
  max_timeout_seconds: 300
  max_output_bytes: 200000
  memory: 1g
  cpus: 1.0
  pids_limit: 256
  max_concurrent_runs: 4
  cleanup_always: true
```

## 23. Open Questions

1. Which service is the source of truth for `project_id -> project root` lookup?
2. Should paused projects block terminal execution or only background analysis?
3. Which image profiles are required for the first production use case?
4. Should write mode require a separate explicit confirmation flag?
5. Should network access be disabled globally for MVP?
6. Where should audit records be stored?
7. Should stdout/stderr be stored fully on disk or only partially in database?
8. How should file ownership be mapped between container user and host user?
9. Is rootless Docker/Podman required for deployment?
10. Should this server support Windows hosts, or Linux-only initially?

## 24. Initial Recommendation

Start with a conservative MVP:

- one command per disposable container;
- `project_id` only;
- fixed `/workspace` mount;
- default `read_only`;
- default `network: none`;
- no shell mode;
- no sessions;
- no arbitrary images;
- no Docker socket;
- non-root execution;
- hard resource limits;
- full audit trail;
- negative escape tests before declaring the server ready.

This approach keeps the first version simple, testable, and much safer than a long-lived interactive terminal.