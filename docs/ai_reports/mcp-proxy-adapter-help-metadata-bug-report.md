# Bug report: `mcp-proxy-adapter` — `Command.metadata()` not exposed in `help`

**Status:** **Fixed in `mcp-proxy-adapter` 8.10.13** (2026-05-16)  
**Consumer project:** `mcp_terminal` (server `mcp-terminal`)  
**Affected versions:** `8.10.12` and earlier (simple `get_command_info` path ignored `metadata()`)  
**Fixed version:** **`>= 8.10.13`** — see `mcp_proxy_adapter/commands/command_help_info.py`  
**Reporter:** Vasiliy Zdanovskiy — vasilyvz@gmail.com  

---

## Resolution (8.10.13)

Adapter now builds help via `build_command_help_payload()` / `merge_command_metadata_into_help_payload()`:

- Calls `command_class.metadata()` when present.
- Merges `detailed_description`, `parameters`, `return_value`, `usage_examples`, `error_cases`, `best_practices`, etc. into `metadata`.
- Sets top-level `ai_metadata` to the full `metadata()` dict.
- Sets `parameters_docs` alias when `parameters` is present (same as the former consumer patch).

`mcp_terminal` depends on **`mcp-proxy-adapter>=8.10.13,<9`** (`pyproject.toml`). The local monkey-patch `registry_metadata_patch.py` was **removed** as redundant.

**Verify:**

```text
call_server(mcp-terminal, help, { "cmdname": "terminal_run" })
```

Expect `metadata.detailed_description` and `ai_metadata` without any consumer-side registry patch.

---

## Original summary (8.10.12)

Downstream servers implement extended AI documentation via `metadata()` (`docs/metadatastd.md`). In **8.10.12**, `help` + `cmdname` returned only `descr` as `metadata.summary` plus `get_schema()`. MCP clients did not receive `detailed_description`, usage examples, error cases, or best practices.

---

## Expected behavior

1. Callable `@classmethod metadata() -> dict` on a command class is merged into `help` + `cmdname`.
2. No consumer monkey-patch required (**met in 8.10.13**).
3. MCP proxy `help` should forward full server payload (separate proxy ticket if still schema-only).

Target shape for `help` + `cmdname`:

```json
{
  "metadata": {
    "name": "terminal_run",
    "summary": "<short descr>",
    "type": "custom",
    "detailed_description": "...",
    "parameters": {},
    "return_value": {},
    "usage_examples": [],
    "error_cases": {},
    "best_practices": []
  },
  "schema": {},
  "ai_metadata": {}
}
```

---

## Actual behavior in 8.10.12 (historical)

### `CommandRegistry.get_command_info()` (`_info is None`)

Returned only:

```python
{
    "metadata": {"name": ..., "summary": descr, "type": ...},
    "schema": schema,
}
```

### Other gaps (8.10.12)

- `CommandInfo.get_command_info()` did not call `metadata()`.
- Base `Command` had no `metadata()` hook in the adapter.
- MCP Proxy `help` tool often exposed schema only (proxy layer).

---

## Steps to reproduce (8.10.12 only)

1. Install `mcp-proxy-adapter==8.10.12`.
2. Register a command with `metadata()` returning `detailed_description`, etc.
3. `help` + `cmdname` → no `detailed_description` in response.

---

## Impact (before fix)

| Stakeholder | Effect |
|-------------|--------|
| AI agents | One-line `descr` + schema only |
| Downstream servers | Required registry monkey-patch or duplicated prose |
| Metadata standard | `metadata()` unused for `help` |

---

## Former consumer workaround (removed)

`mcp_terminal` previously called `apply_registry_metadata_patch()` at startup (`commands/registry_metadata_patch.py`), duplicating logic now in adapter `command_help_info.py`. **Removed** after pinning `>=8.10.13`.

---

## Suggested fix (implemented in 8.10.13)

Adapter module: `mcp_proxy_adapter/commands/command_help_info.py`

- `build_command_help_payload()` — schema + summary + merge.
- `merge_command_metadata_into_help_payload()` — `metadata()`, `ai_metadata`, `_METADATA_MERGE_KEYS`.

`get_command_info` and `get_all_commands_info` (simple path) both use `build_command_help_payload`.

---

## Acceptance criteria

- [x] `help` + `cmdname` returns `detailed_description` without consumer patch (**8.10.13**).
- [x] Commands without `metadata()` unchanged (**8.10.13**).
- [x] `metadata()` exceptions logged, `help` does not fail (**8.10.13**).
- [ ] Regression test in `mcp-proxy-adapter` (recommended upstream).
- [ ] MCP Proxy forwards full `metadata` / `ai_metadata` (if still open).

---

## Related artifacts (mcp_terminal)

| Item | Path |
|------|------|
| Metadata modules | `mcp_terminal/commands/terminal_run_metadata.py`, `terminal_session_create_metadata.py`, … |
| Dependency pin | `pyproject.toml` → `mcp-proxy-adapter>=8.10.13,<9` |
| Metadata standard | `docs/metadatastd.md` |
| Removed workaround | ~~`registry_metadata_patch.py`~~ (deleted) |
