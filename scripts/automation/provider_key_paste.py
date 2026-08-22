#!/usr/bin/env python3
"""
provider_key_paste.py -- take an API key the operator copied BY HAND, prove it works, save it.

WHY THIS EXISTS
---------------
Measured 2026-08-22: Google refuses sign-in inside a Playwright-launched Chrome
("Couldn't sign you in / This browser or app may not be secure"). Playwright starts Chrome
with automation switches set and Google rejects that outright.

Disguising it is off the table. Defeating an anti-automation check on a Google account is
exactly the class of trick that gets an account flagged, and this operator's four accounts
have already been damaged once (see MASTER_WORKLOG.md #1017-#1031).

But for an API key, a browser was never the point. The browser was only ever a way to fetch
a string. So for any Google-gated or otherwise blocked provider, the operator opens the page
in THEIR OWN Chrome -- by hand, no automation anywhere near it -- copies the key, and pastes
it here once. From then on the automation uses the key over plain HTTP and needs no browser
at all, forever.

This is not a workaround or a degraded path. For keys it is strictly better: fewer moving
parts, nothing automated touching the operator's browser, and no session to be revoked.

DISCIPLINE
----------
* Anti-pattern #7: a pasted key is a CANDIDATE until it returns HTTP 200 from the provider's
  OWN upstream endpoint. This script performs that check and refuses to call it verified
  otherwise. `verified: false` is recorded honestly, not hidden.
* The key is never echoed to the screen, never printed, never logged. Terminal input is
  hidden (getpass). Every message shows a redacted fingerprint only.
* Keys land in `state/generated_keys.json`, which is gitignored (`.gitignore` line 3).
  The existing file is backed up before every write.

USAGE
-----
    python provider_key_paste.py                    # menu
    python provider_key_paste.py --provider kie
    python provider_key_paste.py --recheck          # re-verify everything already saved
    python provider_key_paste.py --list             # what is saved, redacted
"""

from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("[PROBLEM] the 'requests' package is missing from this Python.")
    print("[info]    Use the hermes venv interpreter, which has it.")
    raise SystemExit(3)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KEYS_FILE = PROJECT_ROOT / "state" / "generated_keys.json"

