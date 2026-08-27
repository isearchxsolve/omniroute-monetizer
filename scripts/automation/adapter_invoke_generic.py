# -*- coding: utf-8 -*-
"""GENERIC ADAPTER-INVOCATION DRIVER — one script, any chat provider.

The Adapter Thesis says: don't rebuild the request, make the site's OWN app send it.
deepseek proved it in 5s. This generalizes deepseek's hand-tuned script into a single
driver that works on any signed-in chat tab, so the remaining providers (chatglm x-sign,
innerai, cerebras, ...) cost a small constant each instead of ~30 min of protocol
archaeology.

Generic pipeline:
  1. Focus the tab matching --host substring.
  2. Find the input: <textarea> first, else [contenteditable=true].
  3. Inject the sentinel via the NATIVE setter (textarea) or execCommand insertText
     (contenteditable), then dispatch 'input' so the framework's state model sees it.
  4. Trigger the site's own send: Enter keydown; if the input is not consumed, click the
     best send button.
  5. Verdict with a GENERIC false-positive guard: the phrase must appear in a container
     that (a) did NOT exist before send, and (b) is SHORT (~the phrase alone, not the full
     echoed prompt). This rules out matching the user's own message bubble without needing
     provider-specific assistant selectors.

Replay-only: one message on the operator's already-signed-in session. No signup/login/
wall-solving. Attach-only via debuggerAddress. NEVER calls driver.quit().
"""
import argparse
import json
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROMPT = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
EXPECT = "the holy cow jumps over the stricks"
ANSWER_TIMEOUT_S = 90


def attach():
    opts = Options()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    d = webdriver.Chrome(options=opts)
    d.set_script_timeout(ANSWER_TIMEOUT_S + 30)
    return d


def focus(driver, host_sub):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if host_sub in driver.current_url:
                driver.execute_cdp_cmd("Page.bringToFront", {})
                return driver.current_url
        except Exception:
            continue
    return None


# ---- snapshot of existing message-container texts (for the recency guard) ----
SNAP_JS = r"""
(function(){
  const out = [];
  const seen = new Set();
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  document.querySelectorAll(sels).forEach(el=>{
    if(seen.has(el)) return; seen.add(el);
    const t=(el.innerText||'').trim();
    if(t) out.push(t);
  });
  return out;
})()
"""

# ---- inject into textarea or contenteditable ----
INJECT_JS = r"""
(function(prompt){
  // textarea path
  let ta = document.querySelector('textarea');
  if(ta){
    ta.focus();
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(ta, prompt);
    ta.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'textarea', len:(ta.value||'').length};
  }
  // contenteditable path
  let ce = document.querySelector('[contenteditable="true"]');
  if(ce){
    ce.focus();
    let inserted=false;
    try{ inserted=document.execCommand('insertText', false, prompt); }catch(e){}
    if(!inserted){ ce.textContent = prompt; }
    ce.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'contenteditable', len:(ce.innerText||'').length};
  }
  return {ok:false, why:'no textarea or contenteditable found'};
})(arguments[0])
"""

# ---- trigger send: Enter, report whether input was consumed ----
SEND_JS = r"""
(function(){
  const el = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
  if(!el) return {ok:false, why:'no input'};
  const opts={key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true};
  el.dispatchEvent(new KeyboardEvent('keydown',opts));
  el.dispatchEvent(new KeyboardEvent('keypress',opts));
  el.dispatchEvent(new KeyboardEvent('keyup',opts));
  const left = (el.value!==undefined?el.value:el.innerText)||'';
  return {ok:true, method:'enter', remaining:left.length};
})()
"""

