"""cdp_sso.py — run Google SSO inside the CDP automation Chrome (port 9222).

Drives: provider login page -> Continue-with-Google click (fuzzy, shadow-piercing)
-> account chooser (click the account whose identifier matches) -> consent
(#submit_approve_access / Continue/Allow) -> verify identity markers on the
provider page. Prints VERDICT: SSO_DONE | SSO_FAILED:<reason>.
"""
import argparse
import json
import sys
import time
import urllib.request

# Localhost CDP must NEVER route through a proxy. An env HTTP_PROXY/HTTPS_PROXY in the
# launching shell poisons every 127.0.0.1 call with WinError 10061 (2026-10-13: two full
# passes died on a healthy Chrome because of exactly this). Proxy-free opener, always.
CDP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Tee:
    """Mirror stdout/stderr into the run log so swallowed prints survive."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass

import websocket

ACCOUNT = "isearch.xsolve@gmail.com"

# EVENT-DRIVEN BUTTON OBSERVER (2026-10-13, Baba law: no fixed window).
# Injected once per target page. A MutationObserver watches for a
# Continue-with-Google node materializing (late modal render, SPA nav,
# delayed GSI iframe button) and fires window.__ssoSeen the moment it
# appears. The python loop then polls this FLAG (cheap, local read) with
# a generous outer deadline instead of blind sleep-click cycles.
# Covers: modal-after-door, delayed render, two-step doors.
BUTTON_WATCH_JS = """
(() => {
  if (window.__ssoWatchArmed) return 'already_armed';
  window.__ssoSeen = null;
  function scan() {
    const els = document.querySelectorAll('a,button,[role="button"],div,span');
    for (const e of els) {
      const t = ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')).toLowerCase().trim();
      if (!t || t.length > 60) continue;
      if (/with google|^google$|^g$/.test(t) && /continue|sign|log|google/.test(t)) {
        const r = e.getBoundingClientRect();
        if (r.width > 15 && r.height > 15) {
          window.__ssoSeen = t.slice(0, 50);
          return window.__ssoSeen;
        }
      }
    }
    return null;
  }
  window.__ssoCheck = function() { return window.__ssoSeen || scan(); };
  const mo = new MutationObserver(() => { scan(); });
  mo.observe(document.documentElement || document.body, { childList: true, subtree: true, attributes: true });
  window.__ssoWatchArmed = true;
  return scan() || 'armed';
})()
"""

BUTTON_POLL_JS = """(window.__ssoCheck ? window.__ssoCheck() : null)"""

# FEDCM DIALOG PROBE (2026-10-13). Google's new One-Tap / auto-sign-in
# renders as a BROWSER-LEVEL FedCM dialog, not a tab. find_google_tab can
# never see it. This probe asks the page for the FedCM / GSI state so the
# loop can confirm the dialog path instead of waiting for a tab forever.
# Covers: clicked-but-no-tab (replit class), One-Tap passive flows.
FEDCM_PROBE_JS = """
(() => {
  const out = { fedcm: false, gsi: false, onetap: false };
  try {
    if (document.querySelector('div[id^="credential_picker"], iframe[src*="accounts.google.com/gsi"]')) out.gsi = true;
    if (window.google && window.google.accounts && window.google.accounts.id) out.onetap = true;
    if (navigator.credentials && navigator.credentials.get) out.fedcm = 'api_present';
  } catch (e) { out.err = String(e).slice(0, 60); }
  return JSON.stringify(out);
})()
"""

SSO_CLICK_JS = """
(() => {
  function* deep(root) {
    for (const el of root.querySelectorAll('a,button,[role="button"],div,span'))
      { yield el; if (el.shadowRoot) yield* deep(el.shadowRoot); }
  }
  function txt(e) {
    return ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '') +
            ' ' + (e.title || '')).toLowerCase().trim();
  }
  const hrefs = [];
  for (const e of document.querySelectorAll('a[href]')) {
    const h = e.href || '';
    if (/accounts\\.google\\.com\\/(o\\/oauth2|signin|gsi)|google\\.com\\/o\\/oauth2|auth\\/google|google.*oauth|oauth.*google/i.test(h)) {
      const r = e.getBoundingClientRect();
      if (r.width > 5) hrefs.push(h);
    }
  }
  if (hrefs.length) { window.location.href = hrefs[0]; return { ok: true, via: 'href' }; }
  const attrSels = ['[data-provider*="google" i]','[aria-label*="google" i]',
    '[class*="google" i][class*="btn" i]','[id*="google" i][id*="btn" i]'];
  for (const sel of attrSels) {
    for (const e of document.querySelectorAll(sel)) {
      const r = e.getBoundingClientRect();
      if (r.width > 15 && r.height > 15) { e.click(); return { ok: true, via: 'attr', sel: sel }; }
    }
  }
  const reExact = /^(continue|sign in|log in|sign up|login|signup) with google$|^google$|^g$/;
  let best = null, bestScore = 0;
  for (const e of deep(document)) {
    const t = txt(e);
    if (!t || t.length > 60) continue;
    let s = 0;
    if (reExact.test(t)) s = 100;
    else if (/with google/.test(t)) s = 80;
    else if (/^google$/.test(t)) s = 70;
    else if (/google/.test(t) && /sign|continue|login/.test(t)) s = 60;
    if (s > bestScore) {
      const r = e.getBoundingClientRect();
      if (r.width > 15 && r.height > 15) { best = e; bestScore = s; }
    }
  }
  if (best) { best.scrollIntoView({ block: 'center' }); best.click();
    return { ok: true, via: 'text', t: txt(best).slice(0, 50) }; }
  return { ok: false };
})()
"""

# DOOR STEP (census 2026-10-12): Perplexity et al hide Google behind a
# "Sign In" door button - click it first, the Google button then appears
# in the modal/auth surface.
DOOR_JS = """
(() => {
  for (const e of document.querySelectorAll('button, a, [role="button"]')) {
    const t = (e.innerText || '').toLowerCase().trim();
    if (/^(sign in|log in|login|sign up|get started)$/.test(t)) {
      const r = e.getBoundingClientRect();
      if (r.width > 20 && r.height > 10) { e.click(); return 'door_clicked:' + t; }
    }
  }
  return 'none';
})()
"""

CHOOSER_JS = """
(() => {
  function* deep(root) {
    for (const el of root.querySelectorAll('*'))
      { yield el; if (el.shadowRoot) yield* deep(el.shadowRoot); }
  }
  for (const el of deep(document)) {
    const id = el.getAttribute ? (el.getAttribute('data-identifier') || el.getAttribute('data-email') || '') : '';
    const t = (el.innerText || '').toLowerCase();
    if ((id && id.toLowerCase().includes('%ACCOUNT%')) ||
        t.includes('%ACCOUNT%')) {
      const target = el.closest('[role="link"], li, button, div[tabindex]') || el;
      target.click();
      return 'clicked_account';
    }
  }
  return 'none';
})()
""".replace("%ACCOUNT%", ACCOUNT)

CONSENT_JS = """
(() => {
  const byId = document.querySelector('#submit_approve_access');
  if (byId) { byId.click(); return 'clicked_allow_id'; }
  for (const b of document.querySelectorAll('button, [role="button"], div[role="button"]')) {
    const t = (b.innerText || '').toLowerCase().trim();
    if (t === 'continue' || t === 'allow' || t === 'confirm' || t === 'next') {
      b.click(); return 'clicked_confirm';
    }
  }
  return 'none';
})()
"""

VERIFY_JS = """
(() => {
  const b = (document.body.innerText || '');
  return JSON.stringify({ url: location.href.slice(0, 120),
    identity: /isearchxso|isearch\\.xsolve|xsolve/i.test(b),
    signIn: /sign in with google|continue with google/i.test(b.slice(0, 5000)) });
})()
"""


class CDP:
    def __init__(self, port):
        self.port = port

    def tabs(self):
        return json.load(CDP_OPENER.open(
            "http://127.0.0.1:%d/json/list" % self.port, timeout=10))

    def new_tab(self, url):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/json/new?%s" % (self.port, url), method="PUT")
        return json.load(CDP_OPENER.open(req, timeout=15))

    def call(self, target_ws, mid, method, params, timeout=20):
        ws = None
        for attempt in range(3):
            try:
                ws = websocket.create_connection(target_ws, timeout=timeout,
                                                 suppress_origin=True)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.2)
        try:
            ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            end = time.time() + timeout
            while time.time() < end:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid:
                    return msg
            return {}
        finally:
            ws.close()

    def js(self, tab, expr, mid=1):
        res = self.call(tab["webSocketDebuggerUrl"], mid, "Runtime.evaluate",
                        {"expression": expr, "returnByValue": True})
        try:
            return res["result"]["result"].get("value")
        except Exception:
            return None


def find_google_tab(cdp, pre_ids=None):
    for t in cdp.tabs():
        u = t.get("url") or ""
        if t.get("type") == "page" and "accounts.google.com" in u:
            if pre_ids is not None and t.get("id") in pre_ids:
                continue  # stale leftover from a previous run - NEVER babysit it
            return t
    return None


def close_tab(port, tid):
    if not tid:
        return
    try:
        CDP_OPENER.open("http://127.0.0.1:%d/json/close/%s" % (port, tid), timeout=6)
        print("  zombie tab closed:", str(tid)[:8])
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--url", required=True)
    ap.add_argument("--match", required=True, help="provider domain fragment")
    a = ap.parse_args()
    _lf = open(r"D:\anonym\war-log\ssodbg-run.log", "a", encoding="utf-8")
    _lf.write("=== RUN %s %s --match %s ===\n"
              % (time.strftime("%Y-%m-%d %H:%M:%S"), a.url, a.match))
    _lf.flush()
    sys.stdout = _Tee(sys.stdout, _lf)
    sys.stderr = _Tee(sys.stderr, _lf)
    cdp = CDP(a.port)

    # Snapshot PRE ids BEFORE opening our own tab - the old order captured AFTER
    # new_tab(), making every run's door tab look pre-existing, so cleanup closed
    # nothing and pages accumulated until Chrome drowned (2026-10-13: websocket
    # timeouts across the pass at 25 leaked pages / 85 targets).
    pre_ids = set()
    for t0 in cdp.tabs():
        if t0.get("type") == "page":
            pre_ids.add(t0.get("id"))
    for t0 in cdp.tabs():
        u0 = t0.get("url") or ""
        if t0.get("type") == "page" and "accounts.google.com" in u0:
            close_tab(a.port, t0.get("id"))
            print("  stale google leftover swept")
    tab = cdp.new_tab(a.url)
    print("tab opened:", tab.get("url", "")[:80])
    time.sleep(6)

    tab_id = tab.get("id")
    chooser_clicked = False
    sso_clicked = False
    sso_click_t = 0.0
    observer_armed = False
    fedcm_logged = False
    deadline = time.time() + 300
    verdict = "SSO_TIMEOUT"
    while time.time() < deadline:
        tabs = [t for t in cdp.tabs()
                if t.get("type") == "page" and t.get("id") == tab_id]
        tab = tabs[0] if tabs else tab

        gt = find_google_tab(cdp, pre_ids)
        if gt is not None:
            u = gt.get("url") or ""
            if "challenge/pwd" in u:
                verdict = "SSO_FAILED:password_challenge_demanded"
                break
            try:
                res = cdp.js(gt, CHOOSER_JS)
            except Exception as e:
                print("  chooser-ws-error:", repr(e)[:70])
                close_tab(a.port, gt.get("id"))
                time.sleep(2)
                continue
            if res == "clicked_account" and not chooser_clicked:
                chooser_clicked = True
                print("  chooser: account clicked (one-shot, now consent-wait)")
            elif res == "clicked_account" and chooser_clicked:
                pass
            time.sleep(2)
            try:
                res2 = cdp.js(gt, CONSENT_JS)
            except Exception as e:
                print("  consent-ws-error:", repr(e)[:70])
                close_tab(a.port, gt.get("id"))
                time.sleep(2)
                continue
            if res2 in ("clicked_allow_id", "clicked_confirm"):
                print("  consent:", res2)
            time.sleep(2)
            continue

        cur = (tab.get("url") or "")
        if a.match in cur:
            # VERIFY FIRST - an already-authenticated session must pass instantly
            # (felo was logged in but the old flow only verified AFTER a door click,
            # so a live session burned 150s and reported SSO_TIMEOUT).
            try:
                v = cdp.js(tab, VERIFY_JS)
            except Exception as e:
                print("  verify-ws-error:", repr(e)[:70])
                time.sleep(3)
                continue
            print("  verify-raw:", str(v)[:160])
            vj = {}
            if isinstance(v, str):
                try:
                    vj = json.loads(v)
                except Exception:
                    vj = {}
            if vj.get("identity"):
                verdict = "SSO_DONE:" + str(vj.get("url", ""))
                break
            if not observer_armed:
                try:
                    arm = cdp.js(tab, BUTTON_WATCH_JS)
                    print("  observer:", str(arm)[:60])
                except Exception as e:
                    print("  observer-ws-error:", repr(e)[:70])
                observer_armed = True
            try:
                seen = cdp.js(tab, BUTTON_POLL_JS)
            except Exception as e:
                print("  observer-poll-ws-error:", repr(e)[:70])
                time.sleep(3)
                continue
            if isinstance(seen, str) and seen and seen not in ("armed", "already_armed"):
                print("  observer: button materialized:", seen[:50])
            if not sso_clicked:
                try:
                    r = cdp.js(tab, SSO_CLICK_JS)
                except Exception as e:
                    print("  click-ws-error:", repr(e)[:70])
                    time.sleep(3)
                    continue
                if isinstance(r, dict) and r.get("ok"):
                    sso_clicked = True
                    sso_click_t = time.time()
                    print("  SSO clicked:", r)
                    time.sleep(4)
                else:
                    try:
                        door = cdp.js(tab, DOOR_JS)
                    except Exception as e:
                        print("  door-ws-error:", repr(e)[:70])
                        time.sleep(3)
                        continue
                    if isinstance(door, str) and door.startswith("door_clicked"):
                        print("  door:", door)
                    time.sleep(3)
                continue
            if sso_clicked and (time.time() - sso_click_t > 12) and not fedcm_logged:
                try:
                    fed = cdp.js(tab, FEDCM_PROBE_JS)
                    print("  fedcm-probe:", str(fed)[:160])
                except Exception as e:
                    print("  fedcm-ws-error:", repr(e)[:70])
                fedcm_logged = True
            if sso_clicked:
                time.sleep(3)
                continue

    print("VERDICT:", verdict)
    closed = 0
    for t0 in cdp.tabs():
        if t0.get("type") == "page" and t0.get("id") not in pre_ids:
            try:
                CDP_OPENER.open(
                    "http://127.0.0.1:%d/json/close/%s" % (a.port, t0["id"]),
                    timeout=6)
                closed += 1
            except Exception:
                pass
    print("tab cleanup: %d new tab(s) closed (no leak)" % closed)
    return 0 if verdict.startswith("SSO_DONE") else 1


if __name__ == "__main__":
    raise SystemExit(main())

