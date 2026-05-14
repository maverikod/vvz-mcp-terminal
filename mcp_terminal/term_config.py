"""
Materialize and validate the term server SimpleConfig.

The canonical shape lives in ``term_server.defaults.json`` (same layering as
``code_analysis/config.json``: adapter ``SimpleConfig`` sections, registration
URLs and TLS layout aligned with the code-analysis server). Runtime code only
copies that file, applies optional overrides, assigns a fresh ``instance_uuid``,
and runs ``SimpleConfig`` + ``SimpleConfigValidator`` — no parallel hard-coded
registration trees in Python.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from mcp_proxy_adapter.core.config.simple_config import SimpleConfig, SimpleConfigModel
from mcp_proxy_adapter.core.config.simple_config_validator import SimpleConfigValidator

from mcp_terminal.paths import repo_root

_DEFAULTS_PATH = Path(__file__).resolve().parent / "term_server.defaults.json"
DEFAULT_TERM_SERVER_LISTEN_PORT = int(
    json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))["server"]["port"]
)

# PEM / CRT paths in JSON may be relative to the config file (``configs/``).
# Adapter startup checks also resolve some paths from process CWD; rewriting
# relative TLS paths to absolute avoids "Referenced file not found" when cwd
# is the repo root.
_SSL_PATH_KEYS = ("cert", "key", "ca", "crl")


def normalize_tls_paths_in_term_config(config_path: Path) -> None:
    """
    If ``server`` / ``client`` / ``registration`` / ``server_validation`` contain
    relative ``ssl`` paths, rewrite them to absolute paths using ``config_path``'s
    directory as the base (same base ``SimpleConfigValidator`` uses).
    """
    config_path = config_path.resolve()
    base = config_path.parent
    data = json.loads(config_path.read_text(encoding="utf-8"))
    changed = False

    def rewrite_ssl(ssl: Any) -> None:
        nonlocal changed
        if not isinstance(ssl, dict):
            return
        for key in _SSL_PATH_KEYS:
            raw = ssl.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            candidate = Path(raw.strip())
            if candidate.is_absolute():
                continue
            resolved = (base / candidate).resolve()
            if not resolved.is_file():
                continue
            new_s = str(resolved)
            if new_s != raw:
                ssl[key] = new_s
                changed = True

    for section in ("server", "client", "registration", "server_validation"):
        block = data.get(section)
        if isinstance(block, dict):
            rewrite_ssl(block.get("ssl"))

    if changed:
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def default_config_path() -> Path:
    """Path to the runtime SimpleConfig JSON (usually gitignored)."""
    return repo_root() / "configs" / "term_server.json"


def ensure_code_analysis_mtls_layout_symlinks(root: Path) -> None:
    """
    Ensure ``mtls_certificates/mtls_certificates/{client,ca}/`` exists like code_analysis.

    Symlinks point at the flat ``mtls_certificates/client/mcp-proxy.*`` and ``ca/ca.crt``
    so paths in ``term_server.defaults.json`` resolve from ``configs/``.
    """
    nested = root / "mtls_certificates" / "mtls_certificates"
    client = nested / "client"
    ca_dir = nested / "ca"
    client.mkdir(parents=True, exist_ok=True)
    ca_dir.mkdir(parents=True, exist_ok=True)
    flat_client = root / "mtls_certificates" / "client"
    flat_ca = root / "mtls_certificates" / "ca" / "ca.crt"
    for name in ("mcp-proxy.crt", "mcp-proxy.key"):
        target = client / name
        if (flat_client / name).is_file() and not target.exists() and not target.is_symlink():
            target.symlink_to(Path("..") / ".." / "client" / name)
    ca_link = ca_dir / "ca.crt"
    if flat_ca.is_file() and not ca_link.exists() and not ca_link.is_symlink():
        ca_link.symlink_to(Path("..") / ".." / "ca" / "ca.crt")


def load_validated_term_simple_config(path: Path) -> tuple[SimpleConfig, SimpleConfigModel]:
    """Load ``path`` as ``SimpleConfig`` and validate with ``SimpleConfigValidator``."""
    path = path.resolve()
    normalize_tls_paths_in_term_config(path)
    p = str(path)
    simple_config = SimpleConfig(p)
    model = simple_config.load()
    errors = SimpleConfigValidator(config_path=p).validate(model)
    if errors:
        lines = "\n".join(f"  - {e.message}" for e in errors)
        raise ValueError(f"Invalid term server config {path}:\n{lines}")
    simple_config.model = model
    return simple_config, model


def validate_term_server_config(path: Path) -> None:
    """Run ``load_validated_term_simple_config`` for side effect (raise on invalid)."""
    load_validated_term_simple_config(path)


def ensure_term_server_config(
    *,
    host: str | None = None,
    port: int | None = None,
    tls_cert_pem: str | None = None,
    ca_cert: str | None = None,
) -> Path:
    """
    If ``configs/term_server.json`` is missing, copy ``term_server.defaults.json``,
    set ``registration.instance_uuid``, optional ``server.host`` / ``server.port`` /
    ``server.ssl`` overrides, then validate.

    Always validates the file at the end (same idea as ``code_analysis`` loading +
    ``CodeAnalysisConfigValidator`` / ``SimpleConfigValidator``).
    """
    root = repo_root()
    ensure_code_analysis_mtls_layout_symlinks(root)
    path = default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.is_file():
        data: dict[str, Any] = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
        reg = data.setdefault("registration", {})
        reg["instance_uuid"] = str(uuid.uuid4())
        if host is not None:
            data["server"]["host"] = host
        if port is not None:
            data["server"]["port"] = int(port)
        if tls_cert_pem:
            pem = str(Path(tls_cert_pem))
            data["server"].setdefault("ssl", {})
            data["server"]["ssl"]["cert"] = pem
            data["server"]["ssl"]["key"] = pem
        if ca_cert:
            data["server"].setdefault("ssl", {})
            data["server"]["ssl"]["ca"] = str(Path(ca_cert))
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    validate_term_server_config(path)
    return path
