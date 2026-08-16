#!/usr/bin/env python3
"""
enable_omniroute_noauth.py
--------------------------
Enable OmniRoute's zero-API-key (no-auth) free providers so that
`auto`, `auto/best-free`, and `auto/best-coding` can route to them.

Requires:
  - OmniRoute running (default http://localhost:20128)
  - Management access: either REQUIRE_API_KEY=false for /api/*, or a
    dashboard session / management API key

Usage:
  python enable_omniroute_noauth.py
  python enable_omniroute_noauth.py --base http://127.0.0.1:20128
  python enable_omniroute_noauth.py --key YOUR_OMNIROUTE_API_KEY
  python enable_omniroute_noauth.py --test   # also send a tiny chat probe
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    sys.exit("pip install httpx  (required)")

# Provider ids from OmniRoute's NOAUTH_PROVIDERS catalog + common free pools.
# Safe to POST even if already connected — script treats 409/already-exists as OK.
NOAUTH_CANDIDATES: List[Dict[str, str]] = [
    {"id": "opencode", "name": "OpenCode Free"},
    {"id": "pollinations", "name": "Pollinations"},
    {"id": "felo-web", "name": "Felo"},
    {"id": "felo", "name": "Felo (alias)"},
    {"id": "duckduckgo-web", "name": "DuckDuckGo AI Chat"},
    {"id": "theoldllm", "name": "The Old LLM"},
    {"id": "auggie", "name": "Auggie"},
    {"id": "chipotle", "name": "Chipotle Pepper AI"},
    {"id": "longcat", "name": "LongCat"},
    {"id": "cloudflare-ai", "name": "Cloudflare AI"},
]


def _headers(api_key: Optional[str]) -> Dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _req(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_body: Any = None,
    api_key: Optional[str] = None,
) -> Tuple[int, Any]:
    r = client.request(method, url, headers=_headers(api_key), json=json_body)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def list_providers(client: httpx.Client, base: str, api_key: Optional[str]) -> List[Dict[str, Any]]:
    """Try several list endpoints used across OmniRoute versions."""
    paths = [
        "/api/providers",
        "/api/provider-nodes",
        "/api/providers/list",
    ]
    for path in paths:
        code, body = _req(client, "GET", f"{base}{path}", api_key=api_key)
        if code != 200:
            continue
        if isinstance(body, list):
            return [x for x in body if isinstance(x, dict)]
        if isinstance(body, dict):
            for key in ("providers", "data", "items", "nodes", "connections"):
                if isinstance(body.get(key), list):
                    return [x for x in body[key] if isinstance(x, dict)]
    return []


def provider_ids(rows: List[Dict[str, Any]]) -> set:
    out = set()
    for row in rows:
        for k in ("id", "providerId", "provider", "name", "alias", "type"):
            v = row.get(k)
            if isinstance(v, str) and v.strip():
                out.add(v.strip().lower())
    return out


def enable_one(
    client: httpx.Client,
    base: str,
    api_key: Optional[str],
    provider_id: str,
) -> Tuple[str, str]:
    """
    Returns (status, detail) where status is one of:
      created | exists | enabled | failed
    """
    # OmniRoute accepts a placeholder key for true no-auth providers.
    payloads = [
        {"provider": provider_id, "apiKey": "free", "enabled": True},
        {"id": provider_id, "apiKey": "free", "enabled": True},
        {"providerId": provider_id, "apiKey": "free", "enabled": True},
        {"type": provider_id, "apiKey": "free", "enabled": True},
        # Some builds use camelCase / connection shape
        {
            "provider": provider_id,
            "credentials": {"apiKey": "free"},
            "enabled": True,
            "noAuth": True,
        },
    ]

    for body in payloads:
        code, resp = _req(client, "POST", f"{base}/api/providers", json_body=body, api_key=api_key)
        if code in (200, 201):
            return "created", f"HTTP {code}"
        if code in (409, 422):
            # Already exists — try enable/update
            break
        if code in (400, 404):
            continue  # try next payload shape
        if code in (401, 403):
            return "failed", f"auth required (HTTP {code}) — pass --key or open dashboard session"

    # Try PUT enable on known id variants
    for pid in (provider_id, provider_id.replace("-", "_")):
        for path in (
            f"/api/providers/{pid}",
            f"/api/providers/{pid}/enable",
            f"/api/provider-nodes/{pid}",
        ):
            for method, body in (
                ("PUT", {"enabled": True, "apiKey": "free"}),
                ("PATCH", {"enabled": True}),
                ("POST", {"enabled": True}),
            ):
                code, resp = _req(client, method, f"{base}{path}", json_body=body, api_key=api_key)
                if code in (200, 201, 204):
                    return "enabled", f"{method} {path} -> HTTP {code}"
                if code in (401, 403):
                    return "failed", f"auth required (HTTP {code})"

    return "failed", "no matching create/enable endpoint accepted this provider id"


def test_chat(client: httpx.Client, base: str, api_key: Optional[str], model: str) -> Tuple[bool, str]:
    code, body = _req(
        client,
        "POST",
        f"{base}/v1/chat/completions",
        api_key=api_key or "omniroute",
        json_body={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 16,
            "temperature": 0,
        },
    )
    if code != 200:
        return False, f"HTTP {code}: {str(body)[:200]}"
    try:
        content = body["choices"][0]["message"]["content"]
        used = body.get("model") or model
        return True, f"model={used} reply={content!r}"
    except Exception:
        return True, f"HTTP 200 (unparsed body): {str(body)[:160]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Enable OmniRoute no-auth free providers")
    ap.add_argument(
        "--base",
        default=os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/"),
        help="OmniRoute origin (no trailing /v1)",
    )
    ap.add_argument(
        "--key",
        default=os.environ.get("OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_MGMT_KEY") or "",
        help="Management / API key if your instance requires auth for /api/*",
    )
    ap.add_argument("--test", action="store_true", help="Probe auto / auto/best-free after enabling")
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional subset of provider ids (default: all candidates)",
    )
    args = ap.parse_args()

    base = args.base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    api_key = args.key.strip() or None

    print(f"OmniRoute base : {base}")
    print(f"Auth           : {'Bearer ***' if api_key else '(none — local open management)'}")
    print()

    with httpx.Client(timeout=20.0) as client:
        # Health / reachability
        code, _ = _req(client, "GET", f"{base}/v1/models", api_key=api_key or "omniroute")
        if code >= 500 or code == 0:
            print(f"ERROR: cannot reach {base} (models endpoint HTTP {code})")
            print("Start OmniRoute first:  omniroute   or   docker run -p 20128:20128 ...")
            return 1
        print(f"Reachable      : yes (/v1/models -> HTTP {code})")

        existing = list_providers(client, base, api_key)
        have = provider_ids(existing)
        if existing:
            print(f"Existing providers listed: {len(existing)}")
            if have:
                sample = ", ".join(sorted(have)[:12])
                print(f"  ids sample: {sample}")
        else:
            print("Could not list providers via /api/providers (may need --key or dashboard login).")
            print("Will still attempt create/enable for each no-auth candidate.")
        print()

        targets = NOAUTH_CANDIDATES
        if args.only:
            want = {x.lower() for x in args.only}
            targets = [t for t in NOAUTH_CANDIDATES if t["id"].lower() in want]
            if not targets:
                targets = [{"id": x, "name": x} for x in args.only]

        print("Enabling no-auth candidates:")
        results: List[Tuple[str, str, str]] = []
        for t in targets:
            pid = t["id"]
            # Skip obvious already-present
            if pid.lower() in have or t.get("name", "").lower() in have:
                print(f"  • {pid:<18} SKIP (already present)")
                results.append((pid, "exists", "already in list"))
                continue
            status, detail = enable_one(client, base, api_key, pid)
            mark = {
                "created": "OK ",
                "enabled": "OK ",
                "exists": "OK ",
                "failed": "FAIL",
            }.get(status, "??")
            print(f"  • {pid:<18} {mark} {status} — {detail}")
            results.append((pid, status, detail))

        ok = sum(1 for _, s, _ in results if s in ("created", "enabled", "exists"))
        fail = sum(1 for _, s, _ in results if s == "failed")
        print()
        print(f"Summary: {ok} ok/present, {fail} failed, {len(results)} attempted")

        if fail and not api_key:
            print()
            print("Tip: management API may require a key. From the dashboard:")
            print("  Dashboard → Endpoints / API Keys → create key → re-run with --key <key>")
            print("Or enable manually: Dashboard → Providers → toggle no-auth providers ON.")

        if args.test:
            print()
            print("Chat probes:")
            for model in ("auto", "auto/best-free", "auto/best-coding", "auto/coding"):
                good, msg = test_chat(client, base, api_key, model)
                print(f"  {'OK' if good else 'FAIL'}  {model:<20} {msg}")

        print()
        print("Next: point Neon Architect at OmniRoute and use model auto-best:")
        print(f"  base_url = {base}/v1")
        print("  model    = auto   (or auto/best-free / auto/best-coding)")
        return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
