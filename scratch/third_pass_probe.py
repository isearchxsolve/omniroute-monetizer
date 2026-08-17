#!/usr/bin/env python3
"""Third pass: api-airforce after its 62s cooldown; nous-research model-id fix."""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "provider_deep_probe.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json",
           "Content-Type": "application/json"}


def post(url, payload, timeout=60):
    try:
        r = requests.post(url, json=payload, timeout=timeout, headers=HEADERS)
        return r.status_code, r.text[:500]
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:150]}"


def main() -> int:
    third = {}

    # --- nous-research: inspect model entry structure first ---
    print("nous-research: inspecting model list structure...")
    r = requests.get("https://inference-api.nousresearch.com/v1/models",
                     timeout=30, headers=HEADERS)
    nous_ids = []
    if r.status_code == 200:
        j = r.json()
        items = j.get("data", [])
        print(f"  {len(items)} models; first entry keys: "
              f"{sorted(items[0].keys()) if items else 'n/a'}")
        print(f"  first entry: {json.dumps(items[0])[:400]}")
        # collect candidate ids: prefer fields other than canonical_slug
        for it in items[:50]:
            for key in ("id", "model", "name", "slug"):
                v = it.get(key)
                if isinstance(v, str) and v and "/" in v:
                    nous_ids.append(v)
                    break
    # try a few distinct ids
    tried = []
    seen = set()
    for mid in nous_ids:
        if mid in seen:
            continue
        seen.add(mid)
        if len(tried) >= 3:
            break
        time.sleep(1.5)
        st, body = post("https://inference-api.nousresearch.com/v1/chat/completions",
                        {"model": mid, "messages": [{"role": "user", "content": "hi"}]})
        tried.append({"model": mid, "status": st, "snippet": body[:250]})
        print(f"  [{st}] {mid[:45]:45s} {body[:150]!r}")
    third["nous-research"] = tried

    # --- api-airforce: wait out the cooldown, then ONE request ---
    print("\napi-airforce: waiting 70s for guaranteed-response window...")
    time.sleep(70)
    st, body = post("https://api.airforce/v1/chat/completions",
                    {"model": "devstral-latest",
                     "messages": [{"role": "user", "content": "Reply with the single word: hello"}],
                     "max_tokens": 16, "stream": False})
    third["api-airforce"] = {"status": st, "snippet": body}
    print(f"  [{st}] {body[:300]!r}")

    data = json.loads(OUT.read_text(encoding="utf-8"))
    data["third_pass"] = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "results": third}
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nupdated {OUT} with third_pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
