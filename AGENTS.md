# mcp-terminal - Codex operating contract

**Prompts template:** `codex-prompts-v1` rev **1.6.12** (2026-07-31)

This file is the Codex entrypoint. The root must read these files itself at the
start of a task:

- `codex/roles/common.yaml`
- `codex/roles/laws.yaml`
- `codex/roles/orchestrator.yaml`

Do not delegate reading or interpretation of those files. Resolve every
relative prompt-package reference against `codex/`.

- This contract is `AGENTS.md` plus `codex/` only; Claude and historical role packs do not govern.
- Role names are stages, not required agent types: a missing spawn type is never a blocker.
- One home project owns the session. Its deploy host is ordinary development scope for that project's
  own service, including root access; every other project is read-only — see `laws.project_boundary`.

## Project profile

- Project: `mcp-terminal`
- Local checkout: `/home/vasilyvz/projects/tools/mcp_terminal`
- Default file-access profile: `local` (only the user may switch it).
- Deployment host: `root@192.168.254.26`.
- CAS project ID: `37382ce3-beff-4161-9ddf-362d0460ccf3`
- CAS server: `code-analysis-server-vvz`

Use the `codex/` bundle as the authoritative Codex contract for this project.
Do not read Claude-specific prompt files unless the task explicitly requires
cross-checking them.
