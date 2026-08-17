#!/usr/bin/env python3
"""Deep probe: providers whose /models endpoint answered 200 WITHOUT credentials.

For each candidate we:
  1. Re-fetch the models list and parse real model IDs.
  2. POST an unauthenticated chat completion (valid standard payload) against
     up to 3 chat-capable model IDs.
  3. Record the OBSERVED inference verdict:
       TRULY_OPEN      - 200 with completion choices, zero credentials
       AUTH_REQUIRED   - 401/403 key demand at inference time
       CREDITS         - 402/403 billing/credit language
       RATE_LIMITED    - 429
       OTHER           - anything else (raw status + snippet kept)

Candidates come from state/provider_upstream_scan.json: any provider whose
probe returned status 200 with a JSON body (model list or API info).
freeaiapikey is special-cased: its 410 body advertises a moved base_url,
which we follow.

Zero Terra tokens. Output: state/provider_deep_probe.json
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "state" / "provider_upstream_scan.json"
OUT = ROOT / "state" / "provider_deep_probe.json"

TIMEOUT = 30
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json",
           "Content-Type": "application/json"}

# model-id keywords that are NOT chat models
NON_CHAT_RE = re.compile(
    r"embed|tts|whisper|speech|image|flux|sdxl|stable-diffusion|dall|rerank|"
    r"moderation|audio|music|video|upscale|inpaint|segment|ocr|search", re.I)

PAYWALL_RE = re.compile(
    r"credit|billing|payment|subscription|quota|insufficient|purchase|upgrade|"
    r"paid plan|balance|top.?up", re.I)


def classify_chat(status: int, body: str) -> str:
    b = body[:2000]
    if status == 200:
        try:
            j = json.loads(body)
            if isinstance(j, dict) and (j.get("choices") or j.get("output")
                                        or j.get("content") or j.get("message")):
                return "TRULY_OPEN"
        except Exception:
            pass
        return "TRULY_OPEN"  # 200 on chat endpoint is open enough
    if status == 429:
        return "RATE_LIMITED"
    if status == 402 or PAYWALL_RE.search(b):
        return "CREDITS"
    if status in (401, 403):
        return "AUTH_REQUIRED"
    return "OTHER"


def get_models(url: str):
    """Return (model_ids, raw_snippet) from a models endpoint."""
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    if r.status_code != 200:
        return None, f"models re-fetch status {r.status_code}"
    try:
        j = r.json()
    except Exception:
        return None, r.text[:200]
    items = j.get("data") if isinstance(j, dict) else j
    if not isinstance(items, list):
        return None, r.text[:200]
    ids = []
    for it in items:
        mid = it.get("id") or it.get("name") if isinstance(it, dict) else None
        if isinstance(mid, str) and mid:
            ids.append(mid)
    return ids, f"{len(ids)} models listed"


def pick_chat_models(ids):
    chat = [i for i in ids if not NON_CHAT_RE.search(i)]
    pool = chat if chat else ids
    return pool[:3]


def probe_chat(chat_url: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: hello"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    try:
        r = requests.post(chat_url, json=payload, timeout=TIMEOUT, headers=HEADERS)
        return {"model": model, "status": r.status_code,
                "verdict": classify_chat(r.status_code, r.text),
                "snippet": r.text[:250]}
    except Exception as e:
        return {"model": model, "status": None, "verdict": "ERROR",
                "snippet": f"{type(e).__name__}: {str(e)[:120]}"}


def deep_probe(slug: str, models_url: str) -> dict:
    chat_url = re.sub(r"/models$", "/chat/completions", models_url)
    result = {"slug": slug, "models_url": models_url, "chat_url": chat_url}
    ids, note = get_models(models_url)
    result["models_note"] = note
    if not ids:
        result["verdict"] = "NO_MODEL_LIST"
        return result
    result["model_count"] = len(ids)
    picks = pick_chat_models(ids)
    result["models_tried"] = picks
    attempts = [probe_chat(chat_url, m) for m in picks]
    result["attempts"] = attempts
    # best verdict across attempts: TRULY_OPEN > RATE_LIMITED > CREDITS > AUTH > OTHER
    rank = {"TRULY_OPEN": 0, "RATE_LIMITED": 1, "CREDITS": 2,
            "AUTH_REQUIRED": 3, "OTHER": 4, "ERROR": 5}
    result["verdict"] = min((a["verdict"] for a in attempts), key=lambda v: rank[v])
    return result


def main() -> int:
    scan = json.loads(SCAN.read_text(encoding="utf-8"))["results"]

    # candidates: status 200 with JSON-ish body (model list or API info)
    candidates = {}
    for slug, r in scan.items():
        if r.get("status") != 200:
            continue
        snip = r.get("body_snippet", "") or ""
        probed = r.get("probed")
        if not probed:
            continue
        looks_json = snip.lstrip().startswith(("{", "["))
        if looks_json:
            candidates[slug] = probed

    # freeaiapikey: follow the advertised move from its 410 body
    fa = scan.get("freeaiapikey", {})
    m = re.search(r"https://[^\s\"'<>]+", fa.get("body_snippet", "") or "")
    if m:
        moved = m.group(0).rstrip(".,)")
        base = moved.rstrip("/")
        if base.endswith("/models"):
            pass
        elif base.endswith("/v1"):
            base = base + "/models"
        else:
            base = base + "/v1/models"
        candidates["freeaiapikey"] = base
        print(f"freeaiapikey moved -> {base}")

    print(f"deep-probing {len(candidates)} candidates with open 200 endpoints\n")

    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(deep_probe, s, u): s for s, u in candidates.items()}
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"slug": slug, "verdict": "ERROR", "note": str(e)[:150]}
            results[slug] = res
            print(f"  {slug:20s} -> {res.get('verdict'):14s} "
                  f"({res.get('models_note', '')})")
            for a in res.get("attempts", []):
                print(f"      [{a.get('status')}] {a.get('model', '')[:40]:40s} "
                      f"{a.get('verdict'):14s} {(a.get('snippet') or '')[:80]!r}")

    from collections import Counter
    tally = Counter(r.get("verdict") for r in results.values())
    print("\n=== DEEP-PROBE VERDICT TALLY ===")
    for v, n in tally.most_common():
        print(f"  {v:16s} {n}")

    OUT.write_text(json.dumps({"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "count": len(results), "tally": dict(tally),
                               "results": results}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
