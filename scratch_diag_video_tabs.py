# -*- coding: utf-8 -*-
"""Read-only diagnosis of the two video tabs before capture: labs.google (Flow) and
nemovideo.com. Reports sign-in state, composer, paywall/login text, credit indicators,
and any existing video results. Spends NOTHING."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TARGETS = {
    "labs.google": "labs.google",
    "nemovideo.com": "nemovideo.com",
}

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(25)

# Lightweight: no body.innerText (forces full reflow, hangs on WebGL pages like Flow).
DIAG_JS = r"""
try {
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const ta = Array.from(document.querySelectorAll('textarea')).find(el=>visible(el));
  const ce = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]')).find(el=>visible(el));
  const composer = ta ? ('textarea#'+(ta.id||'(noid)')+' ph="'+(ta.placeholder||'').slice(0,40)+'"')
                 : ce ? ('contenteditable '+(ce.className||'').slice(0,50))
                 : 'NONE';
  // targeted wall/credit probes on small element sets, NOT full body
  const probe = Array.from(document.querySelectorAll('button,a,[class*="credit"],[class*="Credit"],[class*="upgrade"],[class*="plan"]'))
    .map(e=>(e.textContent||'').trim()).filter(Boolean).join(' | ').slice(0,300);
  return JSON.stringify({
    url: location.href,
    title: document.title.slice(0,60),
    composer: composer,
    videoEls: document.querySelectorAll('video').length,
    probe: probe
  });
} catch(e){ return JSON.stringify({error:String(e)}); }
"""

def host_match(u, substr):
    return substr in (u or "")

for seat_host, substr in TARGETS.items():
    found = False
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
        except Exception:
            continue
        u = driver.current_url or ""
        if host_match(u, substr):
            found = True
            try:
                raw = driver.execute_script(DIAG_JS)
                info = json.loads(raw) if raw else {"error":"empty"}
            except Exception as e:
                info = {"error": str(e)}
            print("\n### %s" % seat_host)
            for k in ("url","title","composer","videoEls","probe","error"):
                if k in info:
                    print("  %s: %s" % (k, info[k]))
            break
    if not found:
        print("\n### %s  NO TAB FOUND" % seat_host)
