#!/usr/bin/env python3
"""
Export Exhaustive Verified Healthy Frontier Models List.
Filters for models originating exclusively from active, verified provider connections.
"""
import json
import re
import sys
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

OMNI_BASE = "http://localhost:20128"
OUTPUT_FILE = PROJECT_ROOT / "state" / "exhaustive_frontier_models.json"


def main():
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("[-] Login failed")
        return 1

    s = api.session

    # Fetch active & verified providers
    p_resp = s.get(f"{OMNI_BASE}/api/providers")
    conns = p_resp.json().get("connections", [])

    valid_providers = set()
    for c in conns:
        pid = c.get("id")
        pname = c.get("provider")
        is_active = c.get("isActive")
        test_status = c.get("testStatus")
        valid = c.get("test", {}).get("valid", False)

        if is_active and (test_status == "active" or valid):
            valid_providers.add(pid)
            valid_providers.add(pname)

    # Fetch models
    m_resp = s.get(f"{OMNI_BASE}/v1/models")
    models_data = m_resp.json().get("data", [])

    flagship_regex = re.compile(
        r'(gpt-5|gpt-4o|claude|deepseek|qwen|gemini|llama-3\.3|llama-3\.1-405|mistral-large|codestral|nemotron|o1|o3|sonnet|opus|r1)',
        re.I
    )

    models_by_provider = {}

    for m in models_data:
        mid = m.get("id", "")
        p_id = m.get("providerId")
        prefix = mid.split("/")[0] if "/" in mid else "system"

        if (p_id in valid_providers or prefix in valid_providers) and flagship_regex.search(mid):
            models_by_provider.setdefault(prefix, []).append(mid)

    output = {
        "total_verified_frontier_models": sum(len(v) for v in models_by_provider.values()),
        "provider_count": len(models_by_provider),
        "models_by_provider": models_by_provider,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[+] Saved {output['total_verified_frontier_models']} verified models to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