# ---- fallback: click best send button ----
CLICK_JS = r"""
(function(){
  const cands = Array.from(document.querySelectorAll('button,[role="button"]'))
    .filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&!el.disabled;});
  if(!cands.length) return {ok:false, why:'no enabled button'};
  const pick = cands.find(el=>/send|submit|arrow/i.test((el.getAttribute('aria-label')||'')+(el.className||'')))
            || cands[cands.length-1];
  pick.click();
  return {ok:true, picked:((pick.getAttribute('aria-label')||pick.className||'')+'').slice(0,60)};
})()
"""

# ---- poll: phrase in a NEW, SHORT container ----
POLL_JS = r"""
const expect = arguments[0];
const before = arguments[1];      // array of pre-existing container texts
const cb = arguments[2];
const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
const want = flat(expect);
const beforeSet = new Set(before.map(flat));
const t0 = Date.now();
const timer = setInterval(()=>{
  const seen = new Set();
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  let strong=null, weak=null;
  document.querySelectorAll(sels).forEach(el=>{
    if(seen.has(el)) return; seen.add(el);
    const t=(el.innerText||'').trim();
    if(!t || !flat(t).includes(want)) return;
    const isNew = !beforeSet.has(flat(t));
    const isShort = t.length <= (expect.length*1.6);   // reply alone, not full echoed prompt
    if(isNew && isShort && !strong){ strong={len:t.length, text:t.slice(0,200)}; }
    else if(isNew && !weak){ weak={len:t.length, text:t.slice(0,200)}; }
  });
  if(strong){ clearInterval(timer); cb({found:true, strength:'strong', ms:Date.now()-t0, hit:strong}); }
  else if(Date.now()-t0 > TIMEOUT_MS){
    clearInterval(timer);
    cb({found:!!weak, strength: weak?'weak-only':'none', ms:Date.now()-t0, hit:weak});
  }
}, 800);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="URL substring of the target tab")
    ap.add_argument("--slug", default=None, help="output slug (defaults to host)")
    args = ap.parse_args()
    slug = args.slug or re.sub(r"[^a-z0-9]+", "_", args.host).strip("_")

    driver = attach()
    url = focus(driver, args.host)
    if not url:
        print("NO TAB matching %r" % args.host)
        return 3
    print("on:", url)

    before = driver.execute_script("return " + SNAP_JS.strip()) or []
    print("pre-existing message containers:", len(before))

    r1 = driver.execute_script("return " + INJECT_JS.strip(), PROMPT)
    print("inject:", r1)
    if not r1.get("ok"):
        print("FAIL:", r1.get("why"))
        return 1

    r2 = driver.execute_script("return " + SEND_JS.strip())
    print("send:", r2)
    time.sleep(2)
    if r2.get("remaining", 0) > 0:
        r3 = driver.execute_script("return " + CLICK_JS.strip())
        print("enter did not consume -> button click:", r3)
        time.sleep(2)

    poll = POLL_JS.replace("TIMEOUT_MS", str(ANSWER_TIMEOUT_S * 1000))
    print("polling (up to %ds)..." % ANSWER_TIMEOUT_S)
    r4 = driver.execute_async_script(poll, EXPECT, before)
    print("poll result:", {k: r4.get(k) for k in ("found", "strength", "ms")})
    if r4.get("hit"):
        print("hit len=%d text=%r" % (r4["hit"]["len"], r4["hit"]["text"]))

    found = r4.get("found") and r4.get("strength") == "strong"
    verdict = "REPLAY_OK_ADAPTER_INVOCATION" if found else (
        "WEAK_NEEDS_REVIEW" if r4.get("found") else "FAIL")
    print("\nVERDICT:", verdict)

    json.dump({"host": args.host, "url": url, "verdict": verdict,
               "strength": r4.get("strength"), "ms": r4.get("ms"),
               "method": "generic adapter-invocation",
               "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S")},
              open(r"d:\omniroute-monetizer\state\adapter_invoke_%s.json" % slug, "w",
                   encoding="utf-8"), indent=2)
    print("saved state/adapter_invoke_%s.json" % slug)
    print("DONE - do NOT quit.")
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
