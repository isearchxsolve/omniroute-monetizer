"""tab_recon.py -- read-only census of every AI-video tab in the automation Chrome profile.

WHY: the generic "does the page say Sign In" heuristic is worthless on SPAs -- every one came back
MIXED. What actually decides whether a site is wireable is three facts, and all three can be read
out of a page that is already loaded, without clicking anything and without spending a credit:

  1. WHICH API the page talks to.  performance.getEntriesByType('resource') is the browser's own
     record of every request the page has already made. Filtering it to same-origin XHR/fetch gives
     the site's real API surface for free -- no devtools capture, no guessing at URL shapes.
  2. WHETHER this browser is authenticated to it. A session cookie name, or a bearer-shaped value in
     localStorage, is the difference between "a route we own" and "a signup form".
  3. WHAT it costs. The credit balance rendered on the page is the capacity estimate.

Nothing here types, clicks, submits or navigates. Cookie NAMES only, never values. Anything that
looks like a token is reported by shape and length, never printed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page, list_targets  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "tab_recon.json"

# Tabs already fully understood, or not a provider at all.
SKIP = ("labs.google", "localhost:", "google.com/search", "veoaifree.com", "chrome://", "about:")

SECRET_RE = re.compile(r"(ya29\.[\w\-.]+|AIza[\w\-]{10,}|1//[\w\-]{10,}|eyJ[\w\-]{20,})")

JS = r"""
(() => {
  const out = {url: location.href, host: location.host};
  const T = document.body ? document.body.innerText : "";

  // ---- 1. the site's own API surface, from the browser's own resource timeline ----------------
  let res = [];
  try { res = performance.getEntriesByType('resource') || []; } catch (e) {}
  const api = {};
  for (const r of res) {
    if (r.initiatorType !== 'xmlhttprequest' && r.initiatorType !== 'fetch') continue;
    let u; try { u = new URL(r.name); } catch (e) { continue; }
    // Third-party analytics/ads are noise; keep the site's own hosts.
    const base = u.host.split('.').slice(-2).join('.');
    const self = location.host.split('.').slice(-2).join('.');
    if (base !== self) continue;
    if (/\.(js|css|png|jpe?g|svg|woff2?|webp|gif|mp4)$/i.test(u.pathname)) continue;
    const key = u.host + u.pathname.replace(/\/[0-9a-f]{8,}\b/gi, '/{id}')
                                   .replace(/\/\d{3,}\b/g, '/{n}');
    api[key] = (api[key] || 0) + 1;
  }
  out.api = Object.entries(api).sort((a, b) => b[1] - a[1]).slice(0, 26)
                  .map(([k, n]) => n + "x " + k);

  // ---- 2. is this browser authenticated to it -------------------------------------------------
  // document.cookie only sees non-HttpOnly cookies; Network.getCookies (python side) sees the rest.
  out.jsCookieNames = (document.cookie || "").split(';')
      .map(s => s.split('=')[0].trim()).filter(Boolean).slice(0, 40);
  const auth = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      const v = localStorage.getItem(k) || "";
      if (/token|auth|session|jwt|bearer|credential|sid|uid|account|user/i.test(k)) {
        auth.push({key: k.slice(0, 60), len: v.length,
                   jwt: /^ey[JI]/.test(v) || /"ey[JI]/.test(v)});
      }
    }
  } catch (e) { out.lsError = String(e).slice(0, 60); }
  out.authKeys = auth.slice(0, 18);

  // an email or @handle rendered on the page is the strongest "logged in" signal there is
  const em = T.match(/[\w.+-]+@[\w-]+\.[\w.]{2,}/);
  out.identityShape = em ? (em[0].split('@')[0].slice(0, 2) + "***@" + em[0].split('@')[1]) : null;

  // ---- 3. what it costs ----------------------------------------------------------------------
  out.credits = (T.match(/([0-9][0-9,\.]*)\s*(credits?|coins?|points?|tokens?|generations?)/i)
                 || [null])[0];
  out.limitText = (T.match(/[^\n]{0,70}(daily limit|per day|free plan|watermark|rate limit)[^\n]{0,70}/i)
                 || [null])[0];
  // model names on the page tell us what we would actually be routing to
  out.models = [...new Set((T.match(/\b(veo\s?3(\.\d)?|sora|kling\s?\d(\.\d)?|seedance(\s?\d(\.\d)?)?|wan\s?\d(\.\d)?|hailuo|minimax|luma|runway|pika|hunyuan|ltx|flux)\b/gi) || [])
                 .map(s => s.toLowerCase()))].slice(0, 12);
  out.chars = T.length;
  return JSON.stringify(out);
})()
"""


def scrub(o):
    return json.loads(SECRET_RE.sub("[REDACTED]", json.dumps(o)))


def main() -> int:
    pages = [t for t in list_targets(9222) if t.get("type") == "page"]
    rows = []
    for t in pages:
        u = t.get("url") or ""
        if not u.startswith("http") or any(s in u for s in SKIP):
            continue
        try:
            with Page(u[:60], port=9222) as pg:
                d = json.loads(pg.evaluate(JS, timeout=40))
                # HttpOnly cookies are the ones that usually carry the session; names only.
                try:
                    ck = pg.send("Network.getCookies", {"urls": [u]}, timeout=20)
                    d["cookieNames"] = sorted({c["name"] for c in ck.get("cookies", [])})[:40]
                    d["httpOnly"] = sorted({c["name"] for c in ck.get("cookies", [])
                                            if c.get("httpOnly")})[:40]
                except BaseException as e:
                    d["cookieNames"] = f"({type(e).__name__})"
            rows.append(scrub(d))
        except BaseException as e:                       # SystemExit from pick_page included
            rows.append({"url": u, "host": u.split("/")[2],
                         "error": f"{type(e).__name__}: {str(e)[:80]}"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    print(f"{'HOST':<22} {'AUTH':<5} {'CREDITS':<14} {'API CALLS':<9} MODELS SEEN")
    print("-" * 100)
    for d in rows:
        if d.get("error"):
            print(f"{d['host'][:22]:<22} {'ERR':<5} {d['error']}")
            continue
        authed = bool(d.get("httpOnly")) or bool(d.get("authKeys")) or bool(d.get("identityShape"))
        print(f"{d['host'][:22]:<22} {('yes' if authed else 'no'):<5} "
              f"{str(d.get('credits'))[:14]:<14} {len(d.get('api') or []):<9} "
              f"{','.join(d.get('models') or [])[:44]}")
    print(f"\nfull detail -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
