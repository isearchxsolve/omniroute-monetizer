#!/usr/bin/env python3
"""Bring the whole rig back after anything dies -- a crash, a Chrome loss, or a full reboot.

Why a supervisor at all
-----------------------
This system is five moving parts on four ports, and until now the only thing tying them together was
the operator's memory of which windows had to be open. That is fine until something crashes at 3am.

What actually survives a crash, and what does not, is the important part -- and it is asymmetric:

  * The CHAT pool survives everything. Its supply is `state/secrets/session_*.json`: plain files
    holding a recorded HTTP exchange and a cookie jar. Kill Chrome, kill python, reboot the box, and
    the sessions are exactly as good as they were. This is the entire payoff of capturing to JSON
    instead of driving a live browser.
  * The VIDEO router does NOT survive a Chrome loss. Its supply is live CDP tabs, so a Chrome crash
    destroys it and it has to re-open and re-authenticate tabs. Nothing here can fix that; it can only
    detect it and say so.
  * OmniRoute itself is never touched. See the rule below.

The one rule that is not negotiable
-----------------------------------
**This never restarts, stops, or kills OmniRoute.** It probes it and reports. OmniRoute holds live
OAuth connections whose refresh state is server-side, and bouncing the process to "fix" a bad probe
has previously cost real credentials. A red line in the report is the correct output; a restart is not.
The same applies to the operator's own Chrome: detected, reported, never managed.

Restart policy
--------------
Only processes this repo owns are restarted, identified by their **command line** (not by which port is
occupied -- a port can be somebody else's service, and killing it would be the outage). Restarts are
backed off and capped: a service that will not stay up is reported as broken rather than restarted
forever, because a supervisor in a restart loop is indistinguishable from the fault it is hiding.

Usage
-----
    python omni_supervisor.py --once           # one health snapshot, exit code says if all is well
    python omni_supervisor.py --watch          # supervise: probe, restart what is ours, repeat
    python omni_supervisor.py --up             # start everything missing, then exit
    python omni_supervisor.py --once --json    # machine-readable, for a scheduled task

Writes `state/supervisor_status.json` on every pass. Exit 0 = everything required is up, 1 = something
required is down, 2 = supervisor error.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Optional

try:
    import msvcrt
except ImportError:  # pragma: no cover - Linux/macOS development fallback
    msvcrt = None
try:
    import psutil
except ImportError:  # pragma: no cover - optional diagnostic dependency
    psutil = None

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
LOGS = ROOT / "logs"
STATUS_FILE = STATE / "supervisor_status.json"
AUTHORITATIVE_STATUS_FILE = STATE / "supervisor_status_v2.json"
INSTANCE_LOCK_FILE = STATE / "supervisor.lock"
_INSTANCE_LOCK = None
MEMORY_WARNING_BYTES = 2 * 1024 * 1024 * 1024

PROBE_TIMEOUT_S = 10.0
RESTART_BACKOFF_S = [5, 15, 60, 180]      # then give up and report
SETTLE_AFTER_START_S = 6.0
WATCH_INTERVAL_S = 60.0

# The watch loop runs under pythonw (Startup-folder VBS) or a hidden task console, and every
# subprocess.run below spawns a CONSOLE executable. A console child of a console-less parent makes
# Windows allocate a NEW visible console window -- that is the PowerShell pop the operator saw on
# every pass. CREATE_NO_WINDOW suppresses the allocation for probe children only; the service
# launcher in start() keeps its own flags (DETACHED_PROCESS already hides those).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def acquire_instance_lock() -> bool:
    """Allow one supervisor writer without killing or restarting an incumbent."""
    global _INSTANCE_LOCK
    STATE.mkdir(parents=True, exist_ok=True)
    handle = INSTANCE_LOCK_FILE.open("a+")
    if msvcrt is None:
        _INSTANCE_LOCK = handle
        return True
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except (OSError, IOError):
        handle.close()
        return False
    _INSTANCE_LOCK = handle
    return True


def process_metrics(pid: Optional[int]) -> dict[str, Any]:
    """Return safe process resource metadata without changing the process."""
    if not pid or psutil is None:
        return {}
    try:
        proc = psutil.Process(pid)
        return {"workingSetBytes": int(proc.memory_info().rss),
                "cpuPercent": float(proc.cpu_percent(interval=None))}
    except (OSError, psutil.Error):
        return {}


# --------------------------------------------------------------------------------------------------
# service table
# --------------------------------------------------------------------------------------------------

class Service:
    """One thing that should be running.

    `owned` is the whole safety model. False means this supervisor may look but never touch.
    """

    def __init__(self, key: str, label: str, port: int, health: str, owned: bool,
                 argv: Optional[list] = None, match: str = "", required: bool = True,
                 note: str = ""):
        self.key = key
        self.label = label
        self.port = port
        self.health = health              # URL path to probe, "" = TCP-only check
        self.owned = owned                # may this supervisor start/restart it?
        self.argv = argv or []
        self.match = match                # substring identifying our process on the command line
        self.required = required
        self.note = note
        self.restarts = 0
        self.last_start = 0.0
        self.gave_up = False


def services() -> list:
    py = sys.executable
    auto = str(HERE)
    return [
        Service(
            key="chat_pool", label="Chat pool / superset gateway", port=20130,
            health="/health", owned=True,
            argv=[py, f"{auto}/chat_pool_server.py", "--port", "20130", "--heartbeat-hours", "6"],
            match="chat_pool_server.py",
            note="Free captured sessions, plus forwarding to OmniRoute. Survives reboot: its supply "
                 "is files on disk.",
        ),
        Service(
            key="omniroute", label="OmniRoute chat", port=20128,
            # /v1/models is auth-gated; use the public liveness route so a missing client key is
            # not misreported as a dead OmniRoute process.
            health="/api/health", owned=False, required=False,
            note="NEVER restarted from here. Holds live OAuth connections; bouncing it has cost real "
                 "credentials before. A red line here is a report, not an action. "
                 "The model catalog remains a separate authenticated audit.",
        ),
        Service(
            key="video_router", label="Video router", port=8189,
            health="/healthz", owned=False, required=False,
            note="Owned by the 'OmniRoute Video Router (keepalive)' scheduled task, which relaunches "
                 "it every 5 minutes. Do not fight the task -- it always wins.",
        ),
        Service(
            key="session_pool_shim", label="Session pool shim (chat+video face)", port=8190,
            health="/healthz", owned=False, required=False,
            note="Owned by the 'OmniRoute Session Pool Shim (keepalive)' scheduled task, which "
                 "relaunches it every 5 minutes. Do not fight the task -- it always wins. "
                 "(2026-08-28 worklog #1134: was owned=True here AND owned by the bat task; that "
                 "double ownership is exactly how duplicate shim instances raced onto :8190. "
                 "Single owner now: the bat task. Supervisor probes and reports only.)",
        ),
    ]


# --------------------------------------------------------------------------------------------------
# probing
# --------------------------------------------------------------------------------------------------

def port_listening(port: int) -> Optional[int]:
    """PID listening on the port, or None. Uses netstat because it needs no extra dependency and its
    output is stable across the Windows versions this runs on."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=30,
                             creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (out.stdout or "").splitlines():
        if f":{port} " in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def http_health(port: int, path: str) -> tuple:
    """(ok, payload_or_reason). A non-200 is still a live server, which matters: it means do not
    restart, it means look at the payload."""
    import urllib.error
    import urllib.request
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S) as r:
            raw = r.read().decode("utf-8", "replace")
        try:
            return True, json.loads(raw)
        except ValueError:
            return True, {"raw": raw[:200]}
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}"


