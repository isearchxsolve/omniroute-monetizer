# -*- coding: utf-8 -*-
"""DEFINITIVE ordering check: is the deepseek assistant reply FRESH (after my injected
user message) or pre-existing / an echo of the user bubble?

Read-only. We walk the message containers in DOM order, classify each as user vs
assistant, and confirm:
  (a) the LAST user message is my injected prompt (len~80, contains 'Repeat exactly'),
  (b) an assistant message comes AFTER it, and
  (c) that trailing assistant message contains exactly the 35-char phrase.
If all three hold, the reply is a genuine fresh response to this run.

Attach-only, NEVER driver.quit().
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXPECT = "the holy cow jumps over the stricks"

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(60)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if "deepseek" in driver.current_url:
            break
    except Exception:
        continue
driver.execute_cdp_cmd("Page.bringToFront", {})
print("on:", driver.current_url)

probe = r"""
(function(){
  const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
  const want = flat(EXPECT_PH);
  // Grab every top-level message block in document order.
  const msgs = Array.from(document.querySelectorAll('.ds-message, [class*="ds-message"]'));
  const rows = msgs.map((el,i)=>{
    const t = (el.innerText||'').trim();
    // assistant content carries the markdown assistant class somewhere inside
    const isAsst = !!el.querySelector('.ds-assistant-message-main-content, [class*="assistant"]');
    // user bubbles typically carry the prompt text / a user marker
    const isUser = /repeat exactly|reply exactly|reply with only|omni sentinel/i.test(t) && !isAsst;
    return {i, role: isAsst?'assistant':(isUser?'user':'?'),
            len:t.length, hasPhrase: flat(t).includes(want),
            head:t.slice(0,60)};
  });
  return {count:rows.length, rows};
})()
"""
probe = probe.replace("EXPECT_PH", '"' + EXPECT + '"')
res = driver.execute_script("return " + probe.strip())

rows = res.get("rows", [])
print("\n=== MESSAGES IN DOM ORDER (count=%d) ===" % res.get("count"))
for r in rows:
    mark = " <== PHRASE" if r["hasPhrase"] else ""
    print("  [%2d] %-9s len=%-4d %s%s" % (r["i"], r["role"], r["len"], repr(r["head"]), mark))

# ---- verdict logic ----
# find last user msg index and last assistant-with-phrase index
last_user = max([r["i"] for r in rows if r["role"] == "user"], default=-1)
asst_phrase = [r["i"] for r in rows if r["role"] == "assistant" and r["hasPhrase"]]
last_asst_phrase = max(asst_phrase, default=-1)

print("\n=== VERDICT ===")
print("last user msg index      :", last_user)
print("assistant w/ phrase idx  :", asst_phrase)
if last_asst_phrase > last_user >= 0:
    print("PASS: an assistant message containing the phrase comes AFTER the last user")
    print("      message -> the reply is a FRESH response to this run, not pre-existing.")
elif last_asst_phrase >= 0 and last_user < 0:
    print("AMBIGUOUS: assistant phrase found but no user message classified; check roles.")
else:
    print("FAIL/AMBIGUOUS: phrase-bearing assistant msg is NOT after the last user msg.")
    print("                Could be pre-existing or an echo. Do not claim REPLAY_OK.")
print("DONE (read-only) - do NOT quit.")
