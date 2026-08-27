# -*- coding: utf-8 -*-
"""Read-only sign-in probe of the UNCOVERED open tabs (port 9222).

Attaches to the live automation browser, switches to each ALREADY-OPEN tab whose host
is in the uncovered list, and reports sign-in signals: visible composer, visible
login/signup CTA, and a body snippet. Opens NO new tabs, closes NOTHING, never quits.
"""
import json, time, sys, pathlib
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

UNCOVERED = ["innerai", "claude.ai", "copilot.microsoft", "duck.ai", "genspark",
             "grok.com", "labs.google", "nemovideo", "v0.app", "baichuan"]

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

PROBE_JS = r"""
try {
  const body = document.body ? document.body.innerText : '';
  const composer = !!document.querySelector(
    'textarea, div[contenteditable="true"], [role="textbox"], input[type="text"][placeholder]');
  const cta = !!Array.from(document.querySelectorAll('button,a,[role="button"]'))
    .find(el => /log ?in|sign ?in|sign ?up|continue with|use for free/i.test(el.innerText||'')
              && el.offsetParent !== null);
  return JSON.stringify({
    url: location.href, title: document.title,
    composer: composer, loginCta: cta,
    snippet: body.slice(0, 220).replace(/\s+/g, ' ')
  });
} catch (e) { return JSON.stringify({error: String(e)}); }
"""

def host(u):
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""

seen = set()
handles = driver.window_handles
print("window handles:", len(handles))
for h in handles:
    try:
        driver.switch_to.window(h)
    except Exception:
        continue
    u = driver.current_url or ""
    hh = host(u)
    if not any(k in hh or k in u for k in UNCOVERED):
        continue
    if hh in seen:
        continue
    seen.add(hh)
    try:
        raw = driver.execute_script(PROBE_JS)
        info = json.loads(raw) if raw else {"error": "empty"}
    except Exception as e:
        info = {"error": str(e)}
    verdict = ("SIGNED_IN?" if info.get("composer") and not info.get("loginCta")
               else "LOGIN_WALL?" if info.get("loginCta") else "UNCLEAR")
    print("\n### %-24s %s" % (hh, verdict))
    print("  url:", info.get("url", "")[:90])
    print("  composer:", info.get("composer"), "| loginCta:", info.get("loginCta"))
    print("  snippet:", (info.get("snippet") or info.get("error") or "")[:160])

print("\nprobed hosts:", sorted(seen))
