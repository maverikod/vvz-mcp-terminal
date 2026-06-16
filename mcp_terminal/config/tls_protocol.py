"""
TLS protocol helpers for term server config validation and runtime checks.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations


def is_tls_protocol(protocol: str | None) -> bool:
    """True when ``protocol`` uses TLS (``https`` default, or explicit ``mtls``)."""
    return (protocol or "http").lower() in ("https", "mtls")


def effective_protocol(section: dict | None, *, default: str = "https") -> str:
    """Normalized protocol string for a config section."""
    if not isinstance(section, dict):
        return default
    raw = section.get("protocol", default)
    return str(raw).lower() if raw is not None else default
