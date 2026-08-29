#!/usr/bin/env python3
"""Master three-step graduation pass over every eligible seat: capture -> replay -> graduate.

This is the orchestrator for the mandate. It does NOT reimplement any of the three steps; it drives
the tools that already exist, in the order that makes their guarantees hold, and records a resumable
ledger so a 70-tab pass can be stopped and restarted without redoing work or double-spending a seat.

    Step 1  CAPTURE    tab_graduation_sweep.py --execute --site "<name>"   (captures AND replays)
    Step 2  VERDICT    read that unit's scratch report -- NOT a second replay (see below)
    Step 3  GRADUATE   regenerate the canonical gate, restart :20130, confirm /health lists the host

ONE SEAT, ONE REQUEST
---------------------
`tab_graduation_sweep.py --execute` already performs both the capture and the verifying replay. An
orchestrator that then ran its own replay would send a second live request to the same free account for
one seat's worth of information -- double-spending somebody else's quota to learn what the first request
already established. So step 2 does not send anything: it reads the per-seat report the sweep wrote.

Why it wraps instead of reimplements
------------------------------------
`tab_graduation_sweep.py` already refuses any CDP listener whose Chrome is not running under
`state/automation_profiles`, and it is deliberately serial: one seat, one CDP target, one provider
request at a time. Those are the properties that keep this from touching the operator's live Chrome --
which once permanently revoked their Google session. Driving CDP from here would discard them. So this
script never opens a CDP connection, never types, never submits; it shells out one unit at a time.

THE HAZARD THIS SCRIPT EXISTS TO AVOID
--------------------------------------
`replay_check.py --only <host>` filters the session list and then writes the report ATOMICALLY OVER
`state/replay_check.json`. That file is the gate `chat_pool_server.py` reads at startup to decide which
seats to serve. So verifying one seat with the default `--out` would truncate the gate to a single row,
and the next restart would drop the chat pool from 7 seats to 1. Per-seat verification therefore always
goes to a scratch path, and the canonical gate is regenerated exactly once, at the end, from a FULL run.
The scratch path is imported from the sweep rather than recomputed, so the writer and the reader cannot
drift apart -- if they did, this script would read a stale verdict and graduate a seat that never passed.

WHY STEP 3 IS A RESTART
-----------------------
`chat_pool_server.py` reads the gate once at startup and caches it. A graduated seat is invisible until
:20130 restarts -- 5 graduated seats sat unused for exactly this reason. Writing the seat into
`session_pool.py` is not the step that matters; reloading the server is. :20130 is ours and may be
restarted. **:20128 is OmniRoute's and must never be touched.**

WALLS ARE NEVER RETRIED
-----------------------
A CAPTCHA, payment, phone, plan or quota wall is not a transport error. Retrying it is hammering a free
account someone else owns, and it is how a seat gets burned. A wall is recorded once and the seat is
skipped for good unless `--retry-walls` is passed explicitly.

AND NEITHER IS A REPEATED FAILURE
---------------------------------
Two identical failures for one seat ends that seat's attempts for this run. A third identical attempt
has never once produced a different result in this project's history; it only spends. This rule exists
because ~40 identical retries of one failing call is what burned a day of budget.

VIDEO SEATS ARE A SEPARATE LANE
-------------------------------
The manifest classifies some tabs `VIDEO_SEPARATE_GRADUATION`. Those are NOT graduated here: a video
capture costs clips (the spend gate), and a video seat must never land in the chat pool -- a chat outage
and a video outage fail differently, and one process makes one look like the other. They are listed and
skipped. `--video-lane` prints the ordered work list for the harvester and still refuses to capture.

Also note every jar on disk carries `modality: "chat"` -- including veoaifree.com, a video site. That
field records what a seat was PROBED for, not what it can do. See probe_video_entitlement.py.

    python scripts/automation/graduate_all_seats.py                      # plan only, sends nothing
    python scripts/automation/graduate_all_seats.py --apply
    python scripts/automation/graduate_all_seats.py --apply --limit 5
    python scripts/automation/graduate_all_seats.py --apply --only "Zhipu GLM Chat"
    python scripts/automation/graduate_all_seats.py --video-lane
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable

sys.path.insert(0, str(HERE))
# Import, don't recompute: the sweep decides where a per-seat verdict lands, and this script reads it
# back. Two copies of that path is one rename away from graduating a seat on a stale report.
from tab_graduation_sweep import scratch_report  # noqa: E402

SWEEP = HERE / "tab_graduation_sweep.py"
REPLAY = HERE / "replay_check.py"
POOL_SERVER = HERE / "chat_pool_server.py"

MANIFEST = ROOT / "state" / "tab_graduation_manifest.json"
GATE = ROOT / "state" / "replay_check.json"          # canonical -- only ever written by a FULL run
SCRATCH = ROOT / "state" / "scratch"                 # per-seat reports; path owned by the sweep
LEDGER = ROOT / "state" / "graduation_ledger.json"
WORKLOG = ROOT / "MASTER_WORKLOG.md"

POOL_HEALTH = "http://127.0.0.1:20130/health"
POOL_PORT = 20130

# --- D1 hardening (2026-08-29, worklog #1157/#1158) --------------------------
# Run 3 completed every capture and rebuilt the canonical gate, then died after
# the pool restart and BEFORE save_ledger()/append_worklog(): 31 seats of
# verdicts existed only in a stdout buffer that was lost on kill, and the ledger
# kept run 1 forever. Four independent defences, all load-bearing:
#   * INSTANCE_LOCK  -- one --apply at a time. (The run-3 "two processes" were
#     one venv-launcher pair -- see worklog #1157 -- so the real hazard is a
#     second concurrent run, which WOULD double-spend free seats.)
#   * restart_pool_bounded -- step 3 gets a hard wall-clock ceiling so a wedged
#     /health or Start-Process can never park the run again.
#   * finally: save_ledger + append_worklog -- the ledger and the worklog are
#     written no matter how the run dies, and every run's verdict table is also
#     copied into ledger["runs"] so the data survives even a lost log.
#   * line-buffered stdout under --apply -- a killed run leaves an honest log
#     tail instead of silently losing the last buffered block.
INSTANCE_LOCK = ROOT / "state" / "graduate_all_seats.lock"
RESTART_DEADLINE_S = 180      # hard ceiling on the whole step-3 restart
# The system proxy intercepts loopback on this machine (TECHNOLOGY_TRANSFER §1);
# the /health probe must never route through it.
_HEALTH_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _pid_alive(pid: int) -> bool:
    """Windows liveness probe. os.kill(pid, 0) is NOT safe here: on Windows any
    signal other than the CTRL_* events terminates the target process."""
    if pid <= 0:
        return False
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    except Exception:
        return True  # cannot tell -- assume alive and refuse a second run (fail closed)
    if not handle:
        return False
    k32.CloseHandle(handle)
    return True


def acquire_instance_lock() -> tuple[bool, str]:
    """Single-instance guard for --apply. A stale lock (owner dead) is taken over."""
    if INSTANCE_LOCK.exists():
        try:
            stale_pid = int(INSTANCE_LOCK.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            stale_pid = 0
        if _pid_alive(stale_pid):
            return False, (f"another graduate_all_seats.py --apply appears to be running "
                           f"(pid {stale_pid}, lock {INSTANCE_LOCK.name}); if that is wrong, "
                           f"delete the lock file")
        print(f"  stale instance lock (pid {stale_pid} is gone) -- taking over", flush=True)
    INSTANCE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    INSTANCE_LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True, "acquired"


def release_instance_lock() -> None:
    try:
        if INSTANCE_LOCK.exists() and \
                INSTANCE_LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
            INSTANCE_LOCK.unlink()
    except OSError:
        pass


CAPTURE_TIMEOUT_S = 240
REPLAY_TIMEOUT_S = 180
SEAT_DELAY_S = 4.0          # breadth, not depth: never come back to a provider immediately
MAX_ATTEMPTS = 2            # a third identical attempt has never changed the answer

# A wall is somebody else's boundary. Recorded once, never knocked on again.
WALL_MARKS = (
    "captcha", "recaptcha", "hcaptcha", "turnstile", "cloudflare",
    "payment", "billing", "upgrade your plan", "subscribe", "subscription required",
    "phone", "verify your", "verification required",
    "quota", "out of credits", "insufficient", "limit reached", "too many requests",
    "429", "rate limit", "plan required", "trial expired",
)
AUTH_MARKS = ("401", "403", "unauthorized", "unauthenticated", "session expired", "sign in", "log in")


def run(cmd: list[str], timeout: int) -> tuple[int, str]:
    """Run a child tool. Returns (rc, combined output). Never raises on a non-zero exit."""
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"__TIMEOUT__ after {timeout}s"
    except OSError as exc:
        return 125, f"__OSERROR__ {exc}"


def classify_failure(text: str) -> str:
    low = (text or "").lower()
    if "__TIMEOUT__" in text:
        return "TIMEOUT"
    if any(m in low for m in WALL_MARKS):
        return "WALL"
    if any(m in low for m in AUTH_MARKS):
        return "AUTH"
    return "FAIL"


def load_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except ValueError:
            print(f"  ledger unreadable, starting a fresh one: {LEDGER.name}")
    return {"seats": {}, "runs": []}


def save_ledger(ledger: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def build_manifest(port: int) -> list[dict]:
    """Refresh the manifest. Dry-run mode: metadata only, no tab is attached or focused."""
    rc, out = run([PY, str(SWEEP), "--port", str(port), "--json", str(MANIFEST)], 120)
    if rc != 0 or not MANIFEST.exists():
        print(f"manifest failed (rc={rc}):\n{out[-800:]}")
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("tabs", [])


def dedupe_by_site(tabs: list[dict]) -> list[dict]:
    """One unit per site. Several tabs can share a provider; capturing each would hammer one seat."""
    seen, rows = set(), []
    for t in tabs:
        site = t.get("knownSite") or t.get("host") or ""
        if not site or site in seen:
            continue
        seen.add(site)
        rows.append(t)
    return rows


def gate_verdict(report: pathlib.Path, host: str) -> tuple[str, str]:
    """Read one host's verdict out of a replay report. Returns (verdict, detail)."""
    if not report.exists():
        return "NO_REPORT", "replay_check wrote no report"
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except ValueError as exc:
        return "NO_REPORT", f"unparseable report: {exc}"
    rows = data if isinstance(data, list) else data.get("results", data.get("sessions", []))
    for row in rows:
        if host and host in str(row.get("host", "")):
            return str(row.get("verdict") or "UNKNOWN"), str(row.get("detail") or row.get("reason") or "")
    if len(rows) == 1:
        # A per-seat report was already filtered to one seat by `--only`, so the single row IS this
        # seat even when the names differ -- the manifest's host comes from the tab URL and the jar's
        # from the recorded exchange, and `www.` alone is enough to break a substring match. Falling
        # through to NOT_IN_REPORT here would discard a genuine pass on a cosmetic mismatch.
        row = rows[0]
        return (str(row.get("verdict") or "UNKNOWN"),
                f"[matched the report's only row, {row.get('host')!r}] "
                f"{row.get('detail') or row.get('reason') or ''}")
    return "NOT_IN_REPORT", f"no row for {host} among {len(rows)} row(s)"


