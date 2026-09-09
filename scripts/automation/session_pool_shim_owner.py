"""Exact, WMI-free cleanup for the scheduled :8190 shim owner.

Windows CIM calls have hung inside the keepalive BAT for minutes at a time on
this host.  This helper uses psutil's native process APIs and will kill only a
Python process whose argv contains this repository's exact shim path followed
immediately by the requested port.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Sequence

import psutil


SHIM_SCRIPT = Path(__file__).with_name("session_pool_shim.py").resolve()
PYTHON_NAMES = {"python", "python.exe", "pythonw", "pythonw.exe"}


def _normalise_path(value: str) -> str:
    return os.path.normcase(os.path.abspath(value.strip('"')))


def is_owned_shim_process(
    name: str | None,
    cmdline: Sequence[str] | None,
    port: int,
    *,
    shim_script: Path = SHIM_SCRIPT,
) -> bool:
    """Return True only for this repository's ``session_pool_shim.py PORT``."""

    if not name or name.lower() not in PYTHON_NAMES or not cmdline:
        return False

    target = _normalise_path(str(shim_script.resolve()))
    args = list(cmdline)
    for index, arg in enumerate(args[:-1]):
        try:
            is_script = _normalise_path(arg) == target
        except (OSError, ValueError):
            is_script = False
        if is_script and args[index + 1].strip('"') == str(port):
            return True
    return False


def owned_shim_processes(port: int) -> list[psutil.Process]:
    owned: list[psutil.Process] = []
    current_pid = os.getpid()
    # Asking psutil for ``cmdline`` on every process makes its Windows backend
    # walk every image's command line.  One wedged GUI process can block that
    # query long enough for the task owner's four-second deadline to expire,
    # which leaves a requested code reload unapplied.  Enumerate only the cheap
    # pid/name fields first, then inspect command lines for Python candidates
    # that could possibly be this exact shim.
    for process in psutil.process_iter(("pid", "name")):
        try:
            if process.pid == current_pid:
                continue
            name = process.info.get("name")
            if not name or str(name).lower() not in PYTHON_NAMES:
                continue
            cmdline = process.cmdline()
            if is_owned_shim_process(name, cmdline, port):
                owned.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return owned


def _kill_processes(
    matches: Sequence[psutil.Process], port: int, reason: str
) -> tuple[list[int], list[int]]:
    matched_pids = sorted(process.pid for process in matches)
    for process in matches:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            continue

    _, alive = psutil.wait_procs(matches, timeout=3)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=1)

    remaining = sorted(
        process.pid
        for process in owned_shim_processes(port)
        if process.pid in matched_pids
    )
    for pid in matched_pids:
        print(f"stopped verified {reason} shim pid={pid}", flush=True)
    if remaining:
        print(
            "ERROR exact task-owned shim processes remain: "
            + ",".join(str(pid) for pid in remaining),
            flush=True,
        )
    return matched_pids, remaining


def stop_owned_shims(port: int, reason: str) -> tuple[list[int], list[int]]:
    """Kill every exact launcher/interpreter match and return stopped/remaining PIDs."""

    return _kill_processes(owned_shim_processes(port), port, reason)


def prune_owned_shims(port: int, reason: str) -> tuple[list[int], list[int]]:
    """Keep the exact listening pair and kill only other exact shim processes."""

    matches = owned_shim_processes(port)
    by_pid = {process.pid: process for process in matches}
    listener_pids = {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.status == psutil.CONN_LISTEN
        and connection.pid is not None
        and getattr(connection.laddr, "port", None) == port
    }
    owned_listeners = listener_pids.intersection(by_pid)
    if len(owned_listeners) != 1:
        print(
            "ERROR expected one exact task-owned listener, found "
            f"{sorted(owned_listeners)}",
            flush=True,
        )
        return [], sorted(by_pid)

    keep = set(owned_listeners)
    cursor = by_pid[next(iter(owned_listeners))]
    while True:
        try:
            parent_pid = cursor.ppid()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            break
        parent = by_pid.get(parent_pid)
        if parent is None or parent.pid in keep:
            break
        keep.add(parent.pid)
        cursor = parent

    extras = [process for process in matches if process.pid not in keep]
    if not extras:
        return [], []
    return _kill_processes(extras, port, reason)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--reason",
        choices=("unhealthy", "failed-primary", "healthy-orphan"),
        required=True,
    )
    parser.add_argument(
        "--preserve-listener",
        action="store_true",
        help="keep the exact listener and its exact launcher parent",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    operation = prune_owned_shims if args.preserve_listener else stop_owned_shims
    _, remaining = operation(args.port, args.reason)
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
