# -*- coding: utf-8 -*-
"""Diagnose the DOM of the 7 newly-wired chat tabs for bridge compatibility.

For each tab: switch to it, report (a) the composer element the bridge would inject
into, (b) which message-container selectors from POLL_JS actually match, and (c) a
sample of the newest message container's class. This predicts which hosts the generic
ChromeReplayClient can serve vs. which need custom selectors. Read-only (no typing).
"""
import json, time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

HOSTS = {
    "copilot.microsoft.com": "copilot.microsoft.com",
    "claude.ai": "claude.ai",
    "grok.com": "grok.com",
    "duck.ai": "duck.ai",
    "genspark.ai": "genspark.ai",
    "v0.app": "v0.app",
    "yi.baichuan-ai.com": "baichuan-ai.com",
}

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

DIAG_JS = r"""
try {
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  // composer the bridge would use
  let ta = Array.from(document.querySelectorAll('textarea')).find(el=>visible(el));
  let ce = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]')).find(el=>visible(el));
  const composer = ta ? ('textarea#'+(ta.id||'(noid)')+' ph="'+(ta.placeholder||'').slice(0,30)+'"')
                 : ce ? ('contenteditable '+(ce.className||'').slice(0,40))
                 : 'NONE';
  // message-container selectors from POLL_JS
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  const conts = Array.from(document.querySelectorAll(sels)).filter(el=>visible(el) && (el.innerText||'').trim());
  const last = conts[conts.length-1];
  return JSON.stringify({
    composer: composer,
    containerCount: conts.length,
    lastContainerClass: last ? ((last.className||'')+'').replace(/\s+/g,' ').slice(0,80) : '(none)',
    lastContainerText: last ? (last.innerText||'').replace(/\s+/g,' ').slice(0,60) : '(none)',
    dataRoles: Array.from(new Set(Array.from(document.querySelectorAll('[data-role]')).map(e=>e.getAttribute('data-role')))).slice(0,6)
  });
} catch(e){ return JSON.stringify({error:String(e)}); }
"""

def host(u):
    try: return urlparse(u).netloc.lower()
    except Exception: return ""

found = {}
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
    except Exception:
        continue
    u = driver.current_url or ""
    for seat_host, substr in HOSTS.items():
        if seat_host in found: continue
        if substr in u:
            found[seat_host] = u
            break

for seat_host, substr in HOSTS.items():
    if seat_host not in found:
        print("\n### %-24s NO TAB FOUND" % seat_host); continue
    # switch to that tab
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if substr in (driver.current_url or ""):
                break
        except Exception:
            continue
    try:
        raw = driver.execute_script(DIAG_JS)
        info = json.loads(raw) if raw else {"error":"empty"}
    except Exception as e:
        info = {"error": str(e)}
    print("\n### %-24s" % seat_host)
    print("  composer:", info.get("composer"))
    print("  containers:", info.get("containerCount"),
          "| dataRoles:", info.get("dataRoles"))
    print("  lastClass:", info.get("lastContainerClass"))
    print("  lastText:", info.get("lastContainerText"))
