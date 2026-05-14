"""
CLI: `termgr start|stop|status` — manage minimal HTTPS term server process.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import ssl
from pathlib import Path

from mcp_terminal.paths import repo_root
from mcp_terminal.term_config import (
    DEFAULT_TERM_SERVER_LISTEN_PORT,
    default_config_path,
    ensure_term_server_config,
)


def _pid_path() -> Path:
    return repo_root() / "logs" / "term_server.pid"


def _log_path() -> Path:
    return repo_root() / "logs" / "term_server.log"


def _read_server_port(config_path: Path) -> int:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return int(data.get("server", {}).get("port", DEFAULT_TERM_SERVER_LISTEN_PORT))
    except Exception:
        return DEFAULT_TERM_SERVER_LISTEN_PORT


def _ca_bundle_path() -> Path:
    return repo_root() / "mtls_certificates" / "ca" / "ca.crt"


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cmd_start(_args: argparse.Namespace) -> int:
    root = repo_root()
    (root / "logs").mkdir(parents=True, exist_ok=True)
    cfg = ensure_term_server_config()
    pid_file = _pid_path()
    if pid_file.is_file():
        try:
            old = int(pid_file.read_text().strip())
            if _is_pid_alive(old):
                print(f"Already running (pid {old}).")
                return 0
        except ValueError:
            pass
        pid_file.unlink(missing_ok=True)

    log_f = open(_log_path(), "ab", buffering=0)  # noqa: SIM115
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_terminal.term_server",
            "--config",
            str(cfg),
        ],
        cwd=str(root),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_f.close()
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    print(f"Started term_server pid={proc.pid} config={cfg}")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    pid_file = _pid_path()
    if not pid_file.is_file():
        print("Not running (no pid file).")
        return 0
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        print("Removed stale pid file.")
        return 0
    if not _is_pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        print("Not running (stale pid file removed).")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        print("Process already exited.")
        return 0
    for _ in range(30):
        if not _is_pid_alive(pid):
            break
        time.sleep(0.2)
    pid_file.unlink(missing_ok=True)
    print(f"Sent SIGTERM to pid {pid}.")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    pid_file = _pid_path()
    cfg_path = default_config_path()
    port = _read_server_port(cfg_path) if cfg_path.is_file() else DEFAULT_TERM_SERVER_LISTEN_PORT
    host = "127.0.0.1"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            print("Pid file corrupt.")
            return 1
        alive = _is_pid_alive(pid)
        print(f"pid_file: {pid_file}")
        print(f"pid: {pid} alive={alive}")
    else:
        print("pid_file: (none)")
        print("pid: — alive=False")

    ca = _ca_bundle_path()
    ctx = ssl.create_default_context(cafile=str(ca) if ca.is_file() else None)
    url = f"https://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, context=ctx, timeout=3.0) as resp:  # noqa: S310
            body = resp.read(4000).decode("utf-8", errors="replace")
        print(f"health GET {url} -> {body[:200]}")
    except urllib.error.URLError as exc:
        print(f"health GET {url} -> failed: {exc}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="termgr", description="Terminal adapter process manager")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="Ensure config, start term_server in background").set_defaults(
        func=cmd_start
    )
    sub.add_parser("stop", help="SIGTERM term_server from pid file").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="Show pid and probe HTTPS /health").set_defaults(func=cmd_status)
    ns = parser.parse_args()
    code: int = ns.func(ns)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
