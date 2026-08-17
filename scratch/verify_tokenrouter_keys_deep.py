# Deep-check the 5 keys that returned 400 on /models:
# capture the actual error body, and try chat completions directly.
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "https://api.tokenrouter.com/v1"
MODEL = "qwen/qwen3.8-max-free"

KEYS = [
    "sk-vpHUXIq5GyO9YQipqHgBHERF24SOCseXOCFjjxfG5cY685iL",
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
]


def mask(k: str) -> str:
    return k[:6] + "..." + k[-4:]


def http(method, url, key, payload=None):
    headers = {"Authorization": f"Bearer {key}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, time.time() - t0, r.read().decode("utf-8")[:400]
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")[:400]
        except Exception:
            body = ""
        return e.code, time.time() - t0, body
    except Exception as e:
        return str(e), time.time() - t0, ""


def main():
    for i, key in enumerate(KEYS, 1):
        print(f"=== [{i}/5] {mask(key)} ===")
        s, dt, body = http("GET", BASE + "/models", key)
        print(f"  /models -> {s} ({dt:.2f}s) body: {body!r}")
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "temperature": 0,
            "max_tokens": 64,
        }
        s2, dt2, body2 = http("POST", BASE + "/chat/completions", key, payload)
        print(f"  /chat/completions -> {s2} ({dt2:.2f}s) body: {body2!r}")
        print()


if __name__ == "__main__":
    main()
