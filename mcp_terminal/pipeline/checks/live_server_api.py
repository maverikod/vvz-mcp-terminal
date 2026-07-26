"""Live-server smoke checks for the deployed HTTPS adapter."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request


def _request_json(url: str, *, context: ssl.SSLContext, timeout_seconds: float) -> object:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, context=context, timeout=timeout_seconds) as resp:  # noqa: S310
        return json.load(resp)


def _request_text(url: str, *, context: ssl.SSLContext, timeout_seconds: float) -> str:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, context=context, timeout=timeout_seconds) as resp:  # noqa: S310
        return resp.read(4000).decode("utf-8", errors="replace")


def run_live_server_api_check() -> int:
    """Probe a live deployment when PIPELINE_LIVE_BASE_URL is configured."""
    base_url = os.environ.get("PIPELINE_LIVE_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        print("SKIP live_server_api: set PIPELINE_LIVE_BASE_URL to enable deployed-server checks")
        return 0

    ca_bundle = os.environ.get("PIPELINE_LIVE_CA_CERT", "").strip()
    timeout_seconds = float(os.environ.get("PIPELINE_LIVE_TIMEOUT_SECONDS", "5") or "5")
    expected_version = os.environ.get("PIPELINE_LIVE_EXPECT_VERSION", "").strip()
    allow_legacy_ca = os.environ.get("PIPELINE_LIVE_ALLOW_LEGACY_CA", "").strip() == "1"
    context = ssl.create_default_context(cafile=ca_bundle or None)
    if allow_legacy_ca:
        # Fleet mTLS CAs predate keyUsage/basicConstraints hygiene; Python 3.13+
        # enables VERIFY_X509_STRICT by default and rejects them outright.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if os.environ.get("PIPELINE_LIVE_NO_HOSTNAME_CHECK", "").strip() == "1":
        # Fleet server certs carry Docker DNS names while ops probes dial by IP;
        # server configs ship check_hostname/dnscheck false for the same reason.
        # The chain is still verified against the pinned CA bundle.
        context.check_hostname = False

    try:
        health_body = _request_text(
            f"{base_url}/health",
            context=context,
            timeout_seconds=timeout_seconds,
        )
        openapi = _request_json(
            f"{base_url}/openapi.json",
            context=context,
            timeout_seconds=timeout_seconds,
        )
    except urllib.error.URLError as exc:
        print(f"FAIL live_server_api: {exc}")
        return 1

    if not isinstance(openapi, dict):
        print("FAIL live_server_api: /openapi.json did not return an object")
        return 1

    info = openapi.get("info")
    paths = openapi.get("paths")
    if not isinstance(info, dict):
        print("FAIL live_server_api: OpenAPI info block missing")
        return 1
    if not isinstance(paths, dict):
        print("FAIL live_server_api: OpenAPI paths block missing")
        return 1

    if expected_version:
        actual_version = str(info.get("version", "")).strip()
        if actual_version != expected_version:
            print(
                "FAIL live_server_api: "
                f"expected version {expected_version}, got {actual_version or '<missing>'}"
            )
            return 1

    public_paths = sorted(str(path) for path in paths)
    if "/health" not in public_paths:
        print("FAIL live_server_api: /health missing from OpenAPI")
        return 1
    if len(public_paths) < 2:
        print("FAIL live_server_api: expected more than one published HTTP path")
        return 1

    print(f"health ok: {health_body[:160]}")
    print(f"openapi version: {info.get('version', '')}")
    print(f"openapi paths: {len(public_paths)}")
    return 0