# `verify` is the provider's OWN endpoint -- never OmniRoute. A key that only works through
# OmniRoute proves nothing about the key.
#   auth: "bearer"    -> Authorization: Bearer <key>
#         "x-api-key" -> x-api-key: <key>
#         "query"     -> ?key=<key>
PROVIDERS = {
    "aistudio": {
        "omniroute_provider": "vertex",
        "models": 3,
        "where": "https://aistudio.google.com/apikey",
        "how": "Click 'Create API key', pick a project, then copy the key (starts with AIza).",
        "verify": "https://generativelanguage.googleapis.com/v1beta/models",
        "auth": "query",
        "expect": "AIza",
    },
    "kie": {
        "omniroute_provider": "kie",
        "models": 16,
        "where": "https://kie.ai/api-key",
        "how": "Create a key on that page and copy it.",
        "verify": "https://api.kie.ai/api/v1/chat/credit",
        "auth": "bearer",
        "expect": "",
    },
    "segmind": {
        "omniroute_provider": "segmind",
        "models": 5,
        "where": "https://cloud.segmind.com/console/api-keys",
        "how": "Create a key in the console and copy it (starts with SG_).",
        "verify": "https://api.segmind.com/v1/credits",
        "auth": "x-api-key",
        "expect": "SG_",
    },
    "novita": {
        "omniroute_provider": "novita",
        "models": 2,
        "where": "https://novita.ai/settings/key-management",
        "how": "Add a key under Key Management and copy it.",
        "verify": "https://api.novita.ai/v3/user",
        "auth": "bearer",
        "expect": "",
    },
    "leonardo": {
        "omniroute_provider": "leonardo",
        "models": 1,
        "where": "https://app.leonardo.ai/api-access",
        "how": "Create an API key. If it demands a card, STOP -- that is out of scope.",
        "verify": "https://cloud.leonardo.ai/api/rest/v1/me",
        "auth": "bearer",
        "expect": "",
    },
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def redact(secret: str) -> str:
    """A fingerprint that identifies a key without revealing it. Safe for logs and worklogs."""
    if not secret:
        return "<empty>"
    s = secret.strip()
    if len(s) <= 8:
        return f"<{len(s)} chars, too short to fingerprint>"
    return f"{s[:4]}...{s[-2:]} ({len(s)} chars)"


def _load() -> dict:
    if not KEYS_FILE.exists():
        return {}
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _say("PROBLEM", f"could not read {KEYS_FILE.name}: {type(exc).__name__}")
        _say("info", "refusing to overwrite a file I cannot parse. Nothing was changed.")
        raise SystemExit(4)


def _save(data: dict) -> None:
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if KEYS_FILE.exists():
        backup = KEYS_FILE.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(KEYS_FILE, backup)
        _say("info", f"backed up existing keys to {backup.name}")
    KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _say("ok", f"saved to {KEYS_FILE} (this file is gitignored, it is never committed)")


def _body_verdict(resp) -> tuple[bool | None, str]:
    """Some providers answer HTTP 200 and put the REAL status inside the JSON body.

    MEASURED 2026-08-22, and this is a trap that would have broken anti-pattern #7:

        GET https://api.kie.ai/api/v1/chat/credit  with a garbage bearer token
        -> HTTP 200
        -> {"code":401,"msg":"Unauthorized - Authentication failed..."}

    A status-code-only check certifies that fake key as VERIFIED. Any future provider added
    to this file must be tested with a deliberately invalid key before it is trusted; if a
    bad key yields 200, the body is the only real signal.

    Returns (True, "") body looks fine, (False, reason) body reports an error,
    (None, "") cannot judge from the body -- fall back to the HTTP status.

    Only the provider's numeric code is reported, never its message text: that string is
    third-party controlled and has no business being pasted into our logs verbatim.
    """
    try:
        payload = resp.json()
    except ValueError:
        return None, ""
    if not isinstance(payload, dict):
        return None, ""

    code = payload.get("code")
    if isinstance(code, bool):
        code = None
    if isinstance(code, int) and code not in (0, 200):
        return False, f"HTTP 200 but the provider's body reports code={code}"

    if payload.get("success") is False:
        return False, "HTTP 200 but the provider's body reports success=false"

    for field in ("error", "errors", "detail"):
        if payload.get(field):
            return False, f"HTTP 200 but the provider's body contains '{field}'"

    return True, ""


def verify(name: str, key: str) -> tuple[bool, int | None, str]:
    """Ask the PROVIDER'S OWN endpoint whether this key is real.

    Returns (verified, http_status, note). A 200 alone is NOT enough -- see `_body_verdict`.
    Anything else is reported as-is: 401/403 means the key is wrong, 402/429 usually means the
    account is out of credit, which is out of scope by the operator's standing policy.
    """
    spec = PROVIDERS[name]
    url, auth = spec["verify"], spec["auth"]
    headers, params = {}, {}

    if auth == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    elif auth == "x-api-key":
        headers["x-api-key"] = key
    elif auth == "query":
        params["key"] = key

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as exc:
        return False, None, f"could not reach the provider ({type(exc).__name__})"

    code = resp.status_code
    if code == 200:
        body_ok, why = _body_verdict(resp)
        if body_ok is False:
            return False, code, why
        return True, code, "provider accepted the key"
    if code in (401, 403):
        return False, code, "provider rejected the key (wrong, expired, or not enabled)"
    if code in (402, 429):
        return False, code, "key may be valid but the account is out of credit or rate-limited"
    return False, code, f"unexpected response {code}"


def do_one(name: str, key: str | None = None) -> bool:
    spec = PROVIDERS[name]
    print()
    print("-" * 74)
    print(f"  {name.upper()}   ({spec['models']} models in OmniRoute"
          f" -> provider id '{spec['omniroute_provider']}')")
    print(f"  Open in YOUR OWN Chrome : {spec['where']}")
    print(f"  Then                    : {spec['how']}")
    print()

    if key is None:
        print("  Paste the key and press Enter. It will NOT appear on screen -- that is")
        print("  deliberate, so it never lands in a log or a screenshot.")
        key = getpass.getpass("  key: ").strip()

    if not key:
        _say("YOU", "nothing pasted. Skipped.")
        return False

    expect = spec.get("expect")
    if expect and not key.startswith(expect):
        _say("YOU", f"heads up: {name} keys normally start with '{expect}' and this one does "
                    f"not ({redact(key)}). Checking it anyway.")

    _say("info", f"asking {name}'s own server whether {redact(key)} is real...")
    ok, code, note = verify(name, key)

    data = _load()
    data[name] = {
        "key": key,
        "verified": ok,
        "verify_http": code,
        "verify_note": note,
        "verify_url": spec["verify"],
        "omniroute_provider": spec["omniroute_provider"],
        "source": "operator_paste",
        "updated_at": _now(),
    }
    _save(data)

    if ok:
        _say("ok", f"VERIFIED: {name} returned HTTP 200. This is a real, working key.")
    else:
        shown = code if code is not None else "no response"
        _say("PROBLEM", f"NOT VERIFIED: {name} returned {shown} -- {note}")
        _say("info", "Saved anyway, marked verified=false, so nothing downstream treats it")
        _say("info", "as working. Fix or re-paste, or tell me to drop this provider.")
    return ok


def do_list() -> int:
    data = _load()
    known = [(k, v) for k, v in data.items()
             if isinstance(v, dict) and k in PROVIDERS]
    print()
    print("  Video-provider keys currently saved:")
    if not known:
        print("    (none yet)")
    for k, v in sorted(known):
        state = "VERIFIED" if v.get("verified") is True else "not verified"
        print(f"    {k:<10} {state:<13} {redact(v.get('key', ''))}"
              f"  http={v.get('verify_http')}")
    print()
    print("  What is NOT claimed: that a verified key is wired into OmniRoute, or that it")
    print("  returns real video. Those are separate steps with separate proof.")
    print()
    return 0


def do_recheck() -> int:
    data = _load()
    todo = [k for k in PROVIDERS if isinstance(data.get(k), dict) and data[k].get("key")]
    if not todo:
        _say("info", "no saved video-provider keys to re-check.")
        return 0
    changed = 0
    for name in todo:
        key = data[name]["key"]
        ok, code, note = verify(name, key)
        was = data[name].get("verified")
        data[name].update({"verified": ok, "verify_http": code, "verify_note": note,
                           "updated_at": _now()})
        mark = "ok" if ok else "PROBLEM"
        _say(mark, f"{name:<10} http={code} {note}")
        if was != ok:
            changed += 1
    _save(data)
    _say("info", f"{len(todo)} checked, {changed} changed state.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", help=f"one of: {', '.join(sorted(PROVIDERS))}")
    ap.add_argument("--list", action="store_true", help="show saved keys, redacted")
    ap.add_argument("--recheck", action="store_true", help="re-verify all saved keys")
    args = ap.parse_args(argv)

    if args.list:
        return do_list()
    if args.recheck:
        return do_recheck()

    if args.provider:
        if args.provider not in PROVIDERS:
            _say("PROBLEM", f"unknown provider '{args.provider}'")
            _say("info", f"known: {', '.join(sorted(PROVIDERS))}")
            return 2
        return 0 if do_one(args.provider) else 1

    # Interactive menu.
    print()
    print("=" * 74)
    print("  PASTE AN API KEY")
    print("=" * 74)
    print()
    print("  For providers that will not let an automated browser sign in.")
    print("  You open the page in YOUR OWN Chrome and copy the key. Nothing")
    print("  automated goes near your browser -- you do the copying.")
    print()
    print("  I then ask that provider's own server whether the key is real, and")
    print("  only call it working if the answer is a genuine 200.")
    print()

    names = sorted(PROVIDERS, key=lambda n: -PROVIDERS[n]["models"])
    saved = _load()
    for i, n in enumerate(names, 1):
        cur = saved.get(n)
        state = ""
        if isinstance(cur, dict) and cur.get("key"):
            state = "  [VERIFIED]" if cur.get("verified") else "  [saved, not verified]"
        print(f"    {i}. {n:<10} {PROVIDERS[n]['models']:>2} models{state}")
    print(f"    {len(names) + 1}. show what is saved")
    print("    0. quit")
    print()

    choice = input("  Pick a number: ").strip()
    if choice in ("0", "", "q"):
        _say("info", "nothing changed.")
        return 0
    if choice == str(len(names) + 1):
        return do_list()
    try:
        pick = names[int(choice) - 1]
    except (ValueError, IndexError):
        _say("PROBLEM", "that was not one of the numbers. Nothing changed.")
        return 2

    ok = do_one(pick)
    print()
    _say("info", "Run this again for the next provider, or tell the agent to wire what")
    _say("info", "is verified into OmniRoute and prove it returns real video.")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print("[info] stopped. Nothing changed.")
        raise SystemExit(130)
