#!/usr/bin/env python3
"""Re-test all 7 TokenRouter keys to see if 401 is key-specific or service-wide."""
import json
import time
import urllib.request
import urllib.error

BASE = "https://api.tokenrouter.com/v1"
MODEL = "qwen/qwen3.8-max-free"
KEYS = [
    "sk-vpHUXIq5GyO9YQipqHgBHERF24SOCseXocFjjxfG5cY685iL",
    "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg",
    "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
]


def redact(k):
    return k[:6] + "****" + k[-4:]


def test(key):
    url = BASE.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + key)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
            dt = time.time() - t0
            return r.status, repr(body["choices"][0]["message"]["content"]), dt
    except urllib.error.HTTPError as e:
        dt = time.time() - t0
        try:
            msg = e.read().decode()[:200]
        except Exception:
            msg = ""
        return e.code, msg, dt
    except Exception as e:
        return "EXC", str(e)[:200], time.time() - t0


for i, k in enumerate(KEYS, 1):
    status, msg, dt = test(k)
    print("key{} {} -> {} ({:.2f}s) {}".format(i, redact(k), status, dt, msg))
    time.sleep(1.5)  # avoid rate limiting