def our_process(match: str) -> Optional[int]:
    """PID of a process whose command line contains `match`, or None.

    Matching on the command line rather than the port is deliberate: it is the only way to tell "our
    server is up" from "something else has our port", and those two need opposite responses.
    """
    if not match:
        return None
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | "
          "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60,
                             creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (out.stdout or "").splitlines():
        pid, _, cmd = line.partition("|")
        if match in cmd and pid.strip().isdigit():
            return int(pid.strip())
    return None


def chrome_state() -> dict[str, Any]:
    """Which automation Chromes are alive. Reported, never managed.

    A Chrome loss is the one failure the chat pool does not care about and the video router cannot
    survive, so the report separates them rather than giving one 'chrome ok' flag.
    """
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' } | "
          "ForEach-Object { $_.CommandLine }")
    dirs, debug_ports = [], []
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60,
                             creationflags=NO_WINDOW)
        for line in (out.stdout or "").splitlines():
            m = re.search(r'--user-data-dir=(?:"([^"]+)"|(\S+))', line)
            if m:
                raw = m.group(1) or m.group(2)
                name = pathlib.Path(raw).name
                if name not in dirs:
                    dirs.append(name)
            d = re.search(r"--remote-debugging-port=(\d+)", line)
            if d and d.group(1) not in debug_ports:
                debug_ports.append(d.group(1))
    except (OSError, subprocess.SubprocessError):
        return {"readable": False,
                "note": "could not enumerate chrome.exe; treat Chrome state as unknown"}
    return {
        "readable": True,
        "automationProfiles": dirs,
        "cdpPorts": debug_ports,
        "chatSupplyAffected": False,
        "chatSupplyNote": "chat replay reads session files on disk; a Chrome crash cannot touch it",
        "videoSupplyAffected": not bool(debug_ports),
        "videoSupplyNote": ("video needs live CDP tabs; with no --remote-debugging-port alive there is "
                            "no video supply until tabs are re-opened and re-authenticated"),
    }


