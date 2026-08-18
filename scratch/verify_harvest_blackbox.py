"""Verify blackbox login state + harvest cookie header + inject + E2E."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402

PORT = 9223
KEYS = os.path.join(os.path.dirname(__file__), "..", "state", "generated_keys.json")
SESSION_COOKIES = ["next-auth.session-token", "__Secure-authjs.session-token",
                   "authjs.session-token"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    page = None
    for pg in ctx.pages:
        if "blackbox.ai" in pg.url:
            page = pg
            break

    # Navigate to app root to check signed-in state
    if page:
        try:
            page.goto("https://app.blackbox.ai/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"nav err: {e}")
        print(f"URL: {page.url[:120]}")
        print(f"title: {page.title()!r}")
        body = page.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : ''")
        print(f"body: {body[:200]!r}")

    # Collect blackbox cookies
    cookies = []
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "blackbox.ai" in dom:
            cookies.append(c)
    names = {c["name"] for c in cookies}
    sess = [n for n in SESSION_COOKIES if n in names]
    print(f"\nblackbox cookies: {len(cookies)}, session cookies: {sess}")
    if not sess:
        print("!! no session cookie — login incomplete")
        browser.close()
        sys.exit(1)

    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    browser.close()

# Save harvested header (T11: never print value)
with open(KEYS, "r", encoding="utf-8") as f:
    keys = json.load(f)
keys["cookie_header:blackbox-web"] = {
    "cookie_header": header,
    "cookie_names": sorted(names),
    "harvested_at": datetime.now(timezone.utc).isoformat(),
    "source": "cdp9223 pure chrome visual login",
    "note": "post-Google-SSO next-auth.session-token present",
}
with open(KEYS, "w", encoding="utf-8") as f:
    json.dump(keys, f, indent=2)
print(f"saved cookie_header:blackbox-web (len={len(header)})")

# Inject into OmniRoute
api = OmniRouteAPI()
api.login()

# find existing blackbox-web connection or create
conns = api.get_connections()
cid = None
for c in conns:
    if c.get("provider") == "blackbox-web":
        cid = c.get("id")
        break

if cid:
    r = api.update_connection(cid, {"apiKey": header, "isActive": True})
    print(f"updated existing blackbox-web conn {cid}: HTTP {r['http_status']}")
else:
    resp = api.session.post(f"{api.api}/providers", json={
        "provider": "blackbox-web",
        "name": "blackbox-web (auto-harvested)",
        "authType": "apikey",
        "apiKey": header,
        "isActive": True,
    }, timeout=20)
    print(f"create blackbox-web conn: HTTP {resp.status_code}")
    try:
        cid = resp.json().get("id") or resp.json().get("connection", {}).get("id")
    except Exception:
        cid = None
    print(f"  cid={cid}")

if cid:
    sr = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    print(f"sync-models -> HTTP {sr.status_code}")
    t = api.test_connection(cid)
    tj = t.get("result") or {}
    print(f"test_connection: HTTP {t['http_status']} valid={tj.get('valid')} "
          f"msg={str(tj.get('message') or tj.get('error'))[:150]}")

    # E2E with prefixed model — get real model list first
    print("\n--- models for connection ---")
    mr = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
    models = []
    if mr.status_code == 200:
        try:
            mj = mr.json()
            mlist = mj.get("models") if isinstance(mj, dict) else mj
            for m in (mlist or [])[:10]:
                mid = m.get("id") if isinstance(m, dict) else str(m)
                if mid:
                    models.append(mid)
        except Exception:
            pass
    print(f"  models: {models}")

    print("\n--- E2E /v1/chat/completions ---")
    targets = [f"blackbox-web/{m}" for m in models[:2]] or ["blackbox-web/blackbox-ai"]
    for model in targets:
        try:
            resp = api.session.post(
                f"{api.v1}/chat/completions",
                json={"model": model,
                      "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                      "max_tokens": 60},
                timeout=90,
            )
            print(f"{model}: HTTP {resp.status_code}")
            txt = resp.text
            if resp.status_code == 200:
                if txt.lstrip().startswith("data:"):
                    # SSE stream — collect deltas
                    content = ""
                    for line in txt.splitlines():
                        line = line.strip()
                        if line.startswith("data:") and "[DONE]" not in line:
                            try:
                                j = json.loads(line[5:].strip())
                                d = j.get("choices", [{}])[0].get("delta", {})
                                content += d.get("content") or ""
                            except Exception:
                                pass
                    print(f"  [LIVE-SSE] content: {content[:120]!r}")
                else:
                    try:
                        j = resp.json()
                        print(f"  [LIVE] content: {j['choices'][0]['message']['content'][:120]!r}")
                    except Exception:
                        print(f"  body: {txt[:200]}")
            else:
                print(f"  body: {txt[:300]}")
        except Exception as e:
            print(f"{model}: EXC {type(e).__name__}: {e}")
