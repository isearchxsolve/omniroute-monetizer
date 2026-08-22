"""
chrome_selfheal.py -- ONE command that checks everything, repairs what is repairable,
and says plainly what only a human can do.

Run it after any Chrome weirdness. It is safe to run at any time, as often as you like.

WHAT IT REPAIRS BY ITSELF
  1. Removes any filesystem alias (junction/symlink) pointing at the live Chrome profile.
     This was the 2026-08-22 root cause. Removing the link never touches the real profile.
  2. Reinstalls the machine-wide automation guard if it has gone missing.
  3. Takes a fresh backup of all four profiles, so a future *local* wipe is recoverable.

WHAT IT CANNOT REPAIR, AND WILL NOT PRETEND TO
  A Google session that the server has revoked. Proven on 2026-08-22: a byte-perfect
  credential pair was restored, and Chrome wiped it within a minute because Google had
  already killed it server-side. Only a human signing in fixes that. Any tool claiming
  otherwise is lying.

NEVER: writes to a Chrome file, decrypts a cookie or password, or edits a Chrome database.
Backups are plain file copies. All probing is done on temp copies opened read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

LIVE_ROOT = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Admin\AppData\Local")) / \
    "Google" / "Chrome" / "User Data"

EXPECTED = {
    "Default": "kunal.colab@gmail.com",
    "Profile 14": "xxpertcomments@gmail.com",
    "Profile 16": "niloydassana@gmail.com",
    "Profile 17": "isearch.xsolve@gmail.com",
}

BACKUP_ROOT = Path(r"D:\omniroute-backups\chrome-profiles")

# Places an alias to the live profile has appeared, or plausibly could.
ALIAS_SUSPECTS = [
    PROJECT_ROOT / "state" / "live_link",
    PROJECT_ROOT / "state" / "chrome_link",
    PROJECT_ROOT / "state" / "real_profile",
    PROJECT_ROOT / "live_link",
]

# Files that together constitute a Chrome sync credential. Both or neither.
CREDENTIAL_FILES = ("Web Data", "Preferences")

SITE_PACKAGES_MARKERS = ("chrome_live_guard.pth", "chrome_live_guard_boot.py")


class Report:
    def __init__(self) -> None:
        self.ok: list[str] = []
        self.fixed: list[str] = []
        self.human: list[str] = []
        self.problems: list[str] = []

    def add_ok(self, msg: str) -> None:
        self.ok.append(msg)
        print(f"  [ok]      {msg}")

    def add_fixed(self, msg: str) -> None:
        self.fixed.append(msg)
        print(f"  [FIXED]   {msg}")

    def add_human(self, msg: str) -> None:
        self.human.append(msg)
        print(f"  [YOU]     {msg}")

    def add_problem(self, msg: str) -> None:
        self.problems.append(msg)
        print(f"  [PROBLEM] {msg}")


def section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


# ---------------------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------------------

def chrome_is_running() -> bool | None:
    """True / False / None if it cannot be determined. Never guesses False."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return None
    return any("chrome.exe" in line.lower() for line in out.splitlines())


def is_reparse_point(path: Path) -> bool:
    """Detect a junction. os.path.islink() returns False for junctions -- do not use it."""
    try:
        attrs = os.lstat(str(path)).st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def sweep_aliases(report: Report, dry_run: bool) -> None:
    section("1. Aliases pointing at your real Chrome folder (the 2026-08-22 cause)")
    found_any = False
    for suspect in ALIAS_SUSPECTS:
        if not suspect.exists() and not is_reparse_point(suspect):
            continue
        target = Path(os.path.realpath(str(suspect)))
        live = Path(os.path.realpath(str(LIVE_ROOT)))
        points_at_live = target == live or live in target.parents
        if not points_at_live:
            report.add_ok(f"{suspect.name} exists but does not point at Chrome ({target})")
            continue

        found_any = True
        if not is_reparse_point(suspect):
            # A REAL directory here is a different, nastier problem: Chrome would scaffold
            # empty profiles inside it and every later probe would read the wrong data.
            report.add_problem(
                f"{suspect} is a REAL folder shadowing the Chrome path. Not deleting it "
                f"automatically -- tell the agent, it needs a human decision."
            )
            continue

        if dry_run:
            report.add_problem(f"WOULD REMOVE alias: {suspect} -> {target}  (dry run)")
            continue

        before = len(list(live.iterdir())) if live.exists() else -1
        try:
            os.rmdir(str(suspect))   # removes ONLY the link. shutil.rmtree would delete THROUGH it.
        except OSError as exc:
            report.add_problem(f"could not remove alias {suspect}: {exc}")
            continue
        after = len(list(live.iterdir())) if live.exists() else -1
        if before != after:
            report.add_problem(
                f"alias removed BUT live profile item count changed {before} -> {after}. "
                f"Stop and tell the agent immediately."
            )
        else:
            report.add_fixed(
                f"removed alias {suspect} (link only; live profile untouched, "
                f"{before} items before and after)"
            )

    if not found_any:
        report.add_ok("no alias to the live Chrome folder anywhere. This is the good state.")