def captured_supply() -> dict[str, Any]:
    """The durable asset, counted from disk. This is what actually has to survive a reboot."""
    secrets = STATE / "secrets"
    files = sorted(secrets.glob("session_*.json")) if secrets.exists() else []
    verdicts: dict[str, str] = {}
    vf = STATE / "replay_check.json"
    if vf.exists():
        try:
            d = json.loads(vf.read_text(encoding="utf-8"))
            for r in d.get("results") or []:
                h = str(r.get("host") or "")
                if h and (h not in verdicts or r.get("verdict") == "REPLAY_OK"):
                    verdicts[h] = str(r.get("verdict") or "")
        except (ValueError, OSError):
            pass
    ok = [h for h, v in verdicts.items() if v == "REPLAY_OK"]
    rotated = 0
    for f in files:
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("cookieRotatedAt"):
                rotated += 1
        except (ValueError, OSError):
            pass
    return {
        "captureFiles": len(files),
        "verdictedReplayOk": len(ok),
        "replayOkHosts": sorted(ok),
        "filesWithRotatedCookie": rotated,
        "note": "these files ARE the chat supply; back them up and the pool is portable",
    }


# --------------------------------------------------------------------------------------------------
# passes
# --------------------------------------------------------------------------------------------------

def probe(svc: Service) -> dict[str, Any]:
    pid = port_listening(svc.port)
    row: dict[str, Any] = {
        "service": svc.key, "label": svc.label, "port": svc.port,
        "owned": svc.owned, "required": svc.required, "listening": pid is not None,
        "pid": pid, "note": svc.note,
    }
    if pid is None:
        row["state"] = "DOWN"
        return row
    row.update(process_metrics(pid))
    if svc.health:
        ok, payload = http_health(svc.port, svc.health)
        row["state"] = "UP" if ok else "LISTENING_BUT_UNHEALTHY"
        row["health"] = payload if ok else {"reason": payload}
    else:
        # An unowned service is still safe to interrogate read-only.  TCP presence alone is not
        # application readiness: a hung handler or duplicate instance can hold the port while every
        # client request fails.  Never restart it here; report the application result instead.
        row["state"] = "UP"
        row["health"] = {"probe": "tcp only -- no application path configured"}
    return row


def start(svc: Service) -> bool:
    if not svc.owned:
        return False
    if svc.gave_up:
        return False
    if svc.restarts >= len(RESTART_BACKOFF_S):
        svc.gave_up = True
        log(f"  {svc.key}: giving up after {svc.restarts} restarts -- reporting instead of looping")
        return False
    wait = RESTART_BACKOFF_S[svc.restarts]
    if svc.last_start and (time.time() - svc.last_start) < wait:
        return False
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"{svc.key}.log"
    log(f"  {svc.key}: starting -> {out.name}")
    try:
        with open(out, "ab") as fh:
            fh.write(f"\n--- supervisor start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
                     .encode())
            # New process group: a child that dies with the supervisor defeats the purpose of having
            # one. Same lesson as the Chrome launchers.
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | \
                getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(svc.argv, stdout=fh, stderr=fh, cwd=str(ROOT),
                             creationflags=flags, close_fds=True)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  {svc.key}: start failed -- {type(e).__name__}: {e}")
        return False
    svc.restarts += 1
    svc.last_start = time.time()
    return True


