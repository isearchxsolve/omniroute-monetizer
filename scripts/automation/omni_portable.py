#!/usr/bin/env python3
"""Move this rig to a fresh machine, and check a fresh machine is ready for it.

The honest shape of the problem
------------------------------
Almost none of the value here is the code. The code is ~200 Python files that `pip install` and run
anywhere. The value is the **captured supply**, and it splits cleanly into portable and not:

  PORTABLE -- copy the file and it works on any machine
    state/secrets/session_*.json    the chat supply. A recorded HTTP exchange plus a cookie header, in
                                    plain JSON. Nothing about it is bound to this machine. This is the
                                    single biggest argument for capturing to JSON instead of driving a
                                    live browser: the asset is a file, so the asset is portable.
    state/replay_check.json         which of those actually replay
    scripts/automation/*.json       client configs
    the repository itself           git

  NOT PORTABLE -- copying it produces something that looks right and does not work
    state/omniroute_password.bin    DPAPI-sealed to this Windows user on this machine. On another box
                                    it decrypts to nothing. Must be re-sealed by the operator.
    state/automation_profiles/**    Chrome binds its cookie encryption key to DPAPI too, so a copied
                                    profile has a Cookies database it cannot read -- every site login
                                    is gone while every file is present, which is the worst kind of
                                    failure because it looks like a working restore. Google sign-in is
                                    worse still: Device Bound Session Credentials can treat the move as
                                    a compromise and revoke permanently. Never copy these. Sign in
                                    again on the new machine.
    OmniRoute's own database        live OAuth connections, server-side refresh state. Re-connect there.

So: an export produces a bundle that restores the **chat pool** completely and the **video seats** not
at all. That is not a limitation of this script, it is the shape of the underlying credentials, and
saying so plainly is more useful than a bundle that pretends otherwise.

Usage
-----
    python omni_portable.py --doctor                  # is THIS machine ready? (run first, anywhere)
    python omni_portable.py --export D:\omni_bundle   # build a portable bundle
    python omni_portable.py --import D:\omni_bundle   # restore one onto a fresh machine

The bundle contains secrets (cookie jars). It is exactly as sensitive as the accounts behind it --
treat it like a password file. `--export` refuses to write inside the repo so it cannot be committed
by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"

# Copied verbatim into a bundle. Kept explicit rather than a glob over state/: state/ holds thousands
# of files including hundreds of dated ledger backups, and a bundle that carries all of them is one
# nobody will move.
PORTABLE = [
    ("state/secrets", "dir", "captured sessions -- THE chat supply"),
    ("state/replay_check.json", "file", "which captures actually replay"),
    ("requirements.txt", "file", "python dependencies"),
    ("docs/VIDEO_SUPPLY_CONTRACT.md", "file", "the contract the film kit builds against"),
    ("TECHNOLOGY_TRANSFER.md", "file", "how the technology works"),
]

NEVER_COPY = [
    ("state/omniroute_password.bin", "DPAPI-sealed to this user+machine; re-seal on the new box"),
    ("state/automation_profiles", "Chrome cookie encryption is DPAPI-bound and Google may revoke on "
                                  "a move (DBSC); sign in again instead"),
    ("state/browser_profile", "same"),
    ("state/harvest_profile", "same"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------------------------------

def _which(name: str) -> str:
    p = shutil.which(name)
    return p or ""


def doctor() -> int:
    """Report whether this machine can run the rig. Never changes anything."""
    rows: list = []

    def check(label: str, ok: bool, detail: str, fatal: bool = True) -> None:
        rows.append((label, ok, detail, fatal))

    v = sys.version_info
    check("python >= 3.11", (v.major, v.minor) >= (3, 11),
          f"{v.major}.{v.minor}.{v.micro} at {sys.executable}")

    for mod in ("requests",):
        try:
            __import__(mod)
            check(f"module {mod}", True, "importable")
        except ImportError:
            check(f"module {mod}", False, "missing -- pip install -r requirements.txt")

    try:
        __import__("playwright")
        check("module playwright", True, "importable (optional)")
    except ImportError:
        check("module playwright", False, "missing (optional -- only Tier-2 DOM keygen needs it)",
              fatal=False)

    chrome = ""
    for cand in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(cand).exists():
            chrome = cand
            break
    chrome = chrome or _which("chrome")
    check("Chrome installed", bool(chrome), chrome or "not found -- capture and video both need it")

    ff = _which("ffmpeg")
    check("ffmpeg on PATH", bool(ff), ff or "not found -- film assembly needs it", fatal=False)

    # Supply, the thing that actually matters.
    secrets = STATE / "secrets"
    files = sorted(secrets.glob("session_*.json")) if secrets.exists() else []
    check("captured sessions present", bool(files),
          f"{len(files)} file(s) in state/secrets" if files
          else "none -- nothing to serve until a capture sweep runs or a bundle is imported")

    vf = STATE / "replay_check.json"
    ok_hosts: list = []
    if vf.exists():
        try:
            d = json.loads(vf.read_text(encoding="utf-8"))
            seen: dict = {}
            for r in d.get("results") or []:
                h = str(r.get("host") or "")
                if h and (h not in seen or r.get("verdict") == "REPLAY_OK"):
                    seen[h] = r.get("verdict")
            ok_hosts = sorted(h for h, x in seen.items() if x == "REPLAY_OK")
        except (ValueError, OSError):
            pass
    check("verdicted supply", bool(ok_hosts),
          f"{len(ok_hosts)} REPLAY_OK: {', '.join(ok_hosts)}" if ok_hosts
          else "no REPLAY_OK verdict -- run replay_check.py", fatal=False)

    # Ports. Free is good on a fresh machine; occupied is good on this one. Report, do not judge.
    busy = []
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=30)
        for port in (20128, 20130, 8189):
            if any(f":{port} " in l and "LISTENING" in l for l in (out.stdout or "").splitlines()):
                busy.append(port)
    except (OSError, subprocess.SubprocessError):
        pass
    check("ports", True, f"listening: {busy or 'none'} (20128 OmniRoute, 20130 chat pool, 8189 video)",
          fatal=False)

    width = max(len(r[0]) for r in rows)
    log("\nmachine readiness\n" + "-" * 64)
    fatals = 0
    for label, ok, detail, fatal in rows:
        mark = "ok  " if ok else ("FAIL" if fatal else "warn")
        if not ok and fatal:
            fatals += 1
        log(f"  {mark}  {label:<{width}}  {detail}")
    log("-" * 64)
    if fatals:
        log(f"{fatals} blocking problem(s). Fix those before starting anything.")
    else:
        log("no blocking problems. `python omni_supervisor.py --up` will bring the rig up.")
    log("\nwhat a fresh machine ALWAYS needs a human for, no matter what is imported:")
    log("  1. Chrome sign-ins for the video seats -- profiles cannot be copied (DPAPI + DBSC).")
    log("  2. Re-sealing the OmniRoute password into the local DPAPI vault.")
    log("  3. Re-connecting OmniRoute's own OAuth providers.")
    return 1 if fatals else 0


# --------------------------------------------------------------------------------------------------
# export / import
# --------------------------------------------------------------------------------------------------

def _copy(src: pathlib.Path, dst: pathlib.Path, kind: str) -> int:
    if kind == "dir":
        if not src.is_dir():
            return 0
        n = 0
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                out = dst / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
                n += 1
        return n
    if not src.is_file():
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return 1


def export(dest: pathlib.Path) -> int:
    dest = dest.resolve()
    try:
        dest.relative_to(ROOT)
        log(f"refusing to export inside the repo ({dest}). The bundle holds cookie jars and would be "
            f"one `git add -A` away from being published. Pick a path outside {ROOT}.")
        return 2
    except ValueError:
        pass

    dest.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceRoot": str(ROOT),
        "contains": [],
        "deliberatelyExcluded": [{"path": p, "why": w} for p, w in NEVER_COPY],
        "restoreSteps": [
            "git clone the repository on the new machine",
            "pip install -r requirements.txt",
            "python omni_portable.py --import <this bundle>",
            "python omni_portable.py --doctor        (expect the two human items to be listed)",
            "python omni_supervisor.py --up",
            "sign in to the video provider seats in Chrome by hand -- profiles cannot be copied",
            "re-seal the OmniRoute password locally, then re-connect OmniRoute's OAuth providers",
        ],
        "sensitivity": ("this bundle contains live cookie jars for free provider accounts. It is as "
                        "sensitive as those accounts. Do not commit it, do not email it."),
    }

    total = 0
    log(f"exporting to {dest}")
    for rel, kind, why in PORTABLE:
        n = _copy(ROOT / rel, dest / rel, kind)
        total += n
        manifest["contains"].append({"path": rel, "files": n, "why": why})
        log(f"  {rel:<40} {n:>4} file(s)   {why}")

    (dest / "BUNDLE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"\n{total} file(s) exported, plus BUNDLE_MANIFEST.json")
    log("NOT included, on purpose:")
    for p, w in NEVER_COPY:
        log(f"  {p:<40} {w}")
    log("\nThe chat pool will work fully on the new machine. The video seats will not until somebody "
        "signs in there -- that is a property of Chrome's credential storage, not of this bundle.")
    return 0


def _rotation_stamp(p: pathlib.Path) -> str:
    """`cookieRotatedAt` from a session file, or "" if absent/unreadable."""
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("cookieRotatedAt") or "")
    except (ValueError, OSError):
        return ""


def _would_regress(src: pathlib.Path, dst: pathlib.Path) -> bool:
    """True if importing `src` over `dst` would replace a NEWER cookie jar with an older one.

    This is the one way an import can actively destroy supply. Cookie rotation is written back into the
    session file on every successful call, so a bundle taken last week holds jars that the provider has
    since rotated away from. Restoring it looks like a successful restore and leaves dead sessions --
    the same class of failure as copying a Chrome profile.
    """
    if not dst.exists() or dst.name.startswith("."):
        return False
    a, b = _rotation_stamp(src), _rotation_stamp(dst)
    if not b:
        return False              # nothing on disk to lose
    if not a:
        return True               # bundle predates rotation tracking; disk copy is strictly better
    return a < b                  # ISO-8601 Z stamps compare correctly as strings


def do_import(src: pathlib.Path, force: bool = False) -> int:
    src = src.resolve()
    mf = src / "BUNDLE_MANIFEST.json"
    if not mf.is_file():
        log(f"no BUNDLE_MANIFEST.json in {src} -- that is not a bundle made by --export.")
        return 2
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    log(f"importing bundle created {manifest.get('createdAt')} from {manifest.get('sourceRoot')}")

    total, overwritten, skipped = 0, 0, []
    for entry in manifest.get("contains", []):
        rel = entry["path"]
        s = src / rel
        d = ROOT / rel
        if s.is_dir():
            for f in s.rglob("*"):
                if not f.is_file():
                    continue
                out = d / f.relative_to(s)
                if _would_regress(f, out) and not force:
                    skipped.append(f"{rel}/{f.relative_to(s)}")
                    continue
                if out.exists():
                    overwritten += 1
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
                total += 1
        elif s.is_file():
            if d.exists():
                overwritten += 1
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            total += 1
        log(f"  {rel:<40} restored")

    log(f"\n{total} file(s) restored ({overwritten} overwrote an existing file).")
    if skipped:
        log(f"\n{len(skipped)} session file(s) NOT restored: the copy already on disk has a NEWER "
            f"rotated cookie, and overwriting it would kill a live session.")
        for s_ in skipped[:10]:
            log(f"  kept local: {s_}")
        log("  (--force overrides this, which is almost never what you want)")
    log("\nStill required, by hand -- an import cannot do these:")
    for step in manifest.get("restoreSteps", [])[-3:]:
        log(f"  - {step}")
    log("\nNow run:  python omni_portable.py --doctor")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--doctor", action="store_true", help="check whether this machine is ready")
    g.add_argument("--export", metavar="DIR", help="build a portable bundle at DIR (outside the repo)")
    g.add_argument("--import", dest="imp", metavar="DIR", help="restore a bundle from DIR")
    ap.add_argument("--force", action="store_true",
                    help="on --import, overwrite session files even when the local copy has a newer "
                         "rotated cookie. Almost never correct.")
    a = ap.parse_args()

    if a.doctor:
        return doctor()
    if a.export:
        return export(pathlib.Path(a.export))
    return do_import(pathlib.Path(a.imp), force=a.force)


if __name__ == "__main__":
    sys.exit(main())
