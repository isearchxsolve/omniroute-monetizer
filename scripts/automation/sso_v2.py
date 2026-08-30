"""Bounded Google-SSO v2 for sign-in-walled tabs on :9222.

For each target: find a Google sign-in affordance in the DOM (broad, shadow-piercing),
click it, and if the flow lands on accounts.google.com, click the profile's OWN account
entry (the signed-in Google identity of the automation profile -- no credentials typed,
no MFA bypassed). Settle, report the final URL. One attempt per seat.
"""
import json
import sys
import time
import urllib.parse

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9222

SEATS = {
    "Akool Video": "https://app.akool.com/",
    "DeepInfra Chat": "https://deepinfra.com/chat",
    "Poe": "https://poe.com/",
    "Puter Chat": "https://puter.com/",
    "Phind": "https://www.phind.com/",
}

JS_CLICK_LOGIN = r"""
(() => {
  try {
    const shadows = (root, acc = []) => {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while (n = w.nextNode()) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
      return acc;
    };
    const roots = [document, ...shadows(document)];
    const words = ['log in', 'login', 'sign in', 'signin', 'sign up', 'signup', '登录', '注册'];
    const cands = [];
    for (const r of roots) {
      for (const el of r.querySelectorAll('button, a, [role="button"]')) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 30 || rect.height < 15) continue;
        const t = (el.innerText || el.textContent || '').toLowerCase().trim();
        if (!t || t.length > 40) continue;
        if (words.some(w => t === w || t.startsWith(w))) {
          cands.push({el, score: rect.width * rect.height + (t.includes('sign up') ? 2000 : 0)});
        }
      }
    }
    if (!cands.length) return {ok: false, error: 'no login affordance'};
    cands.sort((a, b) => b.score - a.score);
    cands[0].el.scrollIntoView({block: 'center'});
    cands[0].el.click();
    return {ok: true, clicked: (cands[0].el.innerText || '').slice(0, 30)};
  } catch (e) { return {ok: false, error: 'JS: ' + e.message}; }
})()
"""

JS_FIND_GOOGLE = r"""
(() => {
  try {
  const shadows = (root, acc = []) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let n;
    while (n = w.nextNode()) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
    return acc;
  };
  const roots = [document, ...shadows(document)];
  const sel = ['a[href*="accounts.google.com"]', 'a[href*="accounts.google"]',
               'button[data-provider="google"]', '[data-oauth-server="google"]',
               '[class*="google"][role="button"]', '[class*="google"] button',
               'button[aria-label*="Google"]', 'a[aria-label*="Google"]'];
  const cands = [];
  for (const r of roots) {
    if (!r || typeof r.querySelectorAll !== 'function') continue;
    for (const sel_i of sel) {
      for (const el of r.querySelectorAll(sel_i)) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 30 || rect.height < 15) continue;
        const st = el.ownerDocument.defaultView.getComputedStyle(el);
        if (st.visibility === 'hidden' || st.display === 'none') continue;
        cands.push({el, score: rect.width * rect.height, text: (el.innerText || '').slice(0, 40)});
      }
    }
    for (const el of r.querySelectorAll('button, a, [role="button"], div[role="button"]')) {
      const t = (el.innerText || el.textContent || '').toLowerCase();
      if ((t.includes('google') && t.length < 60 && t.includes('continue')) || t === 'google' || t.includes('sign in with google')) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 30 || rect.height < 15) continue;
        cands.push({el, score: rect.width * rect.height + 5000, text: t.slice(0, 40)});
      }
    }
  }
  if (!cands.length) return {ok: false, error: 'no google affordance'};
  cands.sort((a, b) => b.score - a.score);
  const el = cands[0].el;
  el.scrollIntoView({block: 'center'});
  el.click();
  return {ok: true, text: cands[0].text, count: cands.length};
  } catch (e) { return {ok: false, error: 'JS: ' + e.message + ' @' + e.lineNumber}; }
})()
"""

JS_ACCOUNT_PICKER = r"""
(() => {
  const rows = document.querySelectorAll('div[data-identifier], div[role="link"][data-identifier], li[data-identifier]');
  if (rows.length) { rows[0].click(); return {ok: true, picked: rows[0].innerText.slice(0, 40)}; }
  return {ok: false, error: 'no account rows'};
})()
"""


def settle_url(cdp, seconds=25):
    deadline = time.monotonic() + seconds
    last = ""
    while time.monotonic() < deadline:
        try:
            u = cdp.evaluate("location.href")
            if u and u != last:
                last = u
            time.sleep(1.5)
        except Exception:
            time.sleep(1.5)
    return last


results = []
for name, url in SEATS.items():
    tab = next((t for t in targets(PORT) if t.get("type") == "page"
                and urllib.parse.urlparse(url).hostname.replace("www.", "")
                in (t.get("url") or "")), None)
    if not tab:
        tab = next((t for t in targets(PORT) if t.get("type") == "page"
                    and url.split("//")[1].split("/")[0].split(".")[0]
                    in (t.get("url") or "")), None)
    if not tab:
        results.append((name, "no tab"))
        print(f"  no-tab   {name}")
        continue
    print(f"== {name}  from {tab['url'][:70]}")
    cdp = CDP(tab["webSocketDebuggerUrl"])
    try:
        cdp.call("Page.bringToFront")
    except Exception:
        pass
    # Frozen background tabs never answer Runtime.evaluate -- wake them with a reload
    # (the login wall persists; a reload re-instantiates the page fresh).
    try:
        cdp.call("Page.reload", {"ignoreCache": False})
    except Exception:
        pass
    time.sleep(10)
    time.sleep(1)
    try:
        login = cdp.evaluate(JS_CLICK_LOGIN)
        print("   login click:", json.dumps(login)[:120])
    except Exception as e:
        login = {"ok": False, "error": type(e).__name__}
        print("   login click err:", type(e).__name__)
    time.sleep(6)
    if not login.get("ok"):
        # evidence: what does this page actually show?
        slug = name.split()[0].lower().replace("(", "").replace(")", "")
        try:
            import base64
            d = cdp.call("Page.captureScreenshot", {"format": "png"}, timeout=15)
            open(fr"C:\Users\Admin\AppData\Local\Temp\kilo\sso_{slug}.png", "wb").write(
                base64.b64decode(d["data"]))
        except Exception as e:
            print("   shot err:", type(e).__name__)
        try:
            txt = cdp.evaluate("(() => (document.body ? document.body.innerText : '').slice(0, 400))()")
            print("   text head:", str(txt)[:300].replace("\n", " | "))
        except Exception as e:
            print("   text err:", type(e).__name__)
    try:
        found = cdp.evaluate(JS_FIND_GOOGLE)
    except Exception as e:
        found = {"ok": False, "error": f"{type(e).__name__}"}
    print("   google affordance:", json.dumps(found)[:120])
    if not found.get("ok"):
        results.append((name, f"no-google-affordance: {found.get('error','?')}"))
        continue
    time.sleep(12)
    try:
        loc = cdp.evaluate("location.href")
    except Exception:
        loc = ""
    print("   after click:", str(loc)[:90])
    if "accounts.google.com" in str(loc):
        try:
            pick = cdp.evaluate(JS_ACCOUNT_PICKER)
            print("   picker:", json.dumps(pick)[:120])
        except Exception as e:
            print("   picker err:", type(e).__name__)
        time.sleep(15)
    final = settle_url(cdp, 20)
    print("   settled:", str(final)[:90])
    results.append((name, f"final: {str(final)[:80]}"))

print("\nSUMMARY")
for n, r in results:
    print(f"  {n:<18} {r}")
