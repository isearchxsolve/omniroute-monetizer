"""Analyze the 51 existing OmniRoute connections + catalog to find Google-OAuth signup targets.

Read-only. Prints:
  1. All 51 connections: provider slug, authType, testStatus, isActive, email.
  2. Which provider slugs are NOT yet connected (the 241 EXTERNAL_ACCOUNT_REQUIRED gap).
  3. Cross-reference with ledger classifications.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    probe = load(STATE / "providers_probe.json")
    items = probe if isinstance(probe, list) else probe.get("providers", probe.get("items", []))
    print(f"=== {len(items)} existing connections ===")
    connected_slugs = set()
    for i in sorted(items, key=lambda x: x.get("provider", "")):
        slug = i.get("provider")
        connected_slugs.add(slug)
        print(
            f"{str(slug):24s} auth={str(i.get('authType')):7s} "
            f"test={str(i.get('testStatus')):8s} active={str(i.get('isActive')):5s} "
            f"email={str(i.get('email'))[:30]}"
        )

    ledger = load(STATE / "all_296_providers_execution_ledger.json")["providers"]
    print(f"\n=== ledger: {len(ledger)} offerings ===")

    # The gap: offerings that require an external account and are not connected
    gap = []
    for slug, info in ledger.items():
        cls = info.get("status") or info.get("classification")
        if cls == "EXTERNAL_ACCOUNT_REQUIRED" and slug not in connected_slugs:
            gap.append(slug)
    print(f"\nEXTERNAL_ACCOUNT_REQUIRED and NOT connected: {len(gap)}")
    print(sorted(gap))

    # Which connected slugs use oauth (candidates for Google-style flows already done)
    oauth_slugs = sorted({i.get("provider") for i in items if i.get("authType") == "oauth"})
    apikey_slugs = sorted({i.get("provider") for i in items if i.get("authType") == "apikey"})
    print(f"\nConnected via oauth ({len(oauth_slugs)}): {oauth_slugs}")
    print(f"Connected via apikey ({len(apikey_slugs)}): {apikey_slugs}")


if __name__ == "__main__":
    main()
