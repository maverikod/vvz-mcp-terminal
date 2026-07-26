# MCP Terminal — Docker image and Debian package

Build the production service image, push to Docker Hub, optionally publish sandbox
worker images, and assemble the `mcp-terminal-docker` `.deb` package (same pattern
as `embed` and `svo`).

## Quick start (release build)

From the repository root:

```bash
export MCP_TERMINAL_DOCKERHUB_USERNAME=youruser
export MCP_TERMINAL_DOCKERHUB_TOKEN=...   # optional non-interactive login
./build.sh
```

Output:

- Docker Hub: `<user>/mcp-terminal:<version>` and `:latest`
- Sandbox images (Docker Hub `<user>/mcp-terminal-*`) when not using `--skip-sandbox`
- `docker/dist/mcp-terminal-docker_<version>_amd64.deb`

### Options

| Flag | Effect |
|------|--------|
| `--skip-push` | Build images locally only |
| `--skip-deb` | Skip `.deb` assembly |
| `--skip-sandbox` | Skip sandbox worker image build/push |
| `--dev-run` | After build, start `docker/run.sh` dev container |

Environment:

- `MCP_TERMINAL_DOCKERHUB_REPO` — override image repo (default `<docker-user>/mcp-terminal`)
- `MCP_TERMINAL_SANDBOX_REPO_USER` — Docker Hub user for sandbox repos (default: same as service)
- `MCP_TERMINAL_SANDBOX_IMAGE_*` — override full sandbox image refs (see `docker/sandbox_images.sh`)
- `MCP_TERMINAL_DOCKER_NO_CACHE=1` — pass `--no-cache` to service image build

`build.sh` is the canonical root-level entrypoint for a full release build. It
delegates to `docker/build.sh`, which remains the implementation script.

Build only the `.deb` (image must already exist at the matching tag):

```bash
./docker/build-deb.sh
```

Both root `build.sh` and the underlying `docker/build.sh` plus `build-deb.sh`
always read the version from `pyproject.toml`.
The service image is built and pushed as `<repo>:<version>`, and the Debian
package writes the same reference into `/usr/lib/mcp-terminal/image-spec`.
During install or recreate, `mcp-terminal-docker` pulls that image from Docker
Hub before creating the service container.

Standard flow:

- Run `./build.sh` from a normal user checkout.
- Run `sudo dpkg -i ...` and `sudo apt -f install` on the target host for package installation.
- Run `sudo mcp-terminal-docker recreate` for config or image refreshes that need root-owned Docker mounts.
- Package installs default `server.advertised_host` to `mcp-terminal`, the Docker DNS
  name expected on the shared container network; the service still binds to
  `0.0.0.0` inside the container.

## Install on target host

```bash
sudo dpkg -i docker/dist/mcp-terminal-docker_0.1.0_amd64.deb
sudo apt -f install
mcp-terminal-info
```

`apt -f install` pulls `docker.io | docker-ce`, `adduser`, `python3`, `curl`, etc.

The package:

1. Creates system user/group `mcp-terminal` (adds user to `docker` group)
2. Creates `/etc/mcp-terminal`, `/var/log/mcp-terminal`, `/var/mcp-terminal`
3. Installs `term_server.json` from template and ensures SSH target user via `ensure-ssh-target-user.sh`
4. Normalizes host ownership/modes via `ensure-host-permissions.sh` (mTLS tree group-readable)
5. `docker pull` service image + sandbox worker images
6. Creates and starts container `mcp-terminal` with `docker.sock` and optional SSH known_hosts bind
7. Enables `mcp-terminal-docker.service`

## Host layout

| Path | Purpose |
|------|---------|
| `/etc/mcp-terminal/term_server.json` | Service JSON (created on first install; preserved on upgrade) |
| `/etc/mcp-terminal/ssh_known_hosts` | Pinned SSH host key for `terminal_host_exec` |
| `/usr/lib/mcp-terminal/manage-session-keys.sh` | Ephemeral session key add/remove on host |
| `/etc/mcp-terminal/mtls_certificates/` | TLS material |
| `/etc/default/mcp-terminal` | Port, paths, extra bind mounts |
| `/var/log/mcp-terminal/` | Logs |
| `/var/mcp-terminal/` | Application data |
| `/var/lib/mcp-terminal/` | Package state (uninstall image ref) |

## Operations

```bash
sudo systemctl status mcp-terminal-docker
# After config edits (especially terminal.host_execution):
sudo mcp-terminal-docker recreate    # SSH target user + permission fix run automatically
sudo mcp-terminal-docker status
man mcp-terminal-docker
info mcp-terminal-docker
```

After editing `/etc/mcp-terminal/term_server.json`:

```bash
python3 -m mcp_terminal.config.config_cli validate -c /etc/mcp-terminal/term_server.json
sudo mcp-terminal-docker recreate
```

## Project bind mounts

`watch_dirs` paths must exist on the **host** Docker daemon. Bind the same paths
into the service container via `/etc/default/mcp-terminal`:

```bash
MCP_TERMINAL_EXTRA_BINDS=/home/projects:/home/projects
```

Then `sudo mcp-terminal-docker recreate`.

## Local dev container

```bash
./build.sh --skip-push --skip-deb --skip-sandbox
./docker/run.sh
```

Requires `configs/term_server.json` (create with `termgr create-config`).

## Documentation

- `man mcp-terminal-docker`, `man mcp-terminal-info`, `man mcp-terminal-config`
- `info mcp-terminal-docker`

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
