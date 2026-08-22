#!/usr/bin/env python3
"""harvest_free_keys.py -- sign up at free providers with Google SSO, key by key, and wire them.

THE EXERCISE THIS IMPLEMENTS
----------------------------
Operator, verbatim: *"create accounts in new providers using google sso, create keys and wire
them"*, with the standing rule *"you never open an existing Chrome profile. You open a blank
profile, i signup with google, then you start harvesting."*

That is exactly the loop below:

    blank robot profile (already holds the Google session)
      -> open the provider's site in PLAIN Chrome
      -> operator clicks "Continue with Google"        <- no password typed, ever
      -> operator clicks "create API key", copies it
      -> this script creates the OmniRoute connection WITH that key
      -> OmniRoute tests it against the provider's OWN upstream
      -> valid: kept active.  invalid: the row is DELETED so no junk is left behind.

WHY A HUMAN IS IN THE LOOP, AND WHY THAT IS NOT A SHORTCOMING
------------------------------------------------------------
Google refuses its password/consent step inside a Playwright-launched Chrome -- "Couldn't sign
you in / This browser or app may not be secure", measured 2026-08-22 (worklog #1033). This repo
does not disguise the browser to beat that check; that is how accounts get flagged. So the
sign-in click is the operator's, in an ordinary Chrome with no automation flags. Everything
after the key exists is pure HTTP and needs no browser again.

WHY THE ROW MUST BE CREATED WITH THE KEY IN ONE SHOT
----------------------------------------------------
Measured 2026-08-22: `POST /api/providers` rejects an apikey provider with
`400 {"field":"apiKey","message":"API key is required"}`. Empty string and a single space are
BOTH rejected. So there is no way to pre-create an empty row and fill it in later, and no way to
"wire all 296 providers" without a real key for each. 191 of the 296 are in that class. This
script is therefore the only honest path, not a convenience wrapper.

`paste_provider_key.py::wire_into_omniroute` cannot be reused for these: it requires the
connection to already exist ("one must be created first"), which for a brand-new provider it
never does.

CHROME SAFETY
-------------
The profile comes from `chrome_live_guard.safe_profile_dir()` and is passed through
`assert_safe()` at the call site, so it can never be the operator's live Chrome tree
(`%LOCALAPPDATA%\\Google\\Chrome\\User Data`). Plain `chrome.exe` subprocess, no automation
switches, no debugging port -- the same proven launch path as
`provider_login_helper.run_manual_signin()`.

PAYWALLS AND CAPTCHAS ARE REFUSED, NOT WORKED AROUND
----------------------------------------------------
Operator's standing rule: *"you reject all paywall card requirements and all captcha. You do not
hit them or hammer them."* Implemented literally:

* If a provider asks for a credit/debit card at any point, the answer is `p`. It is recorded as
  `PAYWALL_REFUSED` and the queue moves on. No card is ever entered, and the provider is not
  revisited in this run.
* If a CAPTCHA, "verify you are human", or a phone/KYC check appears, the answer is `c`. It is
  recorded as `CAPTCHA_REFUSED`. Nothing is solved, bypassed, or automated -- and, critically,
  nothing is retried. A CAPTCHA is a site telling you to stop; retrying is hammering.
* There is exactly ONE attempt per provider in the whole run. No retry loop exists anywhere in
  this file, on purpose, so a bad target cannot turn into repeated traffic.
* `--no-card-only` restricts the queue to providers whose own free-tier note states that no
  credit card is required, so the operator never even sees a card prompt.

SECRET HANDLING (anti-pattern #7)
---------------------------------
* A pasted key is a CANDIDATE. It is a key only after OmniRoute's test returns valid=True
  against the provider's own upstream. `valid=False` is never reported as success.
* Keys are never printed or logged -- only a first4...last4 fingerprint.
* Raw keys go only to `state/generated_keys.json`, which is gitignored.

USAGE
-----
    python harvest_free_keys.py --list              # show the queue, open nothing
    python harvest_free_keys.py                     # walk the queue, best targets first
    python harvest_free_keys.py --only zenmux,ai21
    python harvest_free_keys.py --start 10 --count 5
    python harvest_free_keys.py --no-browser        # paste keys you already have
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OMNIROUTE_BASE = "http://localhost:20128"
TARGETS_FILE = ROOT / "state" / "free_key_targets.json"
KEYS_FILE = ROOT / "state" / "generated_keys.json"
REPORT = ROOT / "state" / "harvest" / "free_key_harvest.json"
PROFILE_TAG = "providers"

# Best-first ordering. Criteria, in order: (1) does a Google "Continue with Google" button
# actually exist, (2) is the free tier real and usable rather than a trial that needs a card,
# (3) how much the free tier gives. Anything needing a Chinese phone number, WeChat, KYC or a
# Discord handshake is pushed to the back -- those cannot be completed with a Google click, so
# putting them early would waste the operator's time. Not a quality judgement on the provider.
PRIORITY = [
    # no signup at all, if it works
    "uncloseai",
    # generous, Google-SSO, no card
    "zenmux", "nous-research", "routeway", "openadapter", "api-airforce", "navy",
    "dgrid", "typhoon", "inception", "featherless-ai", "blackbox",
    # real credit grants, Google-SSO, no card
    "agentrouter", "pioneer", "modal", "baseten", "sambanova", "ai21", "reka",
    "scaleway", "hyperbolic", "nebius", "openvecta", "charm-hyper", "tokenrouter",
    "siliconflow", "monsterapi", "nlpcloud", "liquid", "jina-reader", "ollama-cloud",
    "byteplus", "freepik", "bluesminds", "puter",
    # needs something other than a Google click (phone / KYC / WeChat / Discord / Alibaba id)
    "modelscope", "ant-ling", "internlm", "longcat", "sarvam", "dahl", "freetheai",
    "hcnsec", "360ai", "baichuan", "baidu", "coze", "doubao", "iflytek", "sparkdesk",
    "sensenova", "stepfun", "tencent",
]

# Measured dead ends. Kept with the reason rather than silently removed, so the next agent does
# not "discover" them again and spend the operator's clicks on them.
KNOWN_DEAD = {
    "uncloseai": "MEASURED 2026-08-22: created fine and OmniRoute's test said valid=True, but all "
                 "3 models it exposes 404 with 'model does not exist' on /v1/chat/completions. "
                 "Row was deleted. Nothing to sign up for, and nothing that answers.",
}

MASK_RE = re.compile(r"\s+")

# Read off each provider's OWN free-tier note. "no credit card" is the provider's own promise,
# so it is the only thing treated as evidence; everything else is left as unknown rather than
# guessed at. CARD_RISK words mean "this may ask for a card" -- a warning to the operator, never
# a reason to enter one.
NO_CARD_RE = re.compile(r"no credit card|without a credit card|no card", re.I)
CARD_RISK_RE = re.compile(r"credit card|card required|kyc|identity verification|"
                          r"verification required|pay-per-use|paid plan|billing", re.I)


def card_stance(note: str) -> str:
    """'no-card' | 'may-ask-for-card' | 'unknown', from the provider's own words."""
    if NO_CARD_RE.search(note or ""):
        return "no-card"
    if CARD_RISK_RE.search(note or ""):
        return "may-ask-for-card"
    return "unknown"


