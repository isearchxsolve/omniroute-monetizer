#!/usr/bin/env python3
"""
Force refresh ALL OAuth connections (active + inactive).
For connections where the API refresh endpoint succeeds, mark them active.
For connections where the refresh token is truly dead, record them for browser re-auth.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact
from oauth_keepalive import resolve_password

OUTPUT = PROJECT_ROOT / "state" / "force_reauth_results.json"


def main():
    pw = resolve_password()
    if not pw:
        print("ERROR: no management password resolvable")
        return 1

    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("ERROR: management login failed")
        return 1

    conns = api.get_connections()
    oauth_conns = [c for c in conns if c.get("authType") == "oauth"]
    print(f"Total OAuth connections: {len(oauth_conns)}")
    print(f"  Active:   {sum(1 for c in oauth_conns if c.get('isActive'))}")
    print(f"  Inactive: {sum(1 for c in oauth_conns if not c.get('isActive'))}")
    print()

    results = {"refreshed": [], "needs_browser_reauth": [], "unsupported": [], "other_failed": []}

    for conn in oauth_conns:
        cid = conn.get("id")
        provider = conn.get("provider")
        name = conn.get("name") or "unnamed"
        is_active = conn.get("isActive")
        status_label = "ACTIVE  " if is_active else "INACTIVE"

        print(f"[{status_label}] {provider:15s} | {name:30s} -> ", end="", flush=True)

        try:
            res = api.refresh_connection(cid)
            http = res.get("http_status")
            body = res.get("result") or {}
            success = http == 200 and bool(body.get("success"))

            if success:
                exp = body.get("expiresAt", "unknown")
                print(f"REFRESHED (expiresAt={exp})")
                results["refreshed"].append({"id": cid, "provider": provider, "name": name, "expiresAt": exp})
                # If it was inactive but refresh worked, activate it
                if not is_active:
                    try:
                        api.update_connection(cid, {"isActive": True})
                        print(f"           -> Activated!")
                    except Exception as e:
                        print(f"           -> Activate failed: {e}")
            else:
                err = body.get("error") or body.get("message") or f"HTTP {http}"
                err_str = redact(str(err))[:120]
                if "reauth" in err_str.lower() or "refresh token" in err_str.lower() or "expired" in err_str.lower():
                    print(f"NEEDS_BROWSER_REAUTH ({err_str})")
                    results["needs_browser_reauth"].append({"id": cid, "provider": provider, "name": name, "error": err_str})
                elif "unsupported" in err_str.lower() or "not supported" in err_str.lower():
                    print(f"UNSUPPORTED ({err_str})")
                    results["unsupported"].append({"id": cid, "provider": provider, "name": name, "error": err_str})
                else:
                    print(f"FAILED ({err_str})")
                    results["other_failed"].append({"id": cid, "provider": provider, "name": name, "error": err_str})
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"EXCEPTION ({err})")
            results["other_failed"].append({"id": cid, "provider": provider, "name": name, "error": err})

        time.sleep(0.3)

    print()
    print("=" * 60)
    print(f"SUMMARY:")
    print(f"  Refreshed (API):        {len(results['refreshed'])}")
    print(f"  Needs browser re-auth:  {len(results['needs_browser_reauth'])}")
    print(f"  Unsupported:            {len(results['unsupported'])}")
    print(f"  Other failures:         {len(results['other_failed'])}")
    print()

    if results["needs_browser_reauth"]:
        print("Providers needing browser re-auth:")
        for r in results["needs_browser_reauth"]:
            print(f"  [{r['provider']:15s}] {r['name']}")

    OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
