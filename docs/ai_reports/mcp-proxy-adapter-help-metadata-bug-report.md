# Bug report: `mcp-proxy-adapter` — `Command.metadata()` not exposed in `help`

**Consumer project:** `mcp_terminal` (server `mcp-terminal`, custom commands via `register_custom_commands_hook`)  
**Adapter package:** `mcp_proxy_adapter` (installed from venv / `site-packages`)  
**Date:** 2026-05-16  
**Reporter:** Vasiliy Zdanovskiy — vasilyvz@gmail.com  

---

## Summary

Downstream servers implement extended AI documentation via a class method `metadata()` (contract aligned with consumer `docs/metadatastd.md`). The adapter’s `help` command with `cmdname` **does not call** `metadata()` and returns only `descr` as `metadata.summary` plus `get_schema()`. MCP clients and the proxy therefore never receive `detailed_description`, usage examples, error cases, or best practices—the reason `metadata()` exists.

---

## Expected behavior

1. If a registered command class defines a callable `@classmethod metadata() -> dict`, `CommandRegistry.get_command_info()` and `HelpCommand` should include that content in the response (full dict or a stable field subset).
2. No consumer-side monkey-patch should be required.
3. The MCP proxy `help` tool should not strip fields already present in the server JSON-RPC response (see **Proxy** below).

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
  "schema": {}
}
```

Optional duplicate top-level `ai_metadata` is acceptable if all fields are merged into `metadata`.

---

## Actual behavior

### 1. `CommandRegistry.get_command_info()` (`_info is None` branch)

File: `mcp_proxy_adapter/commands/command_registry.py` (approx. lines 513–529).

```python
descr = getattr(command_class, "descr", "")
return {
    "metadata": {
        "name": command_name,
        "summary": descr,
        "type": command_type,
    },
    "schema": schema,
}
```

`metadata()` is never checked or invoked.

### 2. `CommandInfo.get_command_info()` (`_info is not None` branch)

File: `mcp_proxy_adapter/commands/registry/command_info.py`.

Returns `name`, `type`, `class`, `module`, `schema`, class attributes—**no** `metadata()`.

### 3. Base `Command` in the adapter

`mcp_proxy_adapter/commands/base.py` does not declare `metadata()`. The contract exists only in consumer documentation; the adapter does not implement it.

### 4. MCP Proxy `help` tool (external)

MCP Proxy `help` with `server_id` + `command: terminal_run` returns mainly **JSON Schema** (`parameters`), without `detailed_description`.

Direct server call `help` + `params: { "cmdname": "terminal_run" }` returns full text only after the consumer workaround (see below); stock adapter returns `metadata.summary` + `schema` only.

---

## Steps to reproduce

1. Register a custom command with `metadata()`:

```python
class MyCommand(Command):
    name = "my_command"
    descr = "Short one line."

    @classmethod
    def metadata(cls) -> dict:
        return {
            "name": cls.name,
            "detailed_description": "Long AI-facing text...",
            "usage_examples": [],
            "error_cases": {},
            "best_practices": [],
        }

    @classmethod
    def get_schema(cls) -> dict:
        return {"type": "object", "properties": {}, "additionalProperties": False}
```

2. JSON-RPC: `help` with `cmdname: "my_command"`.
3. **Observe:** response contains only `metadata.summary == descr`; no `detailed_description` or other metadata fields.

**Reference in `mcp_terminal`:** `terminal_run` — `mcp_terminal/commands/terminal_run_metadata.py`; stock adapter does not surface it.

---

## Impact

| Stakeholder | Effect |
|-------------|--------|
| AI agents (Cursor, MCP) | See one-line `descr` and schema only; miss lifecycle, flags, safety notes |
| Downstream servers | Must patch `CommandRegistry` at startup or duplicate prose in `descr` / schema descriptions |
| Metadata standard | `metadata()` is dead code for `help`/OpenAPI if the adapter ignores it |

---

## Consumer workaround (temporary)

`mcp_terminal/term_server.py` calls `apply_registry_metadata_patch()` on startup (`mcp_terminal/commands/registry_metadata_patch.py`), which wraps `CommandRegistry.get_command_info` and adds:

- `ai_metadata` — full `command_class.metadata()` result
- `metadata.detailed_description`, `usage_examples`, `error_cases`, `best_practices`, `parameters_docs`, `return_value`

Fragile: import order, registry API changes, not reusable by other servers without copy-paste.

---

## Suggested fix (adapter)

1. In **`CommandRegistry.get_command_info()`** (both simple and `CommandInfo` paths), after building the base dict:

```python
if hasattr(command_class, "metadata") and callable(command_class.metadata):
    try:
        ai = command_class.metadata()
        if isinstance(ai, dict) and ai:
            info["ai_metadata"] = ai
            for key in (
                "detailed_description",
                "parameters",
                "return_value",
                "usage_examples",
                "error_cases",
                "best_practices",
                "description",
                "version",
                "category",
            ):
                if key in ai:
                    info["metadata"][key] = ai[key]
    except Exception as e:
        self.logger.warning("metadata() failed for %s: %s", command_name, e)
```

2. **Optional:** declare `@classmethod metadata() -> dict` on base `Command` defaulting to `{}`.

3. **Document** that `help` + `cmdname` is the AI documentation channel; `descr` is the one-line list summary.

4. **MCP Proxy (separate repo, if applicable):** ensure proxied `help` forwards `metadata` / `ai_metadata`, not schema-only `help_info`.

---

## Acceptance criteria

- [ ] `help` + `cmdname` for a command with `metadata()` returns `detailed_description` and `usage_examples` without consumer monkey-patch.
- [ ] Commands without `metadata()` behave as today (`summary` + `schema`).
- [ ] Exceptions in `metadata()` are logged; `help` does not fail (partial info returned).
- [ ] Regression test in `mcp-proxy-adapter`: mock command with `metadata()` → assert fields in `get_command_info`.

---

## Related artifacts (mcp_terminal)

| Item | Path |
|------|------|
| Workaround patch | `mcp_terminal/commands/registry_metadata_patch.py` |
| Patch applied at startup | `mcp_terminal/term_server.py` |
| Example metadata | `mcp_terminal/commands/terminal_run_metadata.py`, `terminal_session_create_metadata.py`, … |
| Metadata standard | `docs/metadatastd.md` |
| Startup log line | `CommandRegistry.get_command_info patched for ai_metadata` |

---

## Verification after fix

```text
call_server(mcp-terminal, help, { "cmdname": "terminal_run" })
```

Response should include `metadata.detailed_description` (multi-paragraph lifecycle text) **without** `apply_registry_metadata_patch()`.
