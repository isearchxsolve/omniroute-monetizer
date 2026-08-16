#!/usr/bin/env python3
"""Inject unharvested env-var API keys into matching OmniRoute connections,
then verify upstream via POST /api/providers/{id}/test.

Zero-fabrication: only injects when the test returns valid=true do we keep
isActive=true; otherwise the connection is left/reverted inactive.
Never prints key values.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, mask_token

# provider slug -> env var candidates
CANDIDATES = {
    "llm7": ["LLM7_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "huggingface": ["HUGGINGFACE_API_KEY", "HF_TOKEN"],
    "friendliai": ["FRIENDLI_API_KEY", "FRIENDLIAI_API_KEY"],
    "lmarena": ["LMARENA_API_KEY"],
    "qoder": ["QODER_API_KEY"],
    # openai/anthropic env keys already proven dead (401) by cli_token_harvester — not re-injected
    "ainative": ["AINATIVE_API_KEY"],
}


def main() -> int:
    api = OmniRouteAPI()
    if not api.login():
        return 1
    conns = api.get_connections()
    by_provider = {}
    for c in conns:
        by_provider.setdefault(c.get("provider", "").lower(), []).append(c)

    results = []
    for slug, envs in CANDIDATES.items():
        key = None
        for e in envs:
            v = os.environ.get(e, "").strip()
            if v:
                key = v
                break
        existing = by_provider.get(slug, [])
        if not key:
            print(f"  {slug:14} no env key available; conns={len(existing)}")
            results.append((slug, "no_env_key", None))
            continue
        if not existing:
            # create new connection
            payload = {
                "provider": slug,
                "name": f"{slug} (auto-harvested)",
                "authType": "apikey",
                "apiKey": key,
                "isActive": True,
            }
            r = api.session.post(f"{api.api}/providers", json=payload, timeout=30)
            if r.status_code not in (200, 201):
                print(f"  {slug:14} create FAILED HTTP {r.status_code}: {r.text[:100]}")
                results.append((slug, "create_failed", r.status_code))
                continue
            cid = (r.json().get("connection") or r.json()).get("id")
            print(f"  {slug:14} created conn {cid[:8]} with {mask_token(key)}")
        else:
            c0 = existing[0]
            cid = c0["id"]
            r = api.session.put(f"{api.api}/providers/{cid}", json={"apiKey": key, "isActive": True}, timeout=30)
            if r.status_code != 200:
                print(f"  {slug:14} inject FAILED HTTP {r.status_code}: {r.text[:100]}")
                results.append((slug, "inject_failed", r.status_code))
                continue
            print(f"  {slug:14} injected {mask_token(key)} into conn {cid[:8]}")

        # verify upstream
        t0 = time.time()
        res = api.test_connection(cid)
        dt = int((time.time() - t0) * 1000)
        result = res.get("result", {}) or {}
        valid = bool(result.get("valid"))
        diag = result.get("diagnosis", "")
        if isinstance(diag, dict):
            diag = diag.get("type", "")
        print(f"  {slug:14} test: valid={valid} {dt}ms diag={str(diag)[:50]}")
        if not valid:
            # revert inactive — zero fabrication
            api.session.put(f"{api.api}/providers/{cid}", json={"isActive": False}, timeout=30)
            print(f"  {slug:14} reverted to inactive (upstream not verified)")
        results.append((slug, "valid" if valid else "invalid", dt))

    ok = sum(1 for _, s, _ in results if s == "valid")
    print(f"\nSUMMARY: {ok} newly verified / {len(results)} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
