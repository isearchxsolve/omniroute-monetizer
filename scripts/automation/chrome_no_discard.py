#!/usr/bin/env python3
"""Stop Chrome discarding the sweep's tabs, so clicking one does not reload it.

THE SYMPTOM: tabs reload whenever you click them, and a sweep that walks many tabs keeps losing
the page it just set up.

THE CAUSE, measured in this repo on 2026-08-24 (see video_router.wake_tab and video_provider.py:96):
Chrome's memory saver DISCARDS an idle tab's renderer. The tab stays in the tab strip and still
appears in /json/list, and browser-domain CDP calls still answer instantly -- but there is no
execution context any more, so every Runtime.evaluate hangs until the deadline. When a human clicks
a discarded tab, Chrome has to re-create that renderer, which means loading the page again from
scratch: the reload-on-click. Same root cause, two faces.

Two things make it fire harder here, and both are self-inflicted:

  * A sweep leaves tabs idle by construction -- it works one tab while the other twenty sit still,
    which is exactly the signal memory saver looks for.
  * An off-screen or covered window reads as occluded, and Chrome backgrounds occluded windows more
    aggressively. This repo has already had to fix an invisible off-screen Chrome window (commit
    4ebc5c7), so the automation windows are prime candidates.

THE FIX, in two layers, because neither alone is enough:

  1. NO_DISCARD_FLAGS -- command line, applies to a Chrome you are launching now. Import and splice
     these into any launcher's argv.
  2. patch_profile() -- writes the memory-saver settings into the profile's own Preferences, which
     is PERSISTENT. That is the high-leverage half: this repo launches Chrome from a dozen different
     scripts, and a setting stored in the profile is inherited by all of them without touching one
     line of their argv.

Chrome rewrites Preferences when it exits, so a patch written underneath a RUNNING Chrome is
discarded on shutdown. This refuses to write to a profile Chrome currently holds and says so,
rather than reporting a success that will silently evaporate.

Never touches the operator's live Chrome: every path goes through chrome_live_guard.assert_safe,
which is the module that exists because cloning the live profile permanently revoked a Google
session on 2026-08-22.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import chrome_live_guard  # noqa: E402  -- import for its refusal, not for a side effect


# Command-line half. Grouped by what each one actually prevents, because a flag list nobody can
# explain is a flag list nobody dares change.
NO_DISCARD_FLAGS: list[str] = [
    # The discard machinery itself. Names differ across milestones and Chrome ignores features it
    # does not know, so listing the old and new spellings costs nothing and survives an upgrade.
    "--disable-features="
    "HighEfficiencyModeAvailable,"          # M108-M115 spelling
    "MemorySaverModeAvailable,"             # M116+ rename
    "HeuristicMemorySaver,"                 # M121+ automatic-aggressiveness mode
    "WebContentsDiscard,"                   # the discard mechanism itself
    "CalculateNativeWinOcclusion",          # stop treating an off-screen window as hidden
    # Occluded/backgrounded windows get throttled hard, which is how an off-screen automation
    # window ends up frozen even before it is discarded.
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]

# The persistent half. Set in the per-profile Preferences file.
#   state 0 == disabled. The exclusion list is the belt: "*" tells Chrome to keep every site active,
#   which holds even on a milestone whose feature flag has been renamed out from under us.
_PREF_PATCH: dict[str, object] = {
    "performance_tuning.high_efficiency_mode.state": 0,
    "performance_tuning.high_efficiency_mode_enabled": False,
    "performance_tuning.battery_saver_mode.state": 0,
    "performance_tuning.tab_discarding.exclusions": ["*"],
}


def _set_dotted(tree: dict, dotted: str, value) -> bool:
    """Set a.b.c on a nested dict. True if it changed anything."""
    keys = dotted.split(".")
    node = tree
    for k in keys[:-1]:
        nxt = node.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            node[k] = nxt
        node = nxt
    if node.get(keys[-1]) == value:
        return False
    node[keys[-1]] = value
    return True


_RUNNING_UDD: set[str] | None = None


def running_user_data_dirs() -> set[str]:
    """Lower-cased --user-data-dir of every running chrome.exe.

    MEASURED: an open-for-append probe on Cookies/Preferences does NOT detect a running Chrome on
    Windows -- it reported all 13 profiles free while four Chromes were live on them, which would
    have produced exactly the evaporating patch this module warns about. The process command line is
    the signal that actually works.
    """
    global _RUNNING_UDD
    if _RUNNING_UDD is not None:
        return _RUNNING_UDD
    found: set[str] = set()
    # Single-quoted throughout so nothing needs escaping on either side, and the command line is
    # parsed in python rather than in a PowerShell regex.
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' } | "
          "ForEach-Object { $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        for line in (out.stdout or "").splitlines():
            m = re.search(r'--user-data-dir=(?:"([^"]+)"|(\S+))', line)
            if m:
                raw = m.group(1) or m.group(2)
                found.add(str(pathlib.Path(raw)).rstrip("\\/").lower())
    except (OSError, subprocess.SubprocessError):
        # Cannot tell -> assume every profile is held. Refusing to write is recoverable;
        # writing under a live Chrome loses the change without saying so.
        found.add("*")
    _RUNNING_UDD = found
    return found


def profile_is_locked(profile_dir: pathlib.Path) -> bool:
    """Is Chrome holding this profile right now?"""
    running = running_user_data_dirs()
    if "*" in running:
        return True
    # A profile dir normally sits inside the user-data-dir; some launchers point --user-data-dir
    # straight at it, so check both.
    for cand in (profile_dir.parent, profile_dir):
        if str(cand).rstrip("\\/").lower() in running:
            return True
    return False


def find_profiles(user_data_dir: pathlib.Path) -> list[pathlib.Path]:
    """Every profile directory inside a user-data-dir, i.e. each dir holding a Preferences file."""
    if not user_data_dir.is_dir():
        return []
    out = [p.parent for p in sorted(user_data_dir.glob("*/Preferences")) if p.is_file()]
    # A user-data-dir used directly as a profile (some launchers do this) has Preferences at root.
    if (user_data_dir / "Preferences").is_file():
        out.append(user_data_dir)
    return out


def patch_profile(profile_dir: pathlib.Path, apply: bool = False) -> dict:
    """Disable discarding for one profile. Returns a report row; never raises on a bad profile."""
    row: dict = {"profile": str(profile_dir), "changed": [], "status": "ok"}
    try:
        chrome_live_guard.assert_safe(profile_dir, who="chrome_no_discard")
    except BaseException as e:                       # the guard's refusal is deliberately not Exception
        row["status"] = f"REFUSED: live profile -- {type(e).__name__}"
        return row

    prefs = profile_dir / "Preferences"
    if not prefs.is_file():
        row["status"] = "skip: no Preferences file"
        return row
    if profile_is_locked(profile_dir):
        # Reported, not worked around. Chrome would overwrite us on exit and the caller would think
        # the sweep was fixed when nothing had changed.
        row["status"] = "LOCKED: Chrome is running on this profile -- close it, then re-run"
        return row

    try:
        tree = json.loads(prefs.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        row["status"] = f"skip: unreadable Preferences ({type(e).__name__})"
        return row
    if not isinstance(tree, dict):
        row["status"] = "skip: Preferences is not an object"
        return row

    for dotted, value in _PREF_PATCH.items():
        if _set_dotted(tree, dotted, value):
            row["changed"].append(dotted)
    if not row["changed"]:
        row["status"] = "already set"
        return row
    if not apply:
        row["status"] = f"would change {len(row['changed'])} keys (dry run)"
        return row

    try:
        tmp = prefs.with_name("Preferences.nodiscard.tmp")
        tmp.write_text(json.dumps(tree, separators=(",", ":")), encoding="utf-8")
        tmp.replace(prefs)                            # atomic: a half-written Preferences resets the profile
    except OSError as e:
        row["status"] = f"write failed: {type(e).__name__}"
        return row
    row["status"] = f"patched {len(row['changed'])} keys"
    return row


def default_roots() -> list[pathlib.Path]:
    """The repo's own Chrome roots. Deliberately hard-coded to state/ so a typo cannot reach live."""
    state = ROOT / "state"
    roots = [state / "automation_profiles", state / "browser_profile", state / "harvest_profile",
             state / "claude_profiles"]
    # Nested seat dirs: state/automation_profiles/<seat>/ is itself a user-data-dir.
    for base in list(roots):
        if base.is_dir():
            roots.extend(p for p in sorted(base.iterdir()) if p.is_dir())
    return [r for r in roots if r.is_dir()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the change (default is a dry run)")
    ap.add_argument("--root", action="append", default=[],
                    help="a user-data-dir to patch; repeatable. Defaults to the repo's state/ roots.")
    ap.add_argument("--flags", action="store_true", help="print the launch flags and exit")
    a = ap.parse_args()

    if a.flags:
        print(" ".join(NO_DISCARD_FLAGS))
        return 0

    roots = [pathlib.Path(r) for r in a.root] or default_roots()
    if not roots:
        print("no Chrome user-data-dir found under state/ -- nothing to patch")
        return 1

    profiles: list[pathlib.Path] = []
    for r in roots:
        for p in find_profiles(r):
            if p not in profiles:
                profiles.append(p)
    if not profiles:
        print(f"no profile (a dir with a Preferences file) under: {', '.join(str(r) for r in roots)}")
        return 1

    print(f"{'apply' if a.apply else 'DRY RUN'}: {len(profiles)} profile(s)\n")
    rows = [patch_profile(p, apply=a.apply) for p in profiles]
    for row in rows:
        try:
            shown = str(pathlib.Path(row["profile"]).relative_to(ROOT))
        except ValueError:
            shown = row["profile"]
        print(f"  {shown[:58]:58s} {row['status']}")

    locked = [r for r in rows if r["status"].startswith("LOCKED")]
    if locked:
        print(f"\n{len(locked)} profile(s) skipped because Chrome holds them. Chrome rewrites "
              f"Preferences on exit, so patching under a running Chrome is discarded on shutdown.")
    if not a.apply:
        print("\nnothing written -- re-run with --apply")
    else:
        print("\nsettings take effect on the profile's NEXT launch. For a Chrome already running, "
              "the command-line half is what matters: chrome_no_discard.py --flags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
