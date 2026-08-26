#!/usr/bin/env python3
"""Make the supervisor survive a reboot -- register it as a logon task, or show the command and stop.

The gap this closes
-------------------
omni_supervisor.py brings the rig back after a crash, but only while it is itself running. After a
full reboot nothing starts it, so "complete reboot recovery" is only real once the supervisor launches
at logon. This registers that one Windows Scheduled Task and nothing else.

What it deliberately does NOT do
--------------------------------
  * It does not touch OmniRoute or the video router. The supervisor it launches already treats both as
    hands-off (OmniRoute is never restarted; the video router has its own 5-minute keepalive task that
    always wins). This installer only arranges for the supervisor to run; the supervisor's own safety
    model is unchanged.
  * It does not launch Chrome. Video seats need a signed-in Chrome, and auto-launching Chrome against a
    real profile is the one move that has cost a Google session before (DBSC). Bringing video seats
    back after a reboot stays a deliberate operator step. The CHAT pool -- whose supply is files on
    disk -- comes back fully and automatically; that asymmetry is inherent, not a shortcoming here.

Safety
------
Default is a DRY RUN: it prints the exact schtasks command and changes nothing. `--install` registers
the task (Task Scheduler, needs elevation); `--startup` arms the same watch loop with no elevation via
a Startup-folder .vbs launcher; `--uninstall` removes both; `--status` reports whether either is armed.
Both mechanisms are fully reversible (`--uninstall`, Task Scheduler, or deleting the .vbs), which is
why arming is a normal action rather than a one-way door.

    python install_autostart.py                 # show the command, change nothing (default)
    python install_autostart.py --install        # register the logon task (Task Scheduler; needs elevation)
    python install_autostart.py --startup        # arm via a Startup-folder launcher (no elevation)
    python install_autostart.py --status
    python install_autostart.py --uninstall
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SUPERVISOR = HERE / "omni_supervisor.py"
TASK_NAME = "OmniRoute Rig Supervisor"
STARTUP_DIR = pathlib.Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_VBS = STARTUP_DIR / "omniroute_rig_supervisor.vbs"


def _task_command() -> str:
    """The command the task runs at logon: the supervisor's continuous watch loop.

    pythonw (no console) is preferred so a logon task does not flash a window; falls back to python.
    The watch loop re-probes every interval and restarts only what the supervisor owns (the chat
    pool), backing off and giving up rather than looping -- so a task that fires once at logon is
    enough, no /RI restart spam needed.
    """
    exe = sys.executable
    pyw = pathlib.Path(exe).with_name("pythonw.exe")
    runner = str(pyw) if pyw.exists() else exe
    return f'"{runner}" "{SUPERVISOR}" --watch'


def _schtasks_create_argv() -> list:
    return [
        "schtasks", "/Create", "/TN", TASK_NAME,
        "/TR", _task_command(),
        "/SC", "ONLOGON",
        "/RL", "LIMITED",           # no elevation: the rig runs as the normal user, same as by hand
        "/F",                        # overwrite an existing task of the same name
    ]


def _vbs_quote(s: str) -> str:
    """Quote a string as a VBScript double-quoted literal (an embedded quote is doubled)."""
    return '"' + s.replace('"', '""') + '"'


def _startup_vbs_body() -> str:
    """A Startup-folder .vbs that launches the supervisor watch loop hidden -- no admin, no window flash.

    This is the no-elevation sibling of the scheduled task. Writing a file into the user's own Startup
    folder needs no rights beyond the user's, and it matches the omniroute *.vbs launchers this machine
    already keeps there. pythonw is windowless on its own; the WScript.Shell.Run style 0 is belt-and-
    suspenders so nothing flashes. Delete the file (or --uninstall) to disarm.
    """
    exe = sys.executable
    pyw = pathlib.Path(exe).with_name("pythonw.exe")
    runner = str(pyw) if pyw.exists() else exe
    cmd = f'"{runner}" "{SUPERVISOR}" --watch'
    return (
        "' OmniRoute Rig Supervisor -- no-admin logon autostart (Startup-folder launcher).\r\n"
        "' Launches the supervisor watch loop hidden at every logon. Delete this .vbs to disarm.\r\n"
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f"sh.Run {_vbs_quote(cmd)}, 0, False\r\n"
    )


def _run(argv: list) -> tuple:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, f"{type(e).__name__}: {e}"


def status() -> int:
    armed = False
    code, out = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"])
    if code == 0:
        armed = True
        print(f"scheduled task  : registered '{TASK_NAME}'")
        for line in out.splitlines():
            s = line.strip()
            if s.startswith(("Task To Run", "Schedule Type", "Status", "Next Run Time", "Last Run Time")):
                print(f"    {s}")
    else:
        print(f"scheduled task  : not registered  (arm with --install; needs elevation)")
    if STARTUP_VBS.exists():
        armed = True
        print(f"startup launcher: present  -> {STARTUP_VBS}")
    else:
        print(f"startup launcher: absent   (arm with --startup; no elevation)")
    if not armed:
        print("reboot recovery is NOT armed.")
    return 0 if armed else 1


def install() -> int:
    if not SUPERVISOR.is_file():
        print(f"cannot find {SUPERVISOR} -- refusing to register a task that points at nothing")
        return 2
    argv = _schtasks_create_argv()
    print("registering logon task:")
    print("  " + " ".join(argv))
    code, out = _run(argv)
    print(out.strip())
    if code == 0:
        print(f"\nok. '{TASK_NAME}' will start the supervisor at every logon.")
        print("verify:  python install_autostart.py --status")
        print("it starts now on next logon; to start it this session without logging out:")
        print(f'  {_task_command()}')
        return 0
    print(f"\nschtasks failed (exit {code}). If it says access denied, this user cannot create tasks; "
          f"run the command yourself from an elevated shell, or use --startup (no elevation).")
    return 1


def install_startup() -> int:
    """Arm reboot recovery with no elevation: write a hidden launcher into the user's Startup folder."""
    if not SUPERVISOR.is_file():
        print(f"cannot find {SUPERVISOR} -- refusing to write a launcher that points at nothing")
        return 2
    if not STARTUP_DIR.is_dir():
        print(f"Startup folder not found: {STARTUP_DIR} -- is %APPDATA% set?")
        return 2
    try:
        STARTUP_VBS.write_text(_startup_vbs_body(), encoding="utf-8")
    except OSError as e:
        print(f"could not write {STARTUP_VBS}: {e}")
        return 1
    print(f"armed (no elevation): {STARTUP_VBS}")
    print(f"  runs at logon: {_task_command()}")
    print("verify:  python install_autostart.py --status")
    print("disarm:  python install_autostart.py --uninstall   (or delete that .vbs)")
    print("start it this session without logging out:")
    print(f"  {_task_command()}")
    return 0