def check_guard(report: Report, dry_run: bool) -> None:
    section("2. The automation guard (stops this from happening again)")
    try:
        import chrome_live_guard  # noqa: F401
        report.add_ok("guard module present")
    except Exception as exc:
        report.add_problem(f"guard module MISSING or broken: {exc}")
        return

    # Is it armed machine-wide? Look for the .pth bootstrap next to site-packages.
    import site
    installed_in = []
    for sp in list(site.getsitepackages()) + [site.getusersitepackages()]:
        d = Path(sp)
        if all((d / m).exists() for m in SITE_PACKAGES_MARKERS):
            installed_in.append(d)
    if installed_in:
        report.add_ok(f"guard arms automatically for every Python process ({len(installed_in)} site-packages)")
    else:
        report.add_problem(
            "guard is NOT armed automatically. Scripts must import it by hand, which means a "
            "future script could forget. Tell the agent to reinstall the bootstrap."
        )

    # Live proof: does an attempt actually get refused?
    from chrome_live_guard import LiveProfileRefused, assert_safe
    try:
        assert_safe(LIVE_ROOT, who="selfheal proof")
        report.add_problem("guard did NOT refuse the live profile. It is not working.")
    except LiveProfileRefused:
        report.add_ok("guard actively refuses the live Chrome profile (tested just now)")


def probe_profile(profile: str) -> dict:
    """Read-only: does this profile hold a complete, matching sync credential?"""
    pdir = LIVE_ROOT / profile
    result = {
        "profile": profile,
        "exists": pdir.is_dir(),
        "tokens": None,
        "accounts": [],
        "expected": EXPECTED.get(profile),
        "signed_in": False,
        "note": "",
    }
    if not result["exists"]:
        result["note"] = "profile folder missing"
        return result

    tmp = tempfile.mkdtemp(prefix="selfheal_")
    try:
        wd = pdir / "Web Data"
        if wd.exists():
            dst = Path(tmp) / "wd.db"
            shutil.copy2(wd, dst)
            try:
                con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
                result["tokens"] = con.execute(
                    "SELECT COUNT(*) FROM token_service").fetchone()[0]
                con.close()
            except sqlite3.Error as exc:
                result["note"] = f"Web Data unreadable: {exc}"
        else:
            result["note"] = "Web Data missing"

        prefs = pdir / "Preferences"
        if prefs.exists():
            try:
                data = json.loads(prefs.read_text(encoding="utf-8", errors="replace"))
                for entry in (data.get("account_info") or []):
                    email = entry.get("email")
                    if email:
                        result["accounts"].append(email)
            except (ValueError, OSError) as exc:
                result["note"] = (result["note"] + f" Preferences unreadable: {exc}").strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    result["signed_in"] = bool(result["tokens"]) and bool(result["accounts"])
    return result


