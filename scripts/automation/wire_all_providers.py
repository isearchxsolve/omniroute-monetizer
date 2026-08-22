"""Wire OmniRoute's unwired providers, in bulk, honestly.

The problem this solves
-----------------------
Measured 2026-08-22: OmniRoute's catalog (`state/all_295_providers_catalog.json`) lists 296
providers, but there were only 92 connection rows covering 76 distinct providers. **220 providers
had never been wired at all.** Earlier passes burned time on 6 already-wired providers that were
all blocked by an empty wallet, while those 220 sat untouched.

What was learned the hard way
-----------------------------
* `POST /api/providers` with `{provider, authType, name, isActive}` returns **201** and creates a
  connection -- the route was right all along. Verified with `opencode`.
* The API validates the slug against its OWN enum, which is NARROWER than the catalog JSON.
  `aihorde` and `veoaifree-web` are both in the catalog yet both return
  `400 {"error": "Invalid provider"}`. So the only way to know what is creatable is to try.
* `POST /api/providers/bulk` is NOT bulk-create. Its schema is `{provider: string, entries: []}`
  -- many keys for ONE provider. Wrong tool for this job.
* `server.js` (readable, not minified) carries the auth classification tables. Only two classes
  cost nothing: NOAUTH_PROVIDERS (9) and LOCAL_PROVIDERS (12). See `provider_tables.py`.

Activation policy -- deliberate, and the reason this script has two modes
------------------------------------------------------------------------
A connection that is ACTIVE but has no key is worse than no connection at all: OmniRoute's
router will select it and the request fails. So:

* ``--free``  creates the NOAUTH providers **active** -- they are real public endpoints that need
  no credential, so an active row is immediately usable.
* LOCAL providers are created **inactive** by the same flag. They need no credential either, but
  they point at a localhost port (8188, 7860, 11434, ...) and none of those were listening on this
  box. An active row whose backend is down is exactly the failure this policy exists to avoid, so
  they are parked until their server is up. ``--activate-local`` overrides this.
* ``--park``  creates every other provider **inactive**. The row exists, ready for a key, and the
  router will not route to it. This is wiring without breaking routing.

Honesty rules
-------------
* Nothing is deleted and no existing connection is modified. Only new rows are added.
* A provider is reported as WORKING only if OmniRoute's own test returns valid=True.
  "Created" and "working" are printed as separate columns and never conflated.
* Exact HTTP codes and error text are recorded, never paraphrased.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "all_295_providers_catalog.json"
REPORT = ROOT / "state" / "wire_all_report.json"

# From provider_tables.py against the installed build, 2026-08-22.
NOAUTH = ["aihorde", "auggie", "chipotle", "duckduckgo-web", "felo-web",
          "mimocode", "opencode", "theoldllm", "veoaifree-web"]
LOCAL = ["comfyui", "docker-model-runner", "lemonade", "llama-cpp", "llamafile",
         "lm-studio", "ollama-local", "oobabooga", "sdwebui", "triton", "vllm", "xinference"]
FREE = NOAUTH + LOCAL


def load_catalog() -> list[str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return sorted(data.get("providers", {}))


def create(api: OmniRouteAPI, slug: str, active: bool) -> dict:
    body = {"provider": slug, "authType": "none", "name": slug, "isActive": active}
    try:
        r = api.session.post(f"{api.api}/providers", json=body, timeout=30)
    except Exception as exc:
        return {"http": None, "error": f"{type(exc).__name__}: {exc}"}
    try:
        js = r.json()
    except Exception:
        js = {"raw": r.text[:200]}
    out = {"http": r.status_code}
    if r.status_code in (200, 201):
        out["id"] = (js.get("connection") or {}).get("id")
    else:
        out["error"] = json.dumps(js)[:160]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--free", action="store_true",
                    help="create NOAUTH (active) and LOCAL (parked; see --activate-local)")
    ap.add_argument("--activate-local", action="store_true",
                    help="also activate LOCAL providers -- only do this once their localhost "
                         "server is actually listening, or the router will pick a dead backend")
    ap.add_argument("--park", action="store_true", help="create all remaining providers, INACTIVE")
    ap.add_argument("--test", action="store_true", help="run OmniRoute's own test on each new row")
    ap.add_argument("--limit", type=int, default=0, help="stop after N creates (0 = no limit)")
    args = ap.parse_args()

    if not (args.free or args.park):
        print("nothing to do: pass --free and/or --park")
        return 2

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("[-] OmniRoute login failed -- nothing changed")
        return 2

    have = {str(c.get("provider", "")).lower() for c in api.get_connections()}
    catalog = load_catalog()
    print(f"[*] catalog={len(catalog)}  already wired={len(have)}  unwired={len(catalog) - len(have)}")

    todo: list[tuple[str, bool]] = []
    if args.free:
        todo += [(s, True) for s in NOAUTH if s.lower() not in have]
        todo += [(s, bool(args.activate_local)) for s in LOCAL if s.lower() not in have]
    if args.park:
        todo += [(s, False) for s in catalog
                 if s.lower() not in have and s not in FREE]

    print(f"[*] to create: {len(todo)}  (active={sum(1 for _, a in todo if a)}, parked={sum(1 for _, a in todo if not a)})")

    rows, created, rejected = [], 0, 0
    for i, (slug, active) in enumerate(todo, 1):
        if args.limit and created >= args.limit:
            print(f"[*] --limit {args.limit} reached; stopping. {len(todo) - i + 1} not attempted.")
            break
        res = create(api, slug, active)
        row = {"provider": slug, "active_requested": active, **res}
        if res.get("http") in (200, 201):
            created += 1
            if args.test and res.get("id"):
                t = api.test_connection(res["id"])
                r = t.get("result") or {}
                row["test_http"] = t.get("http_status")
                row["valid"] = r.get("valid")
                row["test_error"] = (r.get("error") or (r.get("diagnosis") or {}).get("message"))
            mark = "OK " if row.get("valid") else "new"
            print(f"  [{i:>3}/{len(todo)}] {mark} {slug:28} 201 "
                  f"{'ACTIVE' if active else 'parked'} valid={row.get('valid')}")
        else:
            rejected += 1
            print(f"  [{i:>3}/{len(todo)}] --  {slug:28} {res.get('http')} {str(res.get('error'))[:70]}")
        rows.append(row)
        time.sleep(0.15)  # be gentle on the local service

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    working = [r for r in rows if r.get("valid")]
    print("\n" + "=" * 70)
    print(f"created : {created}")
    print(f"rejected by the API's provider enum : {rejected}")
    if args.test:
        print(f"created AND OmniRoute-verified valid : {len(working)}")
        for r in working:
            print(f"   {r['provider']}")
    print(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
