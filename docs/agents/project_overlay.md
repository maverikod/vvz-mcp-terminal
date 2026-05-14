<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Project overlay — `mcp_terminal` (this repository)

Repository-specific paths, behavior, and restrictions. Universal layout: [`PROJECT_RULES.md`](../PROJECT_RULES.md) §3 (`LAYOUT-*`).

## Functional context

- **Product:** An **OpenAPI**-described service whose job is to expose, to models, a **shell terminal running inside a container**, with the **end-user project directory bind-mounted** into that container so commands see the same tree the user cares about.
- **MCP path:** Clients (e.g. Cursor) talk to an **MCP proxy**; the proxy forwards tool calls to this service so **LLMs receive terminal access** through the MCP tool surface, not by shelling out on the host IDE machine.
- **Separation:** The **user’s application repo** is data/runtime context (mount target); **this repository** holds the server implementation, ops assets, and agent/rules docs. Keep contract docs (OpenAPI) aligned with what the proxy exposes.
- **What lives here today:** production package [`mcp_terminal/`](../../mcp_terminal/), [`pyproject.toml`](../../pyproject.toml), [`requirements.txt`](../../requirements.txt) / [`requirements-dev.txt`](../../requirements-dev.txt), [`.flake8`](../../.flake8); plus [`.cursor/`](../../.cursor/), [`docs/agents/`](../agents/), [`docs/planning/`](../planning/), optional [`rules_template_agents_protocols_updated.zip`](../../rules_template_agents_protocols_updated.zip). Profile: [`PROJECT_RULES.md`](../PROJECT_RULES.md) §7.
- **Tests:** automated tests under [`tests/`](../../tests/) per **LAYOUT-02**; **non-pytest** harnesses, container smoke scripts, and integration runners under [`scripts/`](../../scripts/) per **LAYOUT-07**.
- **Planning stack (when used):** `docs/plans/` (per [`plan_standard_machine.yaml`](../planning/plan_standard_machine.yaml)) and/or `docs/tech_spec/` for formal work. **Mandatory process:** [`PROJECT_RULES.md`](../PROJECT_RULES.md) **§8** (`PLAN-*`) and `.cursor/rules/planning_workflow.mdc` when those paths are in play.

## Directories and files beyond the universal skeleton

| Path | Note |
|------|------|
| `mcp_terminal/` | Installable Python package (flat layout, no `src/`); depends on **`mcp-proxy-adapter`** (see `pyproject.toml`). |
| `pyproject.toml` | Project metadata, runtime + dev dependencies, `black` / `pytest` / `mypy` tool defaults. |
| `requirements.txt` | Editable install of this repo (`-e .`) for production-like envs. |
| `requirements-dev.txt` | Editable install with `[dev]` extras (pytest, black, flake8, mypy). |
| `mcp_terminal/commands/` | MCP command modules for **mcp-proxy-adapter**; follow **`docs/metadatastd.md`** and **`PROJECT_RULES.md` §9** (`ADP-01`). |
| `docs/metadatastd.md` | Canonical template for command schema + metadata; keep in sync with real command classes. |
| `docs/planning/` | YAML/Markdown standards for tactical and atomic steps (shared with formal agent protocol). |
| `docs/ai_reports/` | Working AI outputs per **LAYOUT-06** (promote finished write-ups into stable `docs/` subtrees). |
| `configs/` | Sample OpenAPI fragments, non-secret defaults, or example mount policies — not production secrets (**LAYOUT-04**). |
| `rules_template_agents_protocols_updated.zip` | Portable rules bundle; README inside describes merge and adaptation checklist. |
| `projectid` (repo root) | **CR-003** identity for this workspace; sample shape in [`projectid.example.json`](../projectid.example.json). |

## Project-specific restrictions

- **Scope:** User project trees arrive as **mounted volumes** inside the service’s containers; do not assume the server repo contains those sources except for local dev fixtures.
- **Safety:** Terminal-in-container features must respect **resource limits**, **working-directory** policy, and **path confinement** relative to the mount (document and enforce in OpenAPI + implementation; avoid “escape the mount” footguns).
- **Secrets:** Do not commit credentials, tokens, or private keys; use **`configs/`** for non-secret samples only (**LAYOUT-04**).
- **Generated indices:** With `USE_CODE_MAP` = `no`, do not introduce `code_analysis/` until §7 enables it and a mapper is wired.

## Filled profile pointer

Concrete profile values for this repo: [`PROJECT_RULES.md`](../PROJECT_RULES.md) **§7**.