def capture_and_verify(site: str, host: str, port: int, wait: int) -> tuple[str, str]:
    """Run ONE sweep unit -- which captures AND replays -- then read the verdict it recorded.

    This deliberately does not replay again. `--execute` has already sent a live verifying request to
    the seat; a second one would spend another of somebody else's free requests to learn a fact we
    already have. A stale report from an earlier run is deleted first, so a unit that dies before
    writing cannot be misread as the pass it scored last week.
    """
    report = scratch_report(site)
    if report.exists():
        report.unlink()
    rc, out = run([PY, str(SWEEP), "--port", str(port), "--execute", "--site", site,
                   "--wait", str(wait)], CAPTURE_TIMEOUT_S + REPLAY_TIMEOUT_S)
    verdict, detail = gate_verdict(report, host)
    if verdict in ("NO_REPORT", "NOT_IN_REPORT"):
        # No verdict was recorded, so the unit died before the replay could score it. Report what
        # actually broke rather than the absence of a report, which names no cause.
        return classify_failure(out), (out or detail).strip()[-300:] or f"rc={rc}"
    return verdict, detail or out[-200:]


def regenerate_gate() -> tuple[bool, dict]:
    """FULL run -- the only thing allowed to write state/replay_check.json."""
    rc, out = run([PY, str(REPLAY), "--out", str(GATE)], REPLAY_TIMEOUT_S * 4)
    if not GATE.exists():
        print(f"  gate not written (rc={rc}): {out[-400:]}")
        return False, {}
    data = json.loads(GATE.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("results", [])
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
    return True, counts


def restart_pool() -> dict:
    """Restart :20130 so it reloads the gate. NEVER touches :20128 -- that is OmniRoute's, not ours."""
    # Kill the port-owning interpreter AND any lingering chat_pool_server.py python
    # process (e.g. the venv-launcher parent of a previous pair, which would otherwise
    # survive its child and linger until the next reboot). The filter matches only the
    # pool script's own name -- this orchestrator's command line never contains it, and
    # powershell.exe is excluded by the Name filter itself.
    rc, out = run(["powershell", "-NoProfile", "-Command",
                   f"Get-NetTCPConnection -LocalPort {POOL_PORT} -State Listen "
                   f"-ErrorAction SilentlyContinue | ForEach-Object "
                   f"{{ Stop-Process -Id $_.OwningProcess -Force }}; "
                   f"Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" "
                   f"| Where-Object {{ $_.CommandLine -match 'chat_pool_server\\.py' }} "
                   f"| ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"], 45)
    time.sleep(1.5)
    run(["powershell", "-NoProfile", "-Command",
         f"Start-Process -FilePath '{PY}' -ArgumentList '{POOL_SERVER.relative_to(ROOT)}' "
         f"-WorkingDirectory '{ROOT}' -WindowStyle Hidden "
         f"-RedirectStandardOutput '{ROOT / 'logs' / 'chat_pool.out'}' "
         f"-RedirectStandardError '{ROOT / 'logs' / 'chat_pool.err'}'"], 45)
    for _ in range(12):
        time.sleep(2)
        try:
            with _HEALTH_OPENER.open(POOL_HEALTH, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:
            continue
    return {}


def restart_pool_bounded(deadline_s: int = RESTART_DEADLINE_S) -> dict:
    """restart_pool() with a hard wall-clock ceiling (D1).

    The worker is a daemon thread: if the restart wedges, the run moves on without
    health data instead of parking forever, and the supervisor task reloads :20130
    from the gate within 5 minutes regardless (TECHNOLOGY_TRANSFER §22).
    """
    result: dict = {}
    done = threading.Event()

    def _worker() -> None:
        nonlocal result
        try:
            result = restart_pool()
        except Exception as exc:  # never let step 3 raise past the ledger write
            result = {"error": f"restart_pool raised: {exc!r}"}
        finally:
            done.set()

    thread = threading.Thread(target=_worker, name="restart-20130", daemon=True)
    thread.start()
    if not done.wait(deadline_s):
        print(f"    WARNING :20130 restart did not finish within {deadline_s}s -- continuing "
              f"without health data (the supervisor task will reload the pool)", flush=True)
    return result


def next_worklog_number() -> int:
    """The active numbering stream's next number: the LAST numbered entry in file
    order, + 1. NOT the global max -- the file carries three stray 4xxx-numbered
    entries from an older merged log (#4552/#4876/#4877 sit near its beginning),
    and max() would jump the live sequence (#1157) to #4878."""
    try:
        text = WORKLOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 1
    matches = list(re.finditer(r"^### \[[^\]]*\] #(\d+)", text, re.MULTILINE))
    return (int(matches[-1].group(1)) + 1) if matches else 1


def append_worklog(lines: list[str], *, summary: str = "") -> None:
    """Append this run's verdict table as a numbered MASTER_WORKLOG.md entry.

    The old '### Graduation pass <ts>' heading broke the worklog's house rule
    ('### [YYYY-MM-DD HH:MM] #N — title') and made run tables un-greppable. Never
    raises (D1): if the append fails, the verdict table is still in ledger['runs'].
    """
    if not (lines or summary):
        return
    n = next_worklog_number()
    stamp = time.strftime("%Y-%m-%d %H:%M")
    body = [f"\n### [{stamp}] #{n} — graduate_all_seats run: {summary or 'verdict table'}\n",
            "| seat | host | verdict | detail | graduated |",
            "|---|---|---|---|---|"] + list(lines) + [""]
    try:
        with WORKLOG.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(body) + "\n")
        print(f"  worklog: entry #{n} appended to {WORKLOG.name}", flush=True)
    except OSError as exc:
        fallback = ROOT / "state" / f"grad_worklog_fallback_{time.strftime('%Y%m%d_%H%M%S')}.md"
        try:
            fallback.write_text("\n".join(body) + "\n", encoding="utf-8")
            print(f"  WARNING worklog append failed ({exc}); table saved to {fallback.name}",
                  flush=True)
        except OSError:
            print(f"  WARNING worklog append failed ({exc}); the table is preserved in "
                  f"ledger['runs']", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually capture. Without this, prints the plan and sends nothing.")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--limit", type=int, default=0, help="stop after N seats (0 = all)")
    ap.add_argument("--only", default="", help="comma-separated exact site names")
    ap.add_argument("--wait", type=int, default=25, help="capture wait seconds per seat")
    ap.add_argument("--retry-walls", action="store_true",
                    help="re-attempt seats previously recorded as walled. Off by default on purpose.")
    ap.add_argument("--redo-passed", action="store_true",
                    help="re-capture seats already REPLAY_OK. Off by default -- they are working supply.")
    ap.add_argument("--video-lane", action="store_true",
                    help="print the ordered video work list and exit. Captures nothing.")
    ap.add_argument("--no-restart", action="store_true",
                    help="skip step 3's :20130 restart (leaves new seats invisible to the pool)")
    args = ap.parse_args()

    tabs = build_manifest(args.port)
    if not tabs:
        return 1

    video = dedupe_by_site([t for t in tabs if t.get("classification") == "VIDEO_SEPARATE_GRADUATION"])
    if args.video_lane:
        print(f"\nVIDEO LANE -- {len(video)} provider(s). This script will NOT capture these.")
        print("A video capture spends clips, and a video seat must never enter the chat pool.\n")
        for t in video:
            print(f"  {t.get('knownSite',''):28} {t.get('host',''):24} "
                  f"{t.get('latestReplayVerdict') or '-':10} {t.get('nextAction','')}")
        print("\nHand these to the harvester. Acceptance: a RESULT exchange observed AND a screenshot")
        print("confirming the sentinel landed in a VIDEO composer. Clips on :8189 is the only number.")
        return 0

    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    seats = dedupe_by_site([t for t in tabs if t.get("classification") == "ELIGIBLE_CAPTURE"])
    if wanted:
        seats = [t for t in seats if (t.get("knownSite") or t.get("host")) in wanted]

    ledger = load_ledger()
    plan, skipped = [], []
    for t in seats:
        site = t.get("knownSite") or t.get("host")
        prior = ledger["seats"].get(site) or {}
        if prior.get("verdict") == "REPLAY_OK" and not args.redo_passed:
            skipped.append((site, "already REPLAY_OK"))
            continue
        # First-run guard: the manifest carries each tab's latest replay verdict from prior sweeps.
        # Without this check a first --apply re-captures and re-replays seats that are ALREADY
        # proven working supply -- the exact double-spend the docstring forbids ("--redo-passed
        # off by default -- they are working supply"). The ledger remains the authority for THIS
        # script's own verdicts; the manifest only seeds the first run. Keyed per-seat so a
        # non-empty ledger (e.g. after a failed pass) still protects the proven seats.
        if (site not in ledger["seats"] and t.get("latestReplayVerdict") == "REPLAY_OK"
                and not args.redo_passed):
            skipped.append((site, "manifest verdict REPLAY_OK (not in ledger, proven supply)"))
            continue
        if prior.get("verdict") == "WALL" and not args.retry_walls:
            skipped.append((site, "walled -- never re-knocked without --retry-walls"))
            continue
        if int(prior.get("attempts", 0)) >= MAX_ATTEMPTS and not args.retry_walls:
            skipped.append((site, f"{prior.get('attempts')} attempts already, same failure"))
            continue
        plan.append(t)
    if args.limit:
        plan = plan[: args.limit]

    print(f"\ntabs {len(tabs)}  eligible sites {len(seats)}  planned {len(plan)}  "
          f"skipped {len(skipped)}  video lane {len(video)} (not touched)")
    for site, why in skipped:
        print(f"  skip  {site:28} {why}")
    print()
    for t in plan:
        print(f"  plan  {t.get('knownSite',''):28} {t.get('host',''):24} "
              f"{t.get('latestReplayVerdict') or '-'}")

    if not args.apply:
        print("\nplan only -- nothing was sent. Re-run with --apply to execute.")
        print("Video seats are excluded by design; see --video-lane.")
        return 0
    if not plan:
        print("\nnothing to do.")
        return 0

    if args.apply:
        locked, lock_msg = acquire_instance_lock()
        if not locked:
            print(f"\nREFUSING to run: {lock_msg}", flush=True)
            return 1
        # Line-buffered stdout: run 3 was killed with its last 8 KB of transcript still
        # in the buffer, which is exactly why its log appears to stop mid-step. Flush
        # every line so a killed run leaves an honest tail behind.
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass

    rows, graduated = [], []
    summary = ""
    try:
        for index, t in enumerate(plan, 1):
            site = t.get("knownSite") or t.get("host")
            host = t.get("host") or ""
            print(f"\n[{index}/{len(plan)}] {site}  ({host})", flush=True)
            entry = ledger["seats"].setdefault(site, {"host": host, "attempts": 0})
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            entry["lastAttemptAt"] = int(time.time())

            verdict, detail = capture_and_verify(site, host, args.port, args.wait)
            entry["verdict"] = verdict
            entry["step"] = "verdict" if verdict.startswith("REPLAY") else "capture"
            entry["detail"] = detail[-300:]
            passed = verdict == "REPLAY_OK"
            print(f"    steps 1-2  {verdict}  {detail[:90]}", flush=True)
            if verdict == "WALL":
                print("           wall -- recorded once, never knocked on again", flush=True)
            if passed:
                graduated.append(site)
                entry["attempts"] = 0
            rows.append(f"| {site} | {host} | {verdict} | {detail[:70].replace('|', '/')} | "
                        f"{'yes' if passed else 'no'} |")
            save_ledger(ledger)
            time.sleep(SEAT_DELAY_S)

        print(f"\nstep 3 graduate -- {len(graduated)} seat(s) replayed clean: "
              f"{', '.join(graduated) or '-'}", flush=True)
        if graduated:
            ok, counts = regenerate_gate()
            print(f"    canonical gate rebuilt: {ok}  {counts}", flush=True)
            if ok and not args.no_restart:
                # Bounded (D1): a hung restart must never park the run. Worst case it
                # degrades to missing health data; the supervisor task reloads :20130
                # from the gate within 5 minutes regardless (TECHNOLOGY_TRANSFER §22).
                health = restart_pool_bounded()
                served = health.get("served", "?")
                ready = health.get("readyNow", "?")
                hosts = [p.get("host") for p in health.get("providers", [])]
                print(f"    :20130 reloaded -- served {served}, ready {ready}", flush=True)
                for h in hosts:
                    print(f"      {h}", flush=True)
                for site in graduated:
                    entry = ledger["seats"][site]
                    entry["servedByPool"] = any(
                        (entry.get("host") or "") in str(h) for h in hosts)
                    if not entry["servedByPool"]:
                        print(f"    WARNING {site} replayed clean but the pool is not serving "
                              f"it -- its verdict is not REPLAY_OK in the canonical gate",
                              flush=True)
            elif args.no_restart:
                print("    --no-restart: the pool has NOT reloaded, so these seats are still "
                      "invisible", flush=True)

        summary = f"{len(graduated)}/{len(plan)} graduated"
        ledger["runs"].append({"at": int(time.time()), "planned": len(plan),
                               "graduated": graduated, "rows": rows})
    finally:
        # D1: the ledger and the worklog are written NO MATTER HOW the run dies.
        if not summary:
            summary = ("no seats executed" if not rows else
                       f"{len(rows)}/{len(plan)} seats attempted (run did not finish; "
                       f"partial table)")
        try:
            save_ledger(ledger)
        except OSError as exc:
            print(f"    WARNING ledger write failed: {exc}", flush=True)
        append_worklog(rows, summary=summary)
        if args.apply:
            release_instance_lock()
    print(f"\nledger: {LEDGER.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