def uninstall() -> int:
    """Disarm both mechanisms. Best-effort: removes whichever is present, reports the other as absent."""
    code, out = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    msg = out.strip()
    if code == 0:
        print(msg or f"removed scheduled task '{TASK_NAME}'")
    else:
        print(f"scheduled task  : nothing removed ({msg or 'not registered'})")
    if STARTUP_VBS.exists():
        try:
            STARTUP_VBS.unlink()
            print(f"startup launcher: removed {STARTUP_VBS}")
        except OSError as e:
            print(f"startup launcher: could not remove {STARTUP_VBS}: {e}")
    else:
        print(f"startup launcher: nothing removed ({STARTUP_VBS})")
    return 0


def dry_run() -> int:
    print("DRY RUN -- nothing changed.\n")
    print(f"task name : {TASK_NAME}")
    print(f"trigger   : ONLOGON (starts when this user logs in)")
    print(f"runs      : {_task_command()}")
    print(f"working   : {ROOT}")
    print("\nthe command that --install would run:")
    print("  " + " ".join(_schtasks_create_argv()))
    print("\nthis registers ONE task that launches the supervisor's watch loop at logon. The")
    print("supervisor restarts only the chat pool (its own process); OmniRoute and the video router")
    print("are never touched, and Chrome is never launched. Run with --install to register it.")
    print(f"\nno-elevation alternative: --startup writes a hidden launcher to your Startup folder")
    print(f"  ({STARTUP_VBS}) -- same watch loop at logon, no admin required.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--install", action="store_true", help="register the logon task (Task Scheduler; needs elevation)")
    g.add_argument("--startup", action="store_true", help="arm via a Startup-folder .vbs launcher (no elevation)")
    g.add_argument("--uninstall", action="store_true", help="remove both the task and the startup launcher")
    g.add_argument("--status", action="store_true", help="report whether reboot recovery is armed")
    a = ap.parse_args()
    if a.install:
        return install()
    if a.startup:
        return install_startup()
    if a.uninstall:
        return uninstall()
    if a.status:
        return status()
    return dry_run()


if __name__ == "__main__":
    sys.exit(main())