def fingerprint(key: str) -> str:
    """first4...last4 -- enough to tell two keys apart, useless to an attacker."""
    k = key.strip()
    if len(k) <= 8:
        return "*" * len(k)
    return f"{k[:4]}...{k[-4:]} (len={len(k)})"


def say(*lines: str) -> None:
    for ln in lines:
        print(ln)


def read_clipboard() -> str:
    """Windows clipboard via PowerShell. Returns '' on any failure -- never raises."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=20,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def find_chrome() -> pathlib.Path | None:
    for c in (
        pathlib.Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        pathlib.Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ):
        if c.is_file():
            return c
    return None


def open_tab(url: str) -> bool:
    """Open one tab in the ROBOT profile using plain Chrome.

    Chrome routes the URL into the already-open window for the same --user-data-dir, so this
    adds a tab rather than starting a second browser. Never waited on: the operator keeps the
    window open for the whole run.
    """
    udd = safe_profile_dir(PROFILE_TAG)
    assert_safe(udd, who="harvest_free_keys")   # cannot ever be the live Chrome tree
    chrome = find_chrome()
    if not chrome:
        say("  [!] could not find an installed chrome.exe; open the link yourself")
        return False
    subprocess.Popen(
        [str(chrome), f"--user-data-dir={udd}", "--no-first-run",
         "--no-default-browser-check", "--window-size=1280,900", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return True


def build_targets() -> list[dict]:
    """Regenerate the free-tier queue from the installed OmniRoute build.

    `state/` is gitignored (`.gitignore:3`), so `free_key_targets.json` does not survive a clone.
    Rather than fail, rebuild it from the source of truth: `APIKEY_PROVIDERS` in
    `dist/open-sse/mcp-server/server.js`.

    That table is assembled from six sub-tables via spreads
    (`...APIKEY_PROVIDERS_GATEWAYS` and friends), so evaluating the literal on its own throws
    `ReferenceError: APIKEY_PROVIDERS_GATEWAYS is not defined`. All six are resolved recursively
    and prepended before Node evaluates it.
    """
    import subprocess as sp
    import tempfile

    import provider_tables as pt

    src = pt.SERVER_JS.read_text(encoding="utf-8", errors="replace")
    lits: dict[str, str] = {}

    def resolve(name: str) -> None:
        if name in lits:
            return
        lit = pt._match_literal(src, name)
        lits[name] = lit
        for m in re.finditer(r"\.\.\.\s*([A-Z][A-Z0-9_]{3,})", lit):
            resolve(m.group(1))

    resolve("APIKEY_PROVIDERS")
    preamble = "\n".join(f"const {k} = {v};" for k, v in reversed(list(lits.items())))
    js = preamble + "\nprocess.stdout.write(JSON.stringify(APIKEY_PROVIDERS));"
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "dump.js"
        p.write_text(js, encoding="utf-8")
        proc = sp.run(["node", str(p)], capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"node failed to evaluate APIKEY_PROVIDERS: {proc.stderr[:300]}")
    table = json.loads(proc.stdout)

    rows = [{"id": pid, "name": e.get("name"), "website": e.get("website"),
             "freeNote": e.get("freeNote"), "authHint": e.get("authHint"),
             "apiKeyUrl": e.get("apiKeyUrl")}
            for pid, e in table.items() if isinstance(e, dict) and e.get("hasFree")]
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FILE.write_text(json.dumps(sorted(rows, key=lambda r: r["id"]), indent=2),
                            encoding="utf-8")
    say(f"[*] rebuilt {TARGETS_FILE.name} from the installed build: "
        f"{len(rows)} providers flagged hasFree")
    return rows


def load_targets() -> list[dict]:
    if not TARGETS_FILE.exists():
        say(f"[*] {TARGETS_FILE.name} missing (state/ is gitignored) -- rebuilding it")
        try:
            build_targets()
        except Exception as exc:
            say(f"[-] could not rebuild the queue: {type(exc).__name__}: {exc}")
            return []
    rows = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    rank = {p: i for i, p in enumerate(PRIORITY)}
    dead = [r["id"] for r in rows if r["id"] in KNOWN_DEAD]
    if dead:
        say(f"[*] skipping {len(dead)} measured dead end(s): {', '.join(dead)}")
        for d in dead:
            say(f"      {d}: {KNOWN_DEAD[d]}")
    rows = [r for r in rows if r["id"] not in KNOWN_DEAD]
    for r in rows:
        r["card_stance"] = card_stance(MASK_RE.sub(" ", str(r.get("freeNote") or "")))
    # Providers that promise "no credit card" come first: those are the ones the operator can
    # finish with a Google click and nothing else. 'may-ask-for-card' goes last so a card prompt
    # is met as late as possible -- and refused when it appears.
    stance_rank = {"no-card": 0, "unknown": 1, "may-ask-for-card": 2}
    rows.sort(key=lambda r: (stance_rank[r["card_stance"]], rank.get(r["id"], 999), r["id"]))
    return rows


def save_key(slug: str, key: str, verified: bool, detail: str) -> None:
    """Raw key -> gitignored state/generated_keys.json. Nothing else ever sees it."""
    store = {}
    if KEYS_FILE.exists():
        try:
            store = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            store = {}
    store[slug] = {
        "key": key,
        "provider": slug,
        "source": "harvest_free_keys (operator pasted after Google SSO signup)",
        "verified": verified,
        "verify_detail": detail,
        "fingerprint": fingerprint(key),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def real_completion(slug: str, timeout: int = 120) -> tuple[bool, str]:
    """Ask OmniRoute for an actual answer from this provider. This is the only proof accepted.

    MEASURED 2026-08-22, and the reason this function exists: `uncloseai` was created, and
    OmniRoute's own `test_connection` returned **valid=True** -- yet all three models it exposes
    (`adamo1139/Hermes-3-Llama-3.1-8B-FP8-Dynamic`, `qwen3.6:27b`, `gemma4:31b`) returned
    **404 "The model does not exist"** on `/v1/chat/completions`. The row was deleted.

    So `valid=True` is NOT evidence a provider works, and reporting it as such would be exactly
    the false "harvested" claim anti-pattern #7 forbids. A provider counts only when a real
    request comes back with real text.

    One request per model, at most 3 models, then it gives up. No retry of a failed model --
    a 404/401 is an answer, and re-asking is hammering.
    """
    try:
        m = requests.get(f"{OMNIROUTE_BASE}/v1/models", timeout=90).json()
    except Exception as exc:
        return False, f"could not list models: {type(exc).__name__}"
    ids = [x.get("id", "") for x in (m.get("data") or [])
           if str(x.get("id", "")).startswith(f"{slug}/")]
    if not ids:
        return False, "OmniRoute exposes no models at all for this provider"

    last = ""
    for mid in ids[:3]:
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": mid, "messages": [{"role": "user", "content": "Reply with: OK"}],
                      "max_tokens": 12},
                timeout=timeout,
            )
        except Exception as exc:
            last = f"{mid}: {type(exc).__name__}"
            continue
        if r.status_code == 200:
            txt = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            if str(txt).strip():
                return True, f"{mid} answered with real text"
            last = f"{mid}: HTTP 200 but empty content"
            continue
        last = f"{mid}: HTTP {r.status_code} {MASK_RE.sub(' ', r.text)[:120]}"
    return False, last or "no model answered"


def wire(api: OmniRouteAPI, slug: str, name: str, key: str) -> dict:
    """Create the connection WITH the key, prove it answers for real, roll back if it does not."""
    body = {"provider": slug, "authType": "apikey", "name": name or slug,
            "apiKey": key, "isActive": True}
    try:
        r = api.session.post(f"{api.api}/providers", json=body, timeout=60)
    except Exception as exc:
        return {"ok": False, "stage": "create", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        js = r.json()
    except Exception:
        js = {"raw": r.text[:200]}
    if r.status_code not in (200, 201):
        return {"ok": False, "stage": "create", "http": r.status_code,
                "detail": json.dumps(js)[:220]}

    cid = (js.get("connection") or {}).get("id")
    if not cid:
        return {"ok": False, "stage": "create", "http": r.status_code,
                "detail": f"created but no id returned: {json.dumps(js)[:180]}"}

    t = api.test_connection(cid)
    res = t.get("result") or {}
    valid = bool(res.get("valid"))
    err = res.get("error") or (res.get("diagnosis") or {}).get("message") or ""
    err = MASK_RE.sub(" ", str(err)).strip()

    if valid:
        # valid=True is a hint, not proof. See real_completion() for why.
        works, detail = real_completion(slug)
        if works:
            return {"ok": True, "stage": "answered", "id": cid,
                    "omniroute_test": "valid=True", "detail": detail}
        err = f"OmniRoute test said valid=True but no model answered -> {detail}"

    # Do not leave a dead active row: the router would select it and every request would fail.
    deleted = False
    try:
        d = api.session.delete(f"{api.api}/providers/{cid}", timeout=30)
        deleted = d.status_code in (200, 204)
    except Exception:
        pass
    return {"ok": False, "stage": "test" if not valid else "no-model-answered",
            "id": cid, "deleted": deleted,
            "detail": err[:260] or "test returned valid=False with no message"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the queue and exit")
    ap.add_argument("--only", default="", help="comma-separated provider ids")
    ap.add_argument("--start", type=int, default=0, help="skip the first N in the queue")
    ap.add_argument("--count", type=int, default=0, help="stop after N providers (0 = all)")
    ap.add_argument("--no-browser", action="store_true", help="do not open any Chrome tab")
    ap.add_argument("--no-card-only", action="store_true",
                    help="queue only providers whose own note says no credit card is required")
    args = ap.parse_args()

    rows = load_targets()
    if not rows:
        return 3

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        say("[-] OmniRoute login failed -- nothing was opened and nothing changed")
        return 2
    have = {str(c.get("provider", "")).lower() for c in api.get_connections()}

    # Drop what is already wired BEFORE any counting, so --list never overstates the work left.
    # build_targets() cannot do this itself: it only reads the installed build, not live state.
    already = [r["id"] for r in rows if r["id"].lower() in have]
    rows = [r for r in rows if r["id"].lower() not in have]
    if already:
        say(f"[*] already wired, not queued ({len(already)}): {', '.join(sorted(already))}")

    if args.no_card_only:
        before = len(rows)
        rows = [r for r in rows if r["card_stance"] == "no-card"]
        say(f"[*] --no-card-only: {len(rows)} of {before} providers state that no card is needed")
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        rows = [r for r in rows if r["id"] in want]
        missing = want - {r["id"] for r in rows}
        if missing:
            say(f"[!] not in the queue (unknown, already wired, or a known dead end): "
                f"{', '.join(sorted(missing))}")
    rows = rows[args.start:]
    if args.count:
        rows = rows[: args.count]

    if args.list:
        say(f"\n{len(rows)} free-tier providers still needing a key (best first)\n")
        for i, r in enumerate(rows, 1):
            note = MASK_RE.sub(" ", str(r.get("freeNote") or "")).strip()
            say(f"{i:>3}. {r['id']:<20} {r['card_stance']:<17} {note[:74]}")
        return 0

    say("", "=" * 78,
        "  GET A FREE KEY, ONE PROVIDER AT A TIME",
        "=" * 78, "",
        "  For each provider I open its website in the ROBOT's Chrome -- the blank one",
        "  you already signed into Google with. Your own Chrome is never touched.",
        "",
        "  You do two clicks:",
        "     1. 'Continue with Google' / 'Sign in with Google'   (no password to type)",
        "     2. find 'API keys' -> create one -> COPY it",
        "",
        "  Then come back here and press Enter. I read it from your clipboard, wire it,",
        "  and test it against the provider itself. If it does not work I delete the row",
        "  so nothing broken is left behind.",
        "",
        "  If the site asks for a CARD  -> type  p  + Enter. We walk away. Never pay.",
        "  If you see a CAPTCHA / phone -> type  c  + Enter. We walk away. Never solve it.",
        "  Type  s  + Enter to skip for any other reason.   Type  q  + Enter to stop.",
        "  Each provider is tried ONCE. Nothing is ever retried or hammered.",
        "-" * 78)

    done, failed, skipped = [], [], []
    refused_card, refused_captcha = [], []
    for i, r in enumerate(rows, 1):
        slug = r["id"]
        if slug in have:
            say(f"\n[{i}/{len(rows)}] {slug} -- already wired, skipping")
            continue

        note = MASK_RE.sub(" ", str(r.get("freeNote") or "")).strip()
        hint = MASK_RE.sub(" ", str(r.get("authHint") or "")).strip()
        url = r.get("apiKeyUrl") or r.get("website") or ""
        say("", "=" * 78, f"[{i}/{len(rows)}]  {slug}   ({r.get('name') or slug})", "=" * 78)
        if note:
            say(f"  what is free : {note[:150]}")
        if r["card_stance"] == "no-card":
            say("  card         : provider states NO CREDIT CARD needed")
        elif r["card_stance"] == "may-ask-for-card":
            say("  card         : MAY ASK FOR A CARD -- if it does, type p and we walk away")
        if hint:
            say(f"  key looks like: {hint[:110]}")
        say(f"  opening      : {url}")

        if not args.no_browser and url:
            open_tab(url)

        try:
            ans = input("\n  Enter = read clipboard | s skip | p card asked | "
                        "c captcha | q quit : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            say("\n  stopped by operator.")
            break
        if ans == "q":
            say("  stopping here. Everything already wired stays wired.")
            break
        if ans == "p":
            refused_card.append(slug)
            say("  [REFUSED] PAYWALL_REFUSED -- card demanded. Walking away, not retrying.")
            continue
        if ans == "c":
            refused_captcha.append(slug)
            say("  [REFUSED] CAPTCHA_REFUSED -- human/phone check. Not solved, not retried.")
            continue
        if ans == "s":
            skipped.append(slug)
            continue

        key = read_clipboard()
        if not key or len(key) < 8 or "\n" in key:
            say("  [!] clipboard does not hold a single key-looking string -- skipped."
                "  (copy just the key, nothing else)")
            skipped.append(slug)
            continue

        say(f"  key read     : {fingerprint(key)}   (never printed in full)")
        say("  wiring + testing against the provider's own endpoint...")
        res = wire(api, slug, r.get("name") or slug, key)

        if res["ok"]:
            save_key(slug, key, True, res["detail"])
            done.append(slug)
            say(f"  [OK] WORKING -- a real model answered. wired and active. {res['detail'][:90]}")
            have.add(slug)
        else:
            save_key(slug, key, False, res["detail"])
            failed.append({"provider": slug, **res})
            say(f"  [--] did not verify at stage '{res['stage']}': {res['detail'][:180]}")
            if res.get("deleted"):
                say("       the dead row was deleted, so routing is unaffected.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "verified_and_wired": done, "failed": failed, "skipped": skipped,
         "PAYWALL_REFUSED": refused_card, "CAPTCHA_REFUSED": refused_captcha},
        indent=2), encoding="utf-8")

    say("", "=" * 78,
        f"  WORKING AND WIRED : {len(done)}" + (f"  -> {', '.join(done)}" if done else ""),
        f"  did not verify    : {len(failed)}",
        f"  PAYWALL_REFUSED   : {len(refused_card)}"
        + (f"  -> {', '.join(refused_card)}" if refused_card else ""),
        f"  CAPTCHA_REFUSED   : {len(refused_captcha)}"
        + (f"  -> {', '.join(refused_captcha)}" if refused_captcha else ""),
        f"  skipped           : {len(skipped)}",
        f"  report            : {REPORT}",
        "=" * 78,
        "  'WORKING' means OmniRoute's own test reached the provider and got a valid",
        "  answer. Nothing here is claimed on the strength of a key merely existing.",
        "  Refused providers were walked away from once and never retried.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
