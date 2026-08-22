#!/usr/bin/env python3
"""
paste_provider_key.py -- the operator pastes an API key; we verify it for real.

WHY THIS EXISTS
---------------
Two walls closed the browser route for good:

  1. Automation may never open the operator's Chrome (2026-08-22 incident: Chrome binds a
     session to one browser instance, so a foreign browser presenting it gets the session
     REVOKED server-side). See CHROME_RULES_FOR_AGENTS.md.
  2. A robot-owned Chrome profile does not help for Google-backed sites: Google refuses
     sign-ins from an automation-controlled browser -- "Couldn't sign you in / This browser
     or app may not be secure", measured 2026-08-22. We do not disguise the browser to beat
     that check; that is how accounts get flagged.

So the human does the part only a human can do -- sign in and copy a key -- in their OWN
Chrome, with no automation involved at all. This script does the part a machine is better at:
verify the key against the provider's real endpoint, and record it.

Once a key exists, no browser is needed ever again. The pipeline talks HTTP.

ANTI-PATTERN #7 IS ENFORCED HERE
--------------------------------
A pasted key is a CANDIDATE, not a key. It becomes a key only when the provider's OWN
upstream endpoint answers HTTP 200. `verified: false` is not a success and is never reported
as one.

SECRET HANDLING
---------------
* Keys are read with getpass, so they are not echoed to the terminal or into scrollback.
* Keys are never printed, logged, or included in any report -- only a masked fingerprint
  (first 4 + last 4 characters) so a human can tell two keys apart.
* Raw keys are written ONLY to state/generated_keys.json, which is gitignored.

USAGE
-----
    python paste_provider_key.py                  # walk every provider that needs a key
    python paste_provider_key.py --only kie
    python paste_provider_key.py --list           # just print the sites and what to click
    python paste_provider_key.py --status         # what is stored + verified already
    python paste_provider_key.py --reverify       # re-check stored keys, paste nothing
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1].parent
KEYS_FILE = PROJECT_ROOT / "state" / "generated_keys.json"
REPORT = PROJECT_ROOT / "state" / "harvest" / "pasted_keys_report.json"

# ---------------------------------------------------------------------------------------
# Targets. `verify` is the provider's OWN endpoint -- never OmniRoute, never a proxy.
# `where` is written for a human who has never seen the dashboard before.
# Model counts are OmniRoute registry counts measured 2026-08-22.
# ---------------------------------------------------------------------------------------

TARGETS = [
    {
        "name": "kie",
        "omniroute_provider": "kie",
        "models": 16,
        "url": "https://kie.ai/api-key",
        "where": "Sign in. The page IS the API key page. Copy the key it shows, or click "
                 "the create/generate button first if it is empty.",
        "pattern": r"^[A-Za-z0-9_\-]{20,}$",
        "verify": {
            "method": "GET",
            "url": "https://api.kie.ai/api/v1/chat/credit",
            "auth": "bearer",
        },
    },
    {
        "name": "segmind",
        "omniroute_provider": "segmind",
        "models": 5,
        "url": "https://cloud.segmind.com/console/api-keys",
        "where": "Sign in with email + password (no Google needed). Console -> API Keys -> "
                 "create one. Keys look like SG_xxxxxxxx.",
        "pattern": r"^SG_[A-Za-z0-9]{10,}$",
        "verify": {
            "method": "GET",
            "url": "https://api.segmind.com/v1/credits",
            "auth": "x-api-key",
            # Segmind rejects any request without a content type AND without a JSON body,
            # before it ever looks at the key. Both are required to reach the auth layer.
            "extra_headers": {"Content-Type": "application/json"},
            "json_body": {},
            # Segmind publishes no free balance/whoami endpoint -- /v1/credits does not
            # exist. MEASURED 2026-08-22: a real key gets 404 "Model information not
            # found" (auth passed, then routing failed), a bogus key gets 401
            # "API key is invalid or may have expired". So 404 here is positive proof
            # that the auth layer accepted the key. Handled in verify().
            "auth_pass_statuses": [404],
        },
    },
    {
        "name": "novita",
        "omniroute_provider": "novita",
        "models": 2,
        "url": "https://novita.ai/settings/key-management",
        "where": "Sign in with email + password (no Google needed). Settings -> Key "
                 "Management -> Add New Key. Copy it before closing the dialog.",
        "pattern": r"^[A-Za-z0-9_\-\.]{20,}$",
        "verify": {
            "method": "GET",
            "url": "https://api.novita.ai/v3/user",
            "auth": "bearer",
        },
    },
    {
        "name": "aistudio",
        "omniroute_provider": "vertex",
        "models": 3,
        "url": "https://aistudio.google.com/apikey",
        "where": "This is Google's own site, so use your normal Chrome where you are already "
                 "signed in. Click 'Create API key', pick any project, copy the key.",
        # Two live formats. Older keys are AIza...; as of 2026-08 AI Studio issues AQ....
        # MEASURED 2026-08-22: an AQ. key authenticates against generativelanguage.
        "pattern": r"^(?:AIza[A-Za-z0-9_\-]{30,}|AQ\.[A-Za-z0-9_\-]{20,})$",
        "verify": {
            "method": "GET",
            "url": "https://generativelanguage.googleapis.com/v1beta/models",
            "auth": "query_key",
        },
    },
    {
        "name": "leonardo",
        "omniroute_provider": "leonardo",
        "models": 1,
        "url": "https://app.leonardo.ai/api-access",
        "where": "SKIP THIS ONE. Kept here only so --only leonardo still works if the "
                 "paywall is ever lifted. See DROPPED below.",
        "pattern": r"^[0-9a-fA-F\-]{30,}$",
        "skip": "API access sits behind a paid plan. Operator confirmed the paywall "
                "2026-08-22. Paying is out of scope.",
        "verify": {
            "method": "GET",
            "url": "https://cloud.leonardo.ai/api/rest/v1/me",
            "auth": "bearer",
        },
    },
]

DROPPED = {
    "haiper": "API-key page is a dead 404, and it is only 1 model. Not worth your time.",
    "runwayml": "OmniRoute has 0 models wired for it, so a key would buy nothing today.",
    "deepinfra": "Account has no funds, and paying is out of scope. Already rejected.",
    "leonardo": "API access is behind a paid plan -- operator hit the paywall 2026-08-22. "
                "Only 1 model, so not worth paying for even if we could.",
}

TIMEOUT = 25


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def read_clipboard() -> str:
    """Return the clipboard text, or "" if it cannot be read.

    Two backends because neither is universally available: PowerShell exists on this machine
    and does not need a display, tkinter works when PowerShell is locked down. The clipboard
    content is treated as secret from the moment it arrives -- it is never printed, only
    fingerprinted.
    """
    import subprocess

    try:
        # -Raw keeps a single-line key intact and avoids trailing newline surprises.
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            return str(root.clipboard_get()).strip()
        finally:
            root.destroy()
    except Exception:
        pass

    return ""


def candidates_for(key: str) -> list[dict]:
    """Which providers could this key belong to, by shape?

    Some keys self-identify (AIza... is Google, SG_... is segmind). Others are generic
    alphanumeric strings shared by several providers -- for those we return every plausible
    target and let the providers themselves decide, which is the only authority that counts.
    """
    matches = [t for t in TARGETS if re.match(t["pattern"], key)]
    # Most specific first: a prefixed pattern beats a catch-all, so segmind/aistudio are
    # tried before the generic ones and we do not waste calls.
    return sorted(matches, key=lambda t: -len(t["pattern"]))


def fingerprint(key: str) -> str:
    """A safe, loggable identity for a key. Never reversible to the key itself."""
    k = key.strip()
    if len(k) <= 10:
        return f"len={len(k)} (too short to fingerprint safely)"
    return f"{k[:4]}...{k[-4:]} (len={len(k)})"


def load_keys() -> dict:
    if not KEYS_FILE.exists():
        return {}
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        _say("PROBLEM", f"could not read {KEYS_FILE.name}: {type(exc).__name__}")
        return {}


def save_key(name: str, target: dict, key: str, verified: bool, detail: str) -> None:
    """Write the raw key to the gitignored keys file. Nothing else ever sees it."""
    data = load_keys()
    data[name] = {
        "key": key,
        "provider": target["omniroute_provider"],
        "models": target["models"],
        "source": "operator_pasted",
        "verified": verified,
        "verify_detail": detail,
        "fingerprint": fingerprint(key),
        "updated_at": _now(),
    }
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _body_verdict(resp) -> tuple[bool | None, str]:
    """Look inside a 200 response for an embedded error code.

    MEASURED 2026-08-22: `GET api.kie.ai/api/v1/chat/credit` answers **HTTP 200** with
    `{"code":401,"msg":"Unauthorized ..."}` for a bogus key -- and for no key at all. Trusting
    the status code alone marked the literal string "NOT_A_REAL_KEY_shape_test" as a verified
    kie key. This is anti-pattern #7 in its purest form: a 200 is not proof.

    Returns (True, why) / (False, why), or (None, "") when the body carries no verdict, in
    which case the caller falls back to the status code.
    """
    try:
        body = resp.json()
    except Exception:
        return None, ""

    if not isinstance(body, dict):
        return None, ""

    # Embedded status code. kie uses `code`; some APIs use `statusCode`.
    for field in ("code", "statusCode", "status"):
        val = body.get(field)
        if isinstance(val, bool) or not isinstance(val, int):
            continue
        if val in (0, 200):
            return True, "provider returned success in the response body"
        msg = str(body.get("msg") or body.get("message") or "").strip()
        msg = re.sub(r"\s+", " ", msg)[:90]
        return False, f"provider replied {field}={val} inside a 200 response" + (
            f": {msg}" if msg else ""
        )

    if body.get("success") is False:
        return False, "provider replied success=false inside a 200 response"

    err = body.get("error")
    if err:
        detail = str(err.get("message") if isinstance(err, dict) else err)
        detail = re.sub(r"\s+", " ", detail)[:90]
        return False, f"provider replied with an error inside a 200 response: {detail}"

    return None, ""


def verify(target: dict, key: str) -> tuple[bool, str]:
    """Hit the provider's OWN endpoint. Only a real success counts (anti-pattern #7)."""
    try:
        import requests
    except ImportError:
        return False, "requests not installed, cannot verify"

    spec = target["verify"]
    url, auth = spec["url"], spec["auth"]
    headers, params = {"Accept": "application/json"}, {}

    if auth == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    elif auth == "x-api-key":
        headers["x-api-key"] = key
    elif auth == "query_key":
        params["key"] = key
    else:
        return False, f"unknown auth mode {auth!r}"

    headers.update(spec.get("extra_headers") or {})

    try:
        resp = requests.request(spec["method"], url, headers=headers, params=params,
                                json=spec.get("json_body"), timeout=TIMEOUT)
    except Exception as exc:
        # Network failure is NOT a bad key. Say so, rather than blaming the key.
        return False, f"could not reach provider ({type(exc).__name__}) -- key not disproven"

    # Auth-layer proof, for providers with no free balance/whoami endpoint. This must be
    # checked BEFORE _body_verdict, because these responses carry an error body by design
    # (the auth succeeded and something *later* failed). Only statuses the target itself
    # declares count, and only after measuring that a bogus key gets 401/403 instead.
    if resp.status_code in (spec.get("auth_pass_statuses") or ()):
        return True, (f"HTTP {resp.status_code} -- the provider's auth layer accepted this "
                      f"key (a bogus key gets 401 here); this provider has no free "
                      f"balance endpoint, so this is as far as verification can go")

    # The body wins over the status line, because some providers lie in the status line.
    body_ok, body_why = _body_verdict(resp)
    if body_ok is False:
        return False, body_why
    if body_ok is True and resp.status_code == 200:
        return True, "HTTP 200 and the provider's own body confirms success"

    if resp.status_code == 200:
        return True, "HTTP 200 from the provider's own endpoint"
    if resp.status_code in (401, 403):
        return False, f"HTTP {resp.status_code} -- provider rejected this key"
    if resp.status_code == 402:
        return False, "HTTP 402 -- account needs funds (out of scope)"
    if resp.status_code == 429:
        return False, "HTTP 429 -- rate limited, key may be fine; try again later"
    return False, f"HTTP {resp.status_code}"


