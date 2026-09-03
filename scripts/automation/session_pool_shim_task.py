"""Console-free scheduled-task owner for the :8190 session-pool shim.

The former VBS -> BAT chain depends on Windows Script Host and CIM process
queries, both of which can block indefinitely on this machine.  This owner uses
only urllib, psutil, and subprocess/CreateProcess.  It is intended to be launched
by the existing scheduled task through the venv's ``pythonw.exe``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

try:
    from .session_pool_shim_owner import prune_owned_shims, stop_owned_shims
except ImportError:
    from session_pool_shim_owner import prune_owned_shims, stop_owned_shims


ROOT = Path(__file__).resolve().parents[2]
SHIM_SCRIPT = Path(__file__).with_name("session_pool_shim.py")
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_DIAG = ROOT / "logs" / "shim_task_diag.log"
DEFAULT_PRIMARY_LOG = ROOT / "logs" / "shim_stdout_current.log"
DEFAULT_REPLACE_REQUEST = ROOT / "state" / "shim_owner_replace.request"
LIVENESS_VERSION = "2026-09-01-liveness-v1"


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{_stamp()}] {message}\n")


def healthz(port: int, timeout: float = 3.0) -> bool:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/healthz")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return (
        payload.get("ok") is True
        and payload.get("service") == "session-pool-shim"
        and payload.get("version") == LIVENESS_VERSION
    )


def wait_for_health(port: int, seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if healthz(port, timeout=min(1.5, max(0.2, deadline - time.monotonic()))):
            return True
        time.sleep(0.25)
    return False


def launch_shim(port: int, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["OMNI_VIDEO_CONFIRM_SPEND"] = "1"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log_path.open("ab", buffering=0) as output:
        process = subprocess.Popen(
            [str(PYTHON_EXE), "-u", str(SHIM_SCRIPT), str(port)],
            cwd=str(ROOT),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creation_flags,
        )
    return process.pid


def request_replace(path: Path) -> None:
    """Atomically ask the registered owner to perform one verified code reload."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(f"requestedAt={_stamp()}\n", encoding="utf-8")
    os.replace(temporary, path)


def consume_replace_request(path: Path) -> bool:
    """Consume one reload marker; a failed reload self-recovers on the next cycle."""

    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def run_owner(
    port: int,
    diag_path: Path,
    primary_log: Path,
    fallback_dir: Path,
    *,
    force_replace: bool = False,
) -> int:
    is_healthy = healthz(port)
    if is_healthy and not force_replace:
        _, remaining = prune_owned_shims(port, "healthy-orphan")
        if remaining:
            _append(diag_path, f"FAILED healthy orphan prune remaining={remaining}")
            return 1
        return 0

    _append(
        diag_path,
        "REPLACE requested native-owner" if force_replace else "PRE-START native-owner",
    )
    _, remaining = stop_owned_shims(port, "unhealthy")
    if remaining:
        _append(diag_path, f"FAILED exact owner cleanup remaining={remaining}")
        return 1

    primary_pid = launch_shim(port, primary_log)
    if wait_for_health(port):
        _, remaining = prune_owned_shims(port, "healthy-orphan")
        if remaining:
            _append(diag_path, f"FAILED primary prune remaining={remaining}")
            return 1
        _append(diag_path, f"RECOVERED primary launcher_pid={primary_pid}")
        return 0

    _append(diag_path, "PRIMARY-UNHEALTHY cleanup-before-fallback")
    _, remaining = stop_owned_shims(port, "failed-primary")
    if remaining:
        _append(diag_path, f"FAILED primary cleanup remaining={remaining}")
        return 1

    fallback_log = fallback_dir / (
        f"shim_stdout_fallback_{time.strftime('%Y%m%dT%H%M%S')}_{os.getpid()}.log"
    )
    fallback_pid = launch_shim(port, fallback_log)
    if wait_for_health(port):
        _, remaining = prune_owned_shims(port, "healthy-orphan")
        if remaining:
            _append(diag_path, f"FAILED fallback prune remaining={remaining}")
            return 1
        _append(
            diag_path,
            f"RECOVERED fallback launcher_pid={fallback_pid} log={fallback_log}",
        )
        return 0

    _append(diag_path, f"FAILED no-healthy-shim log={fallback_log}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8190)
    parser.add_argument("--diag", type=Path, default=DEFAULT_DIAG)
    parser.add_argument("--primary-log", type=Path, default=DEFAULT_PRIMARY_LOG)
    parser.add_argument("--fallback-dir", type=Path, default=ROOT / "logs")
    parser.add_argument(
        "--replace-request", type=Path, default=DEFAULT_REPLACE_REQUEST
    )
    parser.add_argument(
        "--request-replace",
        action="store_true",
        help="write a one-shot marker for the registered owner and exit",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if args.request_replace:
        request_replace(args.replace_request)
        return 0
    try:
        force_replace = consume_replace_request(args.replace_request)
        return run_owner(
            args.port,
            args.diag,
            args.primary_log,
            args.fallback_dir,
            force_replace=force_replace,
        )
    except Exception:
        _append(args.diag, "FAILED owner exception\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
