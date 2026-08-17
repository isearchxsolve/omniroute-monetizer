# Verify TokenRouter API keys against the upstream endpoint.
# AGENTS.md rule: never report a credential as usable unless verified with a
# successful authenticated 200 OK directly against the external provider endpoint.
# Uses a valid, standard chat completion payload (no tiny max_tokens).
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "https://api.tokenrouter.com/v1"
MODEL = "qwen/qwen3.8-max-free"

KEYS = [
    "sk-vpHUXIq5GyO9YQipqHgBHERF24SOCseXOCFjjxfG5cY685iL",
    "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg",
    "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
]


def mask(k: str) -> str:
    return k[:6] + "..." + k[-4:]


def check_models_endpoint(key: str):
    req = urllib.request.Request(
        BASE + "/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            ids = [m.get("id") for m in data.get("data", [])]
            return r.status, ids
    except urllib.error.HTTPError as e:
        return e.code, []
    except Exception as e:
        return str(e), []


def check_chat(key: str):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Reply with exactly: OK"},
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode("utf-8"))
            dt = time.time() - t0
            content = ""
            try:
                content = body["choices"][0]["message"]["content"]
            except Exception:
                pass
            return r.status, dt, (content or "")[:80]
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")[:200]
        except Exception:
            err = ""
        return e.code, time.time() - t0, err
    except Exception as e:
        return str(e), time.time() - t0, ""


def main():
    results = []
    # First: quick /models check per key (auth validity)
    for i, key in enumerate(KEYS, 1):
        status, ids = check_models_endpoint(key)
        has_model = MODEL in ids
        print(f"[{i}/7] {mask(key)}  /models -> {status}  "
              f"models={len(ids)}  has_target_model={has_model}")
        results.append({"key": mask(key), "models_status": status,
                        "n_models": len(ids), "has_model": has_model})

    # Then: one real chat completion per key that passed /models
    print("\n--- chat completion checks (model: %s) ---" % MODEL)
    for i, res in enumerate(results):
        if res["models_status"] != 200:
            res["chat"] = "SKIPPED (auth failed)"
            print(f"[{i+1}/7] {res['key']}  chat -> SKIPPED")
            continue
        status, dt, info = check_chat(KEYS[i])
        res["chat"] = {"status": status, "secs": round(dt, 2), "info": info}
        print(f"[{i+1}/7] {res['key']}  chat -> {status} in {dt:.2f}s  {info!r}")

    out = "d:/omniroute-monetizer/scratch/tokenrouter_key_check_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    ok = sum(1 for r in results
             if isinstance(r.get("chat"), dict) and r["chat"]["status"] == 200)
    print(f"\nSUMMARY: {ok}/7 keys verified with 200 OK chat completions")
    print(f"Results written to {out}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