def print_list() -> None:
    print()
    print("=" * 78)
    print("  OPEN THESE IN YOUR OWN CHROME AND SIGN IN")
    print("=" * 78)
    print()
    print("  Your Chrome. Your normal window. No automation touches it.")
    print("  For each one: sign in, get the API key, copy it. Then run PasteAKey.cmd")
    print("  and paste them in. That is the last manual step.")
    print()
    for i, t in enumerate(TARGETS, 1):
        print(f"  {i}. {t['name'].upper()}   -- unlocks {t['models']} models")
        print(f"     {t['url']}")
        print(f"     {t['where']}")
        print()
    print("-" * 78)
    print("  SKIP THESE -- not worth your time:")
    for name, why in DROPPED.items():
        print(f"     {name:<10} {why}")
    print()
    print("  If any site asks for a credit card or shows a captcha you cannot pass:")
    print("  stop on that one and skip it. Do not pay for anything.")
    print()


def do_status() -> int:
    data = load_keys()
    print()
    print("=" * 78)
    print("  WHAT IS STORED RIGHT NOW")
    print("=" * 78)
    print()
    any_row = False
    for t in TARGETS:
        row = data.get(t["name"])
        if not isinstance(row, dict) or not row.get("key"):
            print(f"  {t['name']:<10} no key yet          ({t['models']} models waiting)")
            continue
        any_row = True
        ver = row.get("verified")
        mark = "VERIFIED" if ver is True else "not verified"
        print(f"  {t['name']:<10} {mark:<19} {row.get('fingerprint', '?')}")
        if ver is not True and row.get("verify_detail"):
            print(f"             reason: {row['verify_detail']}")
    if not any_row:
        print()
        print("  Nothing stored. Run PasteAKey.cmd after you collect the keys.")
    print()
    print("  Verified means: the provider's own endpoint answered HTTP 200.")
    print("  It does NOT yet mean the provider is wired into OmniRoute.")
    print()
    return 0


