"""Session discovery: check which provider dashboards are still authenticated in the CDP Chrome.
Zero handoff: read-only navigation, no clicks, no forms. Captcha/login walls => mark NOT_AUTHENTICATED."""
import asyncio, json, time
from playwright.async_api import async_playwright

TARGETS = [
    ("openrouter", "https://openrouter.ai/settings/keys"),
    ("anthropic",  "https://platform.claude.com/settings/keys"),
    ("github",     "https://github.com/settings/tokens"),
    ("groq",       "https://console.groq.com/keys"),
    ("gemini",     "https://aistudio.google.com/apikey"),
    ("mistral",    "https://console.mistral.ai/api-keys"),
    ("cohere",     "https://dashboard.cohere.com/api-keys"),
    ("cerebras",   "https://cloud.cerebras.ai/api-keys"),
    ("sambanova",  "https://cloud.sambanova.net/apis"),
    ("together",   "https://api.together.xyz/settings/api-keys"),
    ("deepseek",   "https://platform.deepseek.com/api_keys"),
    ("xai",        "https://console.x.ai/"),
]

AUTH_SIGNALS = [
    "api key", "api keys", "create key", "create api key", "generate", "new key",
    "sk-or-", "sk-ant-", "gsk_", "key name", "your keys", "token", "secret",
]
WALL_SIGNALS = [
    "sign in", "log in", "login", "sign up", "continue with google", "continue with github",
    "email address", "password", "welcome back", "create account",
]

async def probe(page, name, url):
    t0 = time.time()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return {"provider": name, "final_url": url, "status": "NAV_ERROR", "error": str(e)[:150], "elapsed": round(time.time()-t0,1)}
    await asyncio.sleep(2.5)  # let SPA hydrate
    final_url = page.url
    title = await page.title()
    body = ""
    try:
        body = await page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 3000)")
    except Exception:
        pass
    low = (body + " " + title).lower()
    auth_hits = [s for s in AUTH_SIGNALS if s in low]
    wall_hits = [s for s in WALL_SIGNALS if s in low]
    # captcha check (policy: discard immediately)
    captcha = any(s in low for s in ("captcha", "hcaptcha", "recaptcha", "turnstile", "verify you are human"))
    if captcha:
        status = "CAPTCHA_DISCARD"
    elif wall_hits and not auth_hits:
        status = "NOT_AUTHENTICATED"
    elif auth_hits:
        status = "AUTHENTICATED"
    else:
        status = "UNKNOWN"
    return {
        "provider": name,
        "target_url": url,
        "final_url": final_url,
        "title": title[:80],
        "status": status,
        "auth_hits": auth_hits[:5],
        "wall_hits": wall_hits[:5],
        "body_snippet": body[:200].replace("\n", " | "),
        "elapsed": round(time.time()-t0, 1),
    }

OUT = "state/session_discovery.json"

def save(results):
    with open(OUT, "w") as f:
        json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results}, f, indent=2)

async def main():
    results = []
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=120000)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for name, url in TARGETS:
            r = await probe(page, name, url)
            print(f"{name:12s} {r['status']:20s} -> {r['final_url'][:90]}", flush=True)
            results.append(r)
            save(results)  # incremental: never lose progress
    print(f"\nsaved -> {OUT}")
    auth = [r["provider"] for r in results if r["status"] == "AUTHENTICATED"]
    print("AUTHENTICATED:", ", ".join(auth) if auth else "none")

asyncio.run(main())