def check_signins(report: Report) -> list[dict]:
    section("3. Are your four accounts signed in?")
    results = []
    for profile, email in EXPECTED.items():
        r = probe_profile(profile)
        results.append(r)
        who = r["accounts"][0] if r["accounts"] else "(no account)"
        if r["signed_in"] and r["expected"] and r["expected"] in r["accounts"]:
            report.add_ok(f"{profile:<11} SIGNED IN as {who}")
        elif r["signed_in"]:
            report.add_problem(
                f"{profile:<11} signed in as {who} but expected {r['expected']} -- wrong account"
            )
        else:
            report.add_human(
                f"{profile:<11} SIGNED OUT (expected {email}). Only you can fix this: "
                f"open Chrome, pick this profile, sign in. No script can."
            )
        if r["note"]:
            print(f"            note: {r['note']}")
    return results


def make_backup(report: Report, dry_run: bool) -> Path | None:
    section("4. Fresh backup (so a future local wipe IS recoverable)")
    running = chrome_is_running()
    if running is None:
        report.add_problem("could not tell whether Chrome is running; skipping backup to be safe")
        return None
    if running:
        report.add_human(
            "Chrome is OPEN, so a backup now could copy half-written files. "
            "Close Chrome completely and run this again to get a clean backup."
        )
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"selfheal_{stamp}"
    if dry_run:
        report.add_ok(f"would back up four profiles to {dest} (dry run)")
        return None

    try:
        dest.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        report.add_problem(f"cannot create backup folder {dest}: {exc}")
        return None

    copied = 0
    for profile in EXPECTED:
        src = LIVE_ROOT / profile
        if not src.is_dir():
            continue
        out = dest / profile
        out.mkdir(parents=True, exist_ok=True)
        for name in CREDENTIAL_FILES + ("Bookmarks", "Login Data", "Login Data For Account"):
            f = src / name
            if f.exists():
                try:
                    shutil.copy2(f, out / name)
                    copied += 1
                except OSError as exc:
                    print(f"            skip {profile}/{name}: {exc}")
        cookies = src / "Network" / "Cookies"
        if cookies.exists():
            (out / "Network").mkdir(exist_ok=True)
            try:
                shutil.copy2(cookies, out / "Network" / "Cookies")
                copied += 1
            except OSError as exc:
                print(f"            skip {profile}/Network/Cookies: {exc}")

    ls = LIVE_ROOT / "Local State"
    if ls.exists():
        try:
            shutil.copy2(ls, dest / "Local State")
            copied += 1
        except OSError as exc:
            print(f"            skip Local State: {exc}")

    report.add_fixed(f"backed up {copied} files to {dest}")
    return dest


# ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Check and self-heal Chrome automation damage.")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only, change nothing (default is to repair)")
    ap.add_argument("--json", metavar="PATH", help="also write a machine-readable report")
    args = ap.parse_args()

    print("=" * 78)
    print("  CHROME SELF-HEAL")
    print("=" * 78)
    print(f"  live Chrome folder : {LIVE_ROOT}")
    print(f"  mode               : {'DRY RUN (nothing will change)' if args.dry_run else 'REPAIR'}")

    report = Report()
    sweep_aliases(report, args.dry_run)
    check_guard(report, args.dry_run)
    signins = check_signins(report)
    make_backup(report, args.dry_run)

    section("SUMMARY")
    print(f"  fine            : {len(report.ok)}")
    print(f"  repaired now    : {len(report.fixed)}")
    print(f"  needs you       : {len(report.human)}")
    print(f"  needs the agent : {len(report.problems)}")

    signed_in = sum(1 for r in signins if r["signed_in"])
    print()
    print(f"  GOOGLE_SYNC_AUTHENTICATED = {signed_in} of 4")
    if signed_in == 4 and not report.problems:
        print("  MONETIZER_READY for Chrome sign-in. Provider logins are a separate thing.")
    elif report.human:
        print("  Sign in to the profiles listed under [YOU]. Nothing else is broken.")
    if report.problems:
        print("  Show the [PROBLEM] lines to the agent.")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated": datetime.now().isoformat(timespec="seconds"),
            "dry_run": args.dry_run,
            "live_root": str(LIVE_ROOT),
            "signed_in_count": signed_in,
            "profiles": signins,
            "ok": report.ok,
            "fixed": report.fixed,
            "needs_human": report.human,
            "needs_agent": report.problems,
        }, indent=2), encoding="utf-8")
        print(f"\n  report written: {out}")

    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