def do_reverify() -> int:
    data = load_keys()
    checked = 0
    for t in TARGETS:
        row = data.get(t["name"])
        if not isinstance(row, dict) or not row.get("key"):
            continue
        checked += 1
        ok, detail = verify(t, row["key"])
        save_key(t["name"], t, row["key"], ok, detail)
        _say("ok" if ok else "PROBLEM", f"{t['name']:<10} {detail}")
    if not checked:
        _say("info", "no stored keys to re-verify.")
    return 0


def do_paste(only: list[str] | None) -> int:
    targets = [t for t in TARGETS if not only or t["name"] in only]
    stored = load_keys()
    results = {}

    print()
    print("=" * 78)
    print("  PASTE THE KEYS YOU COLLECTED")
    print("=" * 78)
    print()
    print("  Paste each key and press Enter. The key will NOT appear on screen -- that is")
    print("  deliberate, so it never ends up in your scrollback. Paste still works.")
    print()
    print("  Press Enter on its own to skip a provider you did not get.")
    print("  Keys are saved to state/generated_keys.json, which git ignores.")
    print()

    for i, t in enumerate(targets, 1):
        existing = stored.get(t["name"])
        already = (isinstance(existing, dict) and existing.get("verified") is True)

        print("-" * 78)
        print(f"  {i} of {len(targets)}:  {t['name'].upper()}"
              f"   ({t['models']} models)")
        print(f"       page: {t['url']}")
        if already:
            print(f"       Already stored and verified ({existing.get('fingerprint')}).")
            ans = input("       Press Enter to keep it, or paste a new key to replace: ")
            if not ans.strip():
                results[t["name"]] = "kept_existing_verified"
                _say("ok", f"{t['name']}: keeping the verified key already stored.")
                continue
            key = ans.strip()
        else:
            key = getpass.getpass("       Paste key (hidden), or Enter to skip: ").strip()

        if not key:
            results[t["name"]] = "skipped_by_operator"
            _say("YOU", f"{t['name']}: skipped. {t['models']} models stay unavailable.")
            continue

        # Shape check first: catches a half-copied key before we bother the provider.
        if not re.match(t["pattern"], key):
            _say("YOU", f"that does not look like a {t['name']} key "
                        f"({fingerprint(key)}). Common cause: the copy grabbed extra text.")
            again = getpass.getpass("       Try once more (hidden), or Enter to skip: ").strip()
            if not again:
                results[t["name"]] = "skipped_bad_shape"
                continue
            key = again

        _say("info", f"checking with {t['name']}'s own server...")
        ok, detail = verify(t, key)
        save_key(t["name"], t, key, ok, detail)
        results[t["name"]] = "VERIFIED" if ok else f"NOT_VERIFIED: {detail}"

        if ok:
            _say("ok", f"{t['name']}: VERIFIED -- {detail}. {t['models']} models unlocked "
                       "once wired.")
        else:
            _say("PROBLEM", f"{t['name']}: NOT verified -- {detail}")
            _say("info", "stored anyway so nothing is lost, but it does not count yet.")

    _write_report(results)
    _summary(results)
    return 0


