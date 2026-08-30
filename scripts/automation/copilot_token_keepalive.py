#!/usr/bin/env python3
"""Keep the Copilot auth0 Bearer alive so ws replay never meets an expired token.

The access token expires server-side every 24h -- that is not negotiable. What is durable is
the auth0 refresh_token (offline_access grant), which mints a fresh 24h Bearer on demand. This
script runs on a schedule, refreshes BEFORE expiry, and persists the rotated material to
state/secrets/copilot_auth0.json. The refresh token may rotate on each grant -- the newest
response's refresh_token ALWAYS wins, or the next run dies.

Writes state/copilot_token_status.json (verdict + timestamps only, never token material).
Log: logs/copilot_token.log. Exit 0 = valid Bearer on disk; 1 = refresh failed (operator
must re-sign-in once in the automation profile to re-seed the cache).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets" / "copilot_auth0.json"
STATUS = ROOT / "state" / "copilot_token_status.json"
LOG = ROOT / "logs" / "copilot_token.log"
AUTH0 = "https://auth.copilot.microsoft.com/oauth/token"
REFRESH_MARGIN_S = 2 * 3600        # refresh when < 2h of validity remains
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def token_exp(access_token: str) -> int:
    import base64
    try:
        pad = access_token.split(".")[1] + "=" * (-len(access_token.split(".")[1]) % 4)
        return int(json.loads(base64.urlsafe_b64decode(pad)).get("exp") or 0)
    except Exception:
        return 0


def load() -> dict:
    if not SECRETS.exists():
        raise SystemExit(f"no supply file: {SECRETS} -- seed it from the automation profile's "
                         f"@@auth0spajs@@ cache (client_id + refresh_token)")
    return json.loads(SECRETS.read_text(encoding="utf-8"))


def save(d: dict) -> None:
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRETS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(SECRETS)


def write_status(verdict: str, detail: str) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "detail": detail,
    }, indent=2), encoding="utf-8")


def refresh(d: dict) -> dict:
    r = requests.post(AUTH0,
                      headers={"content-type": "application/x-www-form-urlencoded",
                               "user-agent": UA},
                      data=urllib.parse.urlencode({
                          "grant_type": "refresh_token",
                          "client_id": d.get("client_id"),
                          "refresh_token": d.get("refresh_token"),
                      }), timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"refresh grant failed: HTTP {r.status_code}: {r.text[:120]}")
    tok = r.json()
    out = dict(d)
    out["access_token"] = tok.get("access_token") or ""
    out["refresh_token"] = tok.get("refresh_token") or d.get("refresh_token")   # rotation wins
    out["refreshedAt"] = int(time.time())
    out["exp"] = token_exp(out["access_token"])
    if not out["exp"]:
        raise RuntimeError("refresh grant returned an unparsable access_token")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true",
                    help="refresh even if the current Bearer still has >2h left")
    a = ap.parse_args()

    d = load()
    exp = d.get("exp") or token_exp(d.get("access_token") or "")
    left = exp - int(time.time())
    if exp and left > REFRESH_MARGIN_S and not a.force:
        log(f"bearer valid for {left // 3600}h{(left % 3600) // 60:02d}m -- no refresh needed")
        write_status("VALID", f"bearer valid for {left}s")
        return 0

    log(f"bearer {'missing' if not exp else f'expires in {left}s'} -- refreshing")
    try:
        d2 = refresh(d)
    except Exception as e:
        log(f"REFRESH FAILED: {e}")
        write_status("FAILED", str(e)[:200])
        return 1
    save(d2)
    left = d2["exp"] - int(time.time())
    log(f"refreshed -- new bearer valid {left // 3600}h{(left % 3600) // 60:02d}m "
        f"(refresh token rotated: {d2['refresh_token'] != d.get('refresh_token')})")
    write_status("REFRESHED", f"bearer valid for {left}s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:                       # a keeper must fail loudly, not silently
        log(f"keepalive error: {type(e).__name__}: {e}")
        write_status("ERROR", f"{type(e).__name__}: {e}")
        sys.exit(2)
