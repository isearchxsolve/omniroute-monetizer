"""replay.py -- re-runs a recorded provider flow. No discovery, no guessing.

The operator's model, 2026-08-23:

    "the qi tester records the whole flow test cases and then it captures in the test cases
     and then the selenium starts from there replaying the recording so we do that way you
     take over the control you do the full automation and then record it in the skip so that
     the next time the skip runs it runs flawlessly"

drive.py is the recorder (the agent driving by hand, looking at real pages). This is the
replayer. It reads recordings/<slug>.json and performs exactly those steps.

WHY REPLAY BEATS THE DISCOVERY VERSION
--------------------------------------
MEASURED over a 50-provider discovery sweep, 2026-08-23: 26 of 50 died at
NO_SSO_CONTROL_FOUND -- the code guessed which URL held the login and guessed wrong. A further
6 died looking for a create-key control. Recorded steps cannot guess wrong: a real page was
looked at once, and the control that actually worked was written down.

MEASURED on reka the same day, using a recording of 6 steps: a real key was minted, copied
from the provider's own copy control, and PROVEN with an authenticated 200 OK plus real
generated text from api.reka.ai. That is the whole loop the operator asked for.

WHAT IS STILL REFUSED, EVERY TIME
---------------------------------
* CARD / CAPTCHA / PHONE walls stop that provider immediately. No solving, no retry, no
  hammering. One pass per provider, in the operator's words: "you reject, all paywall card
  requirements and all captcha. You do not hit them or hammer them."
* No password is ever typed. If Google asks for one, the robot profile's session is gone and
  the honest outcome is to stop and say so.
* Keys go only to the gitignored state/generated_keys.json. Console output is fingerprints.
* A provider counts as working ONLY when a real model returns real text. OmniRoute answering
  valid=True is not proof -- uncloseai passed that and every model 404'd.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drive as D  # noqa: E402
import harvest_free_keys as H  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
REC_DIR = ROOT / "recordings"
REPORT = ROOT / "state" / "harvest" / "replay_report.json"

# A masked key chip, e.g. "6de00606••••••••2a98". On providers that never show the full key in
# the DOM, this chip is itself the copy-to-clipboard control.
MASKED_CHIP_RE = re.compile(r"^[0-9a-zA-Z]{4,}[•*·\.]{3,}[0-9a-zA-Z]{3,}$")


def recordings(only: Optional[list[str]]) -> list[dict]:
    out = []
    for p in sorted(REC_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not d.get("steps"):
            continue
        if only and d.get("slug") not in only:
            continue
        out.append(d)
    return out


def resolve_wait(page, role, name, css, frame, exact=False, ms: int = 18000):
    """Wait for a recorded control to exist, then return it.

    MEASURED on reka 2026-08-23: replay failed at step 1 with "control gone: name='API Keys'"
    even though the link was plainly there -- domcontentloaded fires before the SPA paints its
    sidebar. This is a WAIT, not a retry: the action is attempted once, after the page has
    actually rendered the thing the recording named.
    """
    waited = 0
    while True:
        loc = D.resolve(page, role, name, css, frame, exact)
        if loc is not None:
            return loc
        if waited >= ms:
            return None
        page.wait_for_timeout(1000)
        waited += 1000


def click_masked_key(page, index: int, ms: int = 18000) -> bool:
    waited = 0
    while True:
        for fr in D.frames_of(page):
            chips = []
            try:
                for b in fr.get_by_role("button").all()[:120]:
                    if not b.is_visible():
                        continue
                    t = re.sub(r"\s+", "", (b.inner_text(timeout=800) or ""))
                    if MASKED_CHIP_RE.match(t):
                        chips.append(b)
            except Exception:
                continue
            if len(chips) > index:
                chips[index].click(timeout=8000)
                return True
        if waited >= ms:
            return False
        page.wait_for_timeout(1000)
        waited += 1000


def run_step(s: "D.Sess", step: dict, slug: str) -> tuple[bool, str]:
    page = s.page()
    action = step.get("action")

    w = D.walls(D.body_text(page), page)
    if w:
        return False, f"{'+'.join(w)}_REFUSED"

    if action == "goto":
        page.goto(step["url"], wait_until="domcontentloaded", timeout=45000)
    elif action == "click":
        loc = resolve_wait(page, step.get("role"), step.get("name"), step.get("css"),
                           step.get("frame"), bool(step.get("exact")))
        if loc is None:
            return False, f"control gone: role={step.get('role')} name={step.get('name')!r}"
        if step.get("popup"):
            try:
                with s.ctx.expect_page(timeout=12000) as pi:
                    loc.click(timeout=10000)
                pi.value.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
        else:
            loc.click(timeout=10000)
    elif action == "click_masked_key":
        if not click_masked_key(page, int(step.get("index", 0))):
            return False, "no masked key chip on the page"
    elif action == "fill":
        loc = resolve_wait(page, None, None, step["css"], None)
        if loc is None:
            return False, f"input gone: {step['css']}"
        if (loc.get_attribute("type") or "").lower() == "password":
            return False, "REFUSED: replay never types into a password field"
        loc.fill(step.get("value", ""), timeout=8000)
    elif action == "press":
        page.keyboard.press(step["key"])
    elif action == "google":
        rc = D.cmd_google(s, step.get("email"))
        if rc != 0:
            return False, f"google step failed rc={rc}"
    elif action in ("clipboard_key", "copy"):
        sentinel = ""
        if action == "copy":
            # Mark the clipboard BEFORE the copy click, so a read that beats the page's write is
            # caught instead of returning the previous provider's key. See D.poison_clipboard.
            sentinel = D.poison_clipboard(page)
            loc = resolve_wait(page, step.get("role"), step.get("name"), step.get("css"),
                               step.get("frame"), bool(step.get("exact")))
            if loc is None:
                return False, f"copy control gone: name={step.get('name')!r}"
            loc.click(timeout=8000)
            page.wait_for_timeout(600)
        rc = D.cmd_clip(s, slug, sentinel=sentinel)
        if rc != 0:
            return False, "clipboard held no key"
    elif action == "read_key_from_page":
        got = D.wait_for_key(page)
        if not got:
            return False, "no key-shaped text on the page"
        print(f"[+] key from page: {D.fingerprint(got)}", flush=True)
        D.store_key(slug, got)
    elif action == "wire":
        return True, "wire handled after replay"
    else:
        return False, f"unknown action {action!r}"

    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        page.wait_for_timeout(1000)
    return True, "ok"


def replay_one(s: "D.Sess", rec: dict, api, dry_run: bool) -> dict:
    slug = rec["slug"]
    row: dict[str, Any] = {"provider": slug, "steps": len(rec["steps"])}
    print(f"\n[*] {slug}: replaying {len(rec['steps'])} step(s)", flush=True)

    if rec.get("entry_url"):
        try:
            s.page().goto(rec["entry_url"], wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            row.update(ok=False, stage="entry", detail=f"{type(exc).__name__}")
            return row

    for i, step in enumerate(rec["steps"], 1):
        ok, detail = run_step(s, step, slug)
        print(f"    {i:>2}. {step['action']:<18} {'ok' if ok else 'FAILED: ' + detail}",
              flush=True)
        if not ok:
            if detail.endswith("_REFUSED"):
                row.update(ok=False, stage="refused", detail=detail)
            else:
                row.update(ok=False, stage=f"step{i}", detail=detail)
            return row

    store = {}
    kf = ROOT / "state" / "generated_keys.json"
    if kf.exists():
        store = json.loads(kf.read_text(encoding="utf-8"))
    key = store.get(slug)
    if not key:
        row.update(ok=False, stage="no-key", detail="replay finished but no key was captured")
        return row
    row["key"] = D.fingerprint(key)

    if dry_run:
        row.update(ok=True, stage="captured", detail="--dry-run: not wired")
        return row

    res = H.wire(api, slug, slug, key)
    row.update(ok=bool(res.get("ok")), stage=res.get("stage"), detail=res.get("detail"),
               deleted=res.get("deleted"))
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated slugs")
    ap.add_argument("--dry-run", action="store_true", help="capture keys but do not wire")
    ap.add_argument("--list", action="store_true", help="show recordings and exit")
    args = ap.parse_args()

    D.RECORDING_ENABLED = False        # replaying must never edit the recording
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    recs = recordings(only)
    if args.list or not recs:
        print(f"recordings in {REC_DIR}: {len(recs)}")
        for r in recs:
            print(f"  {r['slug']:<24} {len(r['steps'])} steps   {r.get('entry_url', '')}")
        if not recs:
            print("  (none yet -- record one with drive.py)")
        return 0

    api = None
    if not args.dry_run:
        api = OmniRouteAPI(password=resolve_password())
        if not api.login():
            print("[-] OmniRoute login failed; nothing changed")
            return 2

    s = D.Sess()
    rows = []
    try:
        for rec in recs:
            try:
                rows.append(replay_one(s, rec, api, args.dry_run))
            except Exception as exc:
                rows.append({"provider": rec["slug"], "ok": False, "stage": "crash",
                             "detail": f"{type(exc).__name__}: {exc}"})
    finally:
        s.close()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    won = [r for r in rows if r.get("ok")]
    refused = [r for r in rows if r.get("stage") == "refused"]
    print("\n" + "=" * 74)
    print(f"replayed          : {len(rows)}")
    print(f"key captured/wired: {len(won)}")
    for r in won:
        print(f"    {r['provider']:<22} {r.get('key', '')}  {r.get('stage')}")
    print(f"walked away from  : {len(refused)}   (card / CAPTCHA / phone -- never solved)")
    for r in refused:
        print(f"    {r['provider']:<22} {r['detail']}")
    others = [r for r in rows if not r.get("ok") and r.get("stage") != "refused"]
    if others:
        print(f"stopped earlier   : {len(others)}")
        for r in others:
            print(f"    {r['provider']:<22} {r.get('stage')}: {str(r.get('detail'))[:70]}")
    print(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