def one_pass(svcs: list, fix: bool) -> dict[str, Any]:
    rows = []
    started = []
    for s in svcs:
        row = probe(s)
        if row["state"] == "DOWN" and s.owned and fix:
            # A port that is listening but is NOT our process is left alone and flagged. Killing it
            # would be a guess about somebody else's service.
            other = row["pid"] is not None and our_process(s.match) is None
            if other:
                row["state"] = "PORT_TAKEN_BY_OTHER"
                row["note"] = (s.note + " | port occupied by a process that is not ours; not touched")
            elif start(s):
                started.append(s.key)
        rows.append(row)
    if started:
        time.sleep(SETTLE_AFTER_START_S)
        rows = [probe(s) for s in svcs]

    required_down = [r["service"] for r in rows
                     if r["required"] and r["state"] not in ("UP",)]
    application_down = [r["service"] for r in rows
                        if r["listening"] and r["state"] == "LISTENING_BUT_UNHEALTHY"]
    resource_warnings = [
        {"service": r["service"], "workingSetBytes": r["workingSetBytes"]}
        for r in rows if r.get("workingSetBytes", 0) >= MEMORY_WARNING_BYTES
    ]
    report = {
        "schemaVersion": 2,
        "statusFile": str(AUTHORITATIVE_STATUS_FILE),
        "writerPid": os.getpid(),
        "writerPython": sys.executable,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "services": rows,
        "startedThisPass": started,
        "requiredDown": required_down,
        "allRequiredUp": not required_down,
        "applicationDown": application_down,
        "allApplicationHealthy": not application_down,
        "resourceWarnings": resource_warnings,
        "chrome": chrome_state(),
        "capturedSupply": captured_supply(),
        "rules": [
            "OmniRoute is never restarted from here -- probe and report only.",
            "The video router belongs to a scheduled task; it relaunches itself every 5 minutes.",
            "The session pool shim belongs to its own scheduled task; probe and report only "
            "(worklog #1134: single owner prevents duplicate :8190 instances).",
            "A port held by a process that is not ours is reported, never killed.",
        ],
    }
    STATE.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2)
    # The versioned artifact is the authoritative read path. Keep updating the legacy filename for
    # older consumers, but do not let an older supervisor overwrite the v2 report.
    AUTHORITATIVE_STATUS_FILE.write_text(encoded, encoding="utf-8")
    STATUS_FILE.write_text(encoded, encoding="utf-8")
    return report


def render(rep: dict[str, Any]) -> None:
    for r in rep["services"]:
        mark = {"UP": "ok  ", "DOWN": "DOWN", "LISTENING_BUT_UNHEALTHY": "SICK",
                "PORT_TAKEN_BY_OTHER": "BUSY"}.get(r["state"], "??  ")
        own = "ours" if r["owned"] else "hands-off"
        req = "" if r["required"] else "  (optional)"
        log(f"  {mark}  :{r['port']:<6} {r['label']:<34} {own}{req}")
    ch = rep["chrome"]
    if ch.get("readable"):
        log(f"  chrome: {len(ch['automationProfiles'])} automation profile(s) alive, "
            f"CDP ports {ch['cdpPorts'] or 'none'}")
        if ch["videoSupplyAffected"]:
            log("          no CDP port alive -> VIDEO supply is down until tabs are re-opened")
        log("          chat supply is unaffected by Chrome state (it reads files, not tabs)")
    cs = rep["capturedSupply"]
    log(f"  supply: {cs['verdictedReplayOk']} REPLAY_OK of {cs['captureFiles']} capture file(s); "
        f"{cs['filesWithRotatedCookie']} carry a rotated cookie")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="one probe, no starting (default)")
    g.add_argument("--up", action="store_true", help="start anything of ours that is missing, exit")
    g.add_argument("--watch", action="store_true", help="supervise continuously")
    ap.add_argument("--interval", type=float, default=WATCH_INTERVAL_S)
    ap.add_argument("--json", action="store_true", help="print the report as JSON only")
    a = ap.parse_args()

    if not acquire_instance_lock():
        log("another supervisor instance owns the report lock; exiting without writing")
        return 0

    svcs = services()
    if a.watch:
        log(f"supervising every {int(a.interval)}s -- Ctrl+C to stop")
        try:
            while True:
                rep = one_pass(svcs, fix=True)
                if not a.json:
                    render(rep)
                else:
                    print(json.dumps(rep))
                time.sleep(a.interval)
        except KeyboardInterrupt:
            log("stopped")
            return 0

    rep = one_pass(svcs, fix=bool(a.up))
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        log("restore check" if not a.up else "bring-up")
        render(rep)
        log(f"status written to {STATUS_FILE.relative_to(ROOT)}")
    return 0 if rep["allRequiredUp"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                       # a supervisor must fail loudly, not silently
        log(f"supervisor error: {type(e).__name__}: {e}")
        sys.exit(2)
