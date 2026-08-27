import json, sys
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

# cerebras page state
print("=== CEREBRAS page state ===")
with Page("chat.cerebras.ai", port=9222) as p:
    try:
        txt = p.evaluate("document.body.innerText.slice(0,600)")
        print("body text:", repr(txt))
    except Exception as e:
        print("text err:", e)
    # try to find model list in page / API
    try:
        models = p.evaluate("""(async()=>{try{
            const r=await fetch('/api/models',{credentials:'include'});
            return r.status+' '+(await r.text()).slice(0,300);
        }catch(e){return 'ERR '+e}})()""")
        print("/api/models:", models)
    except Exception as e:
        print("models err:", e)

print("\n=== GEMINI page state ===")
with Page("gemini.google.com", port=9222) as p:
    try:
        txt = p.evaluate("document.body.innerText.slice(0,400)")
        print("body text:", repr(txt))
    except Exception as e:
        print("text err:", e)
    # signed-in indicator
    try:
        si = p.evaluate("""(()=>{const el=document.querySelector('img[alt], [aria-label*="account"], [aria-label*="Account"]');
            return el ? (el.alt||el.getAttribute('aria-label')) : 'none'})()""")
        print("account indicator:", si)
    except Exception as e:
        print("si err:", e)
