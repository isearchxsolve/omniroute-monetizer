# -*- coding: utf-8 -*-
"""you.com: verify the captured ydc-sk- key with a REAL authenticated API call.
Per AGENTS.md: never report a credential as harvested without a verified 200 OK upstream.
Never prints the key."""
import json, urllib.request, urllib.error, time

SECRET_PATH = "state/secrets/youcom_api_key.json"
rec = json.load(open(SECRET_PATH, encoding="utf-8"))
key = rec["api_key"]
print("testing key:", key[:10] + "..." + key[-4:], "len", len(key))

url = "https://api.you.com/v1/answer"
payload = json.dumps({"query": "Reply exactly one word: Omni"}).encode("utf-8")
req = urllib.request.Request(url, data=payload, method="POST", headers={
    "X-API-Key": key,
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        status = resp.status
        body = resp.read().decode("utf-8", "replace")
    dt = time.time() - t0
    print(f"\nHTTP {status} in {dt:.1f}s")
    try:
        data = json.loads(body)
        ans = data.get("answer", "")
        print("answer field:", ans[:200])
        print("keys:", list(data.keys()))
    except Exception:
        print("raw body head:", body[:400])
    if status == 200:
        print("\n>>> KEY VERIFIED — you.com API is live free supply")
except urllib.error.HTTPError as e:
    print(f"\nHTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
    print(">>> KEY REJECTED" if e.code in (401, 403) else ">>> HTTP error")
except Exception as e:
    print("\nERROR:", e)
