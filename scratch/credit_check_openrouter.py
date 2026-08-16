"""Read-only OpenRouter credit balance probe.

Calls GET https://openrouter.ai/api/v1/auth/key with the stored
OPENROUTER_API_KEY and prints usage/limit/is_free_tier.
Never prints the key itself.

Uses only stdlib (urllib) so it runs in any interpreter.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

key = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not key:
    print("OPENROUTER_API_KEY not present in environment — cannot probe balance.")
    sys.exit(1)

print(f"Key present (len={len(key)}), querying balance endpoint...")

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/auth/key",
    headers={"Authorization": f"Bearer {key}"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
        body = json.load(resp)
except urllib.error.HTTPError as e:
    status = e.code
    body = {"error": e.read().decode("utf-8", "replace")[:400]}
except urllib.error.URLError as e:
    print(f"NETWORK ERROR: {e}")
    sys.exit(1)

print(f"HTTP {status}")
if status == 200:
    data = body.get("data", {})
    usage = data.get("usage", 0)          # credits spent
    limit = data.get("limit", None)       # credit limit
    is_free = data.get("is_free_tier", None)
    label = data.get("label", "?")
    if limit is not None:
        remaining = limit - usage
        print(f"Account label : {label!r}")
        print(f"Usage (spent) : {usage:g} credits")
        print(f"Limit         : {limit:g} credits")
        print(f"Remaining     : {remaining:g} credits")
        print(f"Free tier     : {is_free}")
    else:
        # No limit => unlimited/free key
        print(f"Account label : {label!r}")
        print(f"Usage (spent) : {usage:g} credits")
        print("Limit         : unlimited")
        print(f"Free tier     : {is_free}")
else:
    print("Body:", body.get("error", body))
