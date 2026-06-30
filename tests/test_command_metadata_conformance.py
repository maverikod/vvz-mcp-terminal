"""Metadata and schema conformance tests for terminal_* commands."""

from __future__ import annotations

import inspect
import re
from typing import Any, Dict, Set

import pytest

from mcp_terminal.commands.metadata_common import validate_metadata_shape
from mcp_terminal.term_server import _TERMINAL_COMMAND_TYPES


def _execute_param_names(command_cls: type) -> Set[str]:
    source = inspect.getsource(command_cls.execute)
    names = set(re.findall(r"""kwargs\.get\(\s*['"]([^'"]+)['"]""", source))
    names |= set(re.findall(r"""kwargs\[['"]([^'"]+)['"]\]""", source))
    names |= set(re.findall(r"""['"]([^'"]+)['"]\s+in\s+kwargs""", source))
    names.discard("context")
    return names


@pytest.mark.parametrize("command_cls", _TERMINAL_COMMAND_TYPES, ids=lambda c: c.name)
def test_command_schema_shape(command_cls: type) -> None:
    schema = command_cls.get_schema()
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False
    assert isinstance(schema.get("properties"), dict)
    required = schema.get("required", [])
    assert isinstance(required, list)
    for name in required:
        assert name in schema["properties"]


@pytest.mark.parametrize("command_cls", _TERMINAL_COMMAND_TYPES, ids=lambda c: c.name)
def test_schema_properties_match_execute_kwargs(command_cls: type) -> None:
    schema_props = set(command_cls.get_schema()["properties"].keys())
    execute_params = _execute_param_names(command_cls)
    assert schema_props == execute_params, (
        f"{command_cls.name}: schema/execute mismatch "
        f"schema-only={sorted(schema_props - execute_params)} "
        f"execute-only={sorted(execute_params - schema_props)}"
    )


@pytest.mark.parametrize("command_cls", _TERMINAL_COMMAND_TYPES, ids=lambda c: c.name)
def test_metadata_required_fields(command_cls: type) -> None:
    metadata = command_cls.metadata()
    validate_metadata_shape(metadata, command_name=command_cls.name)


@pytest.mark.parametrize("command_cls", _TERMINAL_COMMAND_TYPES, ids=lambda c: c.name)
def test_metadata_parameters_align_with_schema(command_cls: type) -> None:
    schema = command_cls.get_schema()
    metadata = command_cls.metadata()
    schema_props: Dict[str, Any] = schema["properties"]
    schema_required = set(schema.get("required", []))
    meta_params: Dict[str, Any] = metadata["parameters"]
    assert set(meta_params.keys()) == set(schema_props.keys())
    for name, entry in meta_params.items():
        assert entry.get("type") is not None
        assert entry.get("required") is (name in schema_required)


def test_session_scoped_commands_document_casmgr_errors() -> None:
    from mcp_terminal.commands.metadata_common import CASMGR_SESSION_ERROR_CASES

    casmgr_codes = set(CASMGR_SESSION_ERROR_CASES)

    for command_cls in _TERMINAL_COMMAND_TYPES:
        source = inspect.getsource(command_cls.execute)
        if "resolve_session(" not in source:
            continue
        documented = set(command_cls.metadata().get("error_cases", {}))
        missing = casmgr_codes - documented
        assert not missing, f"{command_cls.name} missing casmgr error_cases: {sorted(missing)}"


def test_server_help_metadata_lists_registered_terminal_commands() -> None:
    from mcp_terminal import term_server

    app_config: Dict[str, Any] = {"registration": {"metadata": {}}}
    description = term_server._apply_terminal_server_help_metadata(app_config)
    command_names = [cmd_cls.name for cmd_cls in _TERMINAL_COMMAND_TYPES]

    assert "Available terminal commands:" in description
    for name in command_names:
        assert f"{name}:" in description

    assert app_config["registration"]["description"] == description
    assert app_config["registration"]["version"] == "0.1.31"
    assert app_config["registration"]["metadata"]["version"] == "0.1.31"
    metadata_commands = app_config["registration"]["metadata"]["commands"]
    assert [entry["name"] for entry in metadata_commands] == command_names