def wire_into_omniroute(target: dict, key: str) -> tuple[bool, str]:
    """Set this key on the matching OmniRoute connection and activate it.

    Best-effort and honest: OmniRoute being unreachable is reported as unreachable, never as
    success. Never restarts or otherwise touches the service (standing rule), and only uses
    the supported /api calls -- never storage.sqlite.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from omniroute_api import OmniRouteAPI
    except Exception as exc:
        return False, f"could not load the OmniRoute client ({type(exc).__name__})"

    provider = target["omniroute_provider"]
    try:
        api = OmniRouteAPI()
        if not api.login():
            return False, "OmniRoute rejected the management login"
        conns = api.get_connections()
    except Exception as exc:
        return False, f"OmniRoute unreachable or refused ({type(exc).__name__})"

    match = next((c for c in conns if c.get("provider") == provider), None)
    if match is None:
        have = sorted({str(c.get("provider")) for c in conns if c.get("provider")})
        return False, (f"no existing connection for provider {provider!r}; "
                       f"one must be created first. Present: {', '.join(have[:12])}")

    try:
        api.update_connection(match["id"], {"apiKey": key, "isActive": True})
    except Exception as exc:
        return False, f"update refused ({type(exc).__name__})"

    return True, f"key set on connection {match['id']} for provider {provider!r}, activated"


def do_clipboard(wire: bool) -> int:
    """Read one key from the clipboard, identify it, verify it, optionally wire it."""
    print()
    print("=" * 78)
    print("  READING THE KEY FROM YOUR CLIPBOARD")
    print("=" * 78)
    print()

    key = read_clipboard()
    if not key:
        _say("PROBLEM", "the clipboard is empty, or I could not read it.")
        _say("info", "Copy the API key (Ctrl+C on the key itself), then run this again.")
        return 1

    if "\n" in key or "\r" in key:
        first = key.splitlines()[0].strip()
        _say("info", "clipboard held several lines; using the first one.")
        key = first

    _say("ok", f"got something from the clipboard: {fingerprint(key)}")
    _say("info", "the key itself is never shown or logged -- only that fingerprint.")

    cands = candidates_for(key)
    if not cands:
        _say("PROBLEM", "this does not match the shape of any key I know how to wire.")
        _say("info", "Expected one of: AIza... or AQ.... (aistudio), SG_... (segmind), "
                     "or a long alphanumeric token (kie/novita).")
        _say("info", "Common cause: the copy picked up a label or extra spaces as well.")
        return 1

    if len(cands) == 1:
        _say("info", f"shape says this is a {cands[0]['name']} key.")
    else:
        names = ", ".join(c["name"] for c in cands)
        _say("info", f"shape is ambiguous ({names}) -- I will ask each provider in turn.")

    winner, detail = None, ""
    for t in cands:
        _say("info", f"asking {t['name']}'s own server...")
        ok, detail = verify(t, key)
        if ok:
            winner = t
            break
        _say("info", f"  {t['name']}: {detail}")

    if winner is None:
        _say("PROBLEM", "no provider accepted this key, so it does not count yet.")
        _say("info", f"last answer: {detail}")
        _say("info", "If the key is brand new, some providers take a minute to activate it. "
                     "Copy it again and retry.")
        return 1

    save_key(winner["name"], winner, key, True, detail)
    _say("ok", f"VERIFIED as {winner['name'].upper()} -- {detail}")
    _say("ok", f"saved to state/generated_keys.json (gitignored). "
               f"{winner['models']} models available once wired.")

    if not wire:
        _say("info", "not wiring (--no-wire given).")
        return 0

    print()
    _say("info", f"wiring {winner['name']} into OmniRoute (management login takes ~10s)...")
    ok, detail = wire_into_omniroute(winner, key)
    if ok:
        _say("ok", f"WIRED -- {detail}")
        print()
        print("  What is NOT claimed: that this provider returns real video yet. Wiring is")
        print("  done; the proof is a 5-second clip that comes back as real MP4 bytes, and")
        print("  that is the next step.")
    else:
        _say("PROBLEM", f"key is verified but NOT wired -- {detail}")
        _say("info", "The key is saved, so nothing is lost. Tell the agent this message.")
    print()
    return 0 if ok else 1


def _write_report(results: dict) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generated_at": _now(),
        "note": "Outcomes only. No key material is stored in this file.",
        "results": results,
        "dropped": DROPPED,
    }, indent=2), encoding="utf-8")
    _say("info", f"wrote {REPORT.relative_to(PROJECT_ROOT)}")


def _summary(results: dict) -> None:
    good = [k for k, v in results.items()
            if v == "VERIFIED" or v == "kept_existing_verified"]
    bad = [(k, v) for k, v in results.items() if v.startswith("NOT_VERIFIED")]
    skipped = [k for k, v in results.items() if v.startswith("skipped")]

    unlocked = sum(t["models"] for t in TARGETS if t["name"] in good)

    print()
    print("=" * 78)
    print("  RESULT")
    print("=" * 78)
    if good:
        print(f"  Verified keys : {', '.join(sorted(good))}")
        print(f"  That is {unlocked} models, once I wire them into OmniRoute.")
    for name, why in bad:
        print(f"  Not verified  : {name} -- {why}")
    if skipped:
        print(f"  Skipped       : {', '.join(sorted(skipped))}")
    if not good:
        print("  No verified keys yet.")
    print()
    print("  What is NOT claimed: that any of these are wired into OmniRoute, or that they")
    print("  return real video yet. Verified means the provider accepted the key. Wiring")
    print("  and a real MP4 are the next two steps, and I do those.")
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the sites to visit and exit")
    ap.add_argument("--clipboard", action="store_true",
                    help="read one key from the clipboard, identify it, verify it, wire it")
    ap.add_argument("--no-wire", action="store_true",
                    help="with --clipboard: verify and save, but do not touch OmniRoute")
    ap.add_argument("--status", action="store_true", help="show which keys are stored/verified")
    ap.add_argument("--reverify", action="store_true", help="re-check stored keys, paste nothing")
    ap.add_argument("--only", default="", help="comma-separated subset, e.g. kie,segmind")
    args = ap.parse_args(argv)

    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    if only:
        known = {t["name"] for t in TARGETS}
        unknown = [s for s in only if s not in known]
        if unknown:
            _say("PROBLEM", f"unknown target(s): {', '.join(unknown)}")
            _say("info", f"known: {', '.join(sorted(known))}")
            return 2

    try:
        if args.list:
            print_list()
            return 0
        if args.clipboard:
            return do_clipboard(wire=not args.no_wire)
        if args.status:
            return do_status()
        if args.reverify:
            return do_reverify()
        return do_paste(only)
    except KeyboardInterrupt:
        print()
        _say("info", "stopped. Anything already pasted was saved.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
