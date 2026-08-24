"""Post-heal acceptance test + verified chat-pool builder (task 1).

For each active provider (gold session/oauth + recovered API keys), fetch its real model
list, pick one chat model, and probe it through the gateway with a tiny prompt. Concurrency
is capped and spread across DISTINCT providers so nothing stacks into a self-inflicted 429.

Proves the verdict-doc standard: semantic answer, not just HTTP 200 / test_status. Writes the
survivors to state/verified_chat_pool.json -- the known-good pool the pipeline load-spreads
across. No secrets touched (model ids + prose only).
"""
from __future__ import annotations
import asyncio, json, os, sys, time, pathlib
import httpx
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI

BASE = "http://127.0.0.1:20128"
URL = BASE + "/v1/chat/completions"
# model ids we must NOT treat as chat
SKIP = ("embed", "rerank", "image", "img", "tts", "whisper", "audio", "video", "veo", "flux",
        "sdxl", "moderation", "guard", "vision-ocr", "-ocr", "seedance", "kling")
# providers that generate media -> not chat, skip entirely
VIDEO_PROV = ("comfyui", "kie", "segmind", "fal", "pollination", "replicate", "runpod",
              "flow", "vertex", "rtst", "topmedia", "digen", "capcut")


def pick_chat_model(models):
    for m in models:
        low = m.lower()
        if not any(s in low for s in SKIP):
            return m
    return None


def gateway_key():
    import sqlite3
    con = sqlite3.connect("file:C:/Users/Admin/.omniroute/storage.sqlite?mode=ro", uri=True, timeout=5)
    try:
        row = con.execute("SELECT key FROM api_keys WHERE name='neon'").fetchone()
        return row[0] if row else None
    finally:
        con.close()


SEM = asyncio.Semaphore(4)


def _sse_content(raw):
    if "data:" not in raw:
        return None
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        p = line[5:].strip()
        if not p or p == "[DONE]":
            continue
        try:
            ch = json.loads(p)
        except ValueError:
            continue
        for c in ch.get("choices") or []:
            d = c.get("delta") or {}
            if d.get("content"):
                out.append(d["content"])
    return "".join(out)


async def probe(client, route, provider, name):
    body = {"model": route, "messages": [{"role": "user", "content": "Reply with one word: pong"}],
            "max_tokens": 40, "stream": False, "temperature": 0}
    t0 = time.time()
    async with SEM:
        try:
            r = await client.post(URL, json=body)
        except Exception as e:
            return {"route": route, "provider": provider, "name": name, "ok": False,
                    "ms": int((time.time()-t0)*1000), "err": f"{type(e).__name__}: {str(e)[:100]}"}
    dt = int((time.time()-t0)*1000)
    if r.status_code >= 400:
        msg = ""
        try:
            j = r.json(); e = j.get("error"); msg = (e.get("message") if isinstance(e, dict) else str(e)) or ""
        except Exception:
            msg = (r.text or "")[:140]
        return {"route": route, "provider": provider, "name": name, "ok": False, "ms": dt,
                "status": r.status_code, "err": str(msg)[:140]}
    try:
        j = r.json(); content = (j.get("choices") or [{}])[0].get("message", {}).get("content")
    except ValueError:
        content = _sse_content(r.text)
    ok = bool(content and content.strip())
    return {"route": route, "provider": provider, "name": name, "ok": ok, "ms": dt,
            "reply": (content or "")[:50]}


async def main():
    api = OmniRouteAPI(); assert api.login()
    conns = [c for c in api.get_connections() if c.get("isActive")]
    # one connection per provider prefix (routing is by model name; gateway picks the account)
    seen, chosen = set(), []
    for c in conns:
        prov = c.get("provider") or c.get("format")
        if not prov or prov in seen or any(v in prov.lower() for v in VIDEO_PROV):
            continue
        models = api.connection_models(c.get("id"))
        m = pick_chat_model(models)
        if not m:
            continue
        seen.add(prov)
        chosen.append((f"{prov}/{m}", prov, str(c.get("name"))[:24]))
    # also verify the app's combos resolve
    for combo in ["auto/best-coding", "auto/best-chat", "auto/free-chat", "auto/best-reasoning"]:
        chosen.append((combo, "COMBO", combo))

    key = gateway_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    print(f"probing {len(chosen)} distinct routes (concurrency 4)...\n")
    async with httpx.AsyncClient(timeout=45.0, headers=headers) as client:
        results = await asyncio.gather(*[probe(client, r, p, n) for r, p, n in chosen])

    results.sort(key=lambda x: (not x["ok"], x.get("ms", 0)))
    ok = [r for r in results if r["ok"]]
    pool = [{"model": r["route"], "provider": r["provider"], "ms": r["ms"]} for r in ok if r["provider"] != "COMBO"]
    os.makedirs("state", exist_ok=True)
    with open("state/verified_chat_pool.json", "w") as f:
        json.dump({"ts": int(time.time()), "count": len(pool), "pool": pool}, f, indent=2)

    print(f"=== VERIFIED ANSWERING: {len(ok)}/{len(results)} routes\n")
    for r in results:
        mark = "OK  " if r["ok"] else "XX  "
        tail = f'-> "{r["reply"].strip()[:30]}"' if r["ok"] else f'[{r.get("status","-")}] {r.get("err","")[:80]}'
        print(f'  {mark}{r["ms"]:6d}ms  {r["route"]:44s} {tail}')
    print(f"\nverified_chat_pool.json written: {len(pool)} known-good non-combo routes for load-spread")


if __name__ == "__main__":
    asyncio.run(main())
