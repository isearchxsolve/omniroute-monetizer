"""Verify which 'gold' (session/oauth, $0) chat routes actually answer RIGHT NOW.

Read-only intent: sends a tiny 'pong' prompt to each candidate concurrently, parses
JSON or SSE, records OK/FAIL + the gateway's own message. Builds the verified pool the
app should load-spread across so parallel agents stop hammering one route into 429.

No secrets touch this path (model ids + prose only). Writes state/gold_chat_probe.json.
"""
from __future__ import annotations
import asyncio, json, os, time
import httpx

BASE = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128").rstrip("/")
if BASE.endswith("/v1"):
    BASE = BASE[:-3]
URL = BASE + "/v1/chat/completions"

# Curated cross-provider set: one strong prose/JSON model per gold provider (diversity =
# load spread) + the 4 routes the app already references, to compare head-to-head.
CANDIDATES = [
    "github/claude-opus-4.8-fast",
    "t3-web/claude-sonnet-4",
    "chatgpt-web/gpt-5.6-thinking",
    "codex/gpt-5.6",
    "xai-oauth/grok-4.5",
    "antigravity/gemini-2.5-flash",
    "agy/gemini-3.7-flash-medium",
    "zai-web/glm-5.2",
    "perplexity-web/pplx-auto",
    "lmarena/claude-sonnet-5",
    "gemini-web/gemini-3.1-flash-lite",
    "kilocode/kilo-auto/balanced",
    "cline/deepseek/deepseek-v4-flash-vision-exp",
    "amazon-q/amazon-q",
    "grok-cli/grok-4.6",
    # app's current references
    "auto/best-coding",
    "auto/best-reasoning",
    "gemini-3.6-flash-high",
    "gemini/gemini-3.6-flash",
]

PROMPT = {"role": "user", "content": "Reply with exactly one word: pong"}
SEM = asyncio.Semaphore(6)  # cap our own concurrency so probing doesn't self-inflict 429


def _sse_content(raw: str):
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


async def probe(client: httpx.AsyncClient, model: str):
    body = {"model": model, "messages": [PROMPT], "max_tokens": 16, "stream": False, "temperature": 0}
    t0 = time.time()
    async with SEM:
        try:
            r = await client.post(URL, json=body)
        except Exception as e:
            return {"model": model, "ok": False, "ms": int((time.time()-t0)*1000), "err": f"{type(e).__name__}: {str(e)[:120]}"}
    dt = int((time.time()-t0)*1000)
    if r.status_code >= 400:
        msg = ""
        try:
            j = r.json(); e = j.get("error"); msg = (e.get("message") if isinstance(e, dict) else str(e)) or ""
        except Exception:
            msg = (r.text or "")[:160]
        return {"model": model, "ok": False, "ms": dt, "status": r.status_code, "err": str(msg)[:200]}
    content = None
    try:
        j = r.json()
        content = (j.get("choices") or [{}])[0].get("message", {}).get("content")
    except ValueError:
        content = _sse_content(r.text)
    ok = bool(content and content.strip())
    return {"model": model, "ok": ok, "ms": dt, "status": r.status_code, "reply": (content or "")[:60]}


async def main():
    async with httpx.AsyncClient(timeout=45.0) as client:
        results = await asyncio.gather(*[probe(client, m) for m in CANDIDATES])
    results.sort(key=lambda x: (not x["ok"], x.get("ms", 0)))
    os.makedirs("state", exist_ok=True)
    with open("state/gold_chat_probe.json", "w") as f:
        json.dump({"ts": int(time.time()), "url": URL, "results": results}, f, indent=2)
    ok = [r for r in results if r["ok"]]
    print(f"VERIFIED {len(ok)}/{len(results)} gold routes answer right now:\n")
    for r in results:
        mark = "OK " if r["ok"] else "XX "
        tail = f'-> "{r["reply"].strip()}"' if r["ok"] else f'[{r.get("status","-")}] {r.get("err","")[:90]}'
        print(f"  {mark}{r['ms']:6d}ms  {r['model']:42s} {tail}")

if __name__ == "__main__":
    asyncio.run(main())
