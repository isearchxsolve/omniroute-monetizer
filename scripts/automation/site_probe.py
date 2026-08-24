"""site_probe.py -- discover a video site's API contract from a tab that is already logged in.

WHY THIS SHAPE: the expensive part of wiring a new provider is finding out which endpoint submits a
job, which one reports progress, and what the payload looks like. There are three ways to learn that
and only one of them is cheap:

  * click Generate with devtools armed -- costs a credit every time you get the capture wrong
  * guess REST shapes -- silently wrong until it charges you
  * READ THE SITE'S OWN JAVASCRIPT -- free, exact, and it lists endpoints you have not triggered yet

This does the third. It fetches the page's own script bundles from inside the page (so same-origin
rules and any auth cookie apply automatically), extracts every API path mentioned, and separately
calls the read-only ones to see what this browser is actually entitled to.

It NEVER submits a generation. Nothing here spends a credit. It reads localStorage to learn WHICH key
holds the bearer, and uses that key inside the page, but the token value never crosses into Python:
only its length and JWT-ness are reported. Cookie names only, never values.

    python site_probe.py rtst.ai --api api.rtst.ai
    python site_probe.py rtst.ai --api api.rtst.ai --get /videomodel --get /model
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402

OUT_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "probes"

SECRET_RE = re.compile(r"(ya29\.[\w\-.]+|AIza[\w\-]{10,}|1//[\w\-]{10,}|eyJ[\w\-]{18,}"
                       r"|sk-[A-Za-z0-9]{20,}|Bearer\s+[\w\-.]{20,})")

# Path fragments worth flagging: these are the verbs a video route is made of.
INTERESTING = re.compile(
    r"(generat|creat|submit|render|video|task|job|queue|poll|status|result|progress|"
    r"credit|balance|quota|billing|point|model|upload|asset|media|history|txt2|t2v|i2v)", re.I)

DISCOVER_JS = r"""
(async (apiHost, needles) => {
  const out = {scripts: 0, bytes: 0, paths: [], hosts: [], errors: [], snippets: [],
               origin: location.origin};

  // The browser already knows every script it loaded; no need to parse HTML.
  const srcs = [...new Set([...document.querySelectorAll('script[src]')].map(s => s.src))];
  const perf = (performance.getEntriesByType('resource') || [])
      .filter(r => r.initiatorType === 'script' || /\.js(\?|$)/.test(r.name)).map(r => r.name);
  // A same-registrable-domain filter LOOKS right and is wrong, for the same reason it was wrong in
  // tab_recon: akool.com and teamily.ai serve their entire app bundle from a CDN host, so that
  // filter discarded all 166 scripts and the probe reported "0 paths" as if the site had no API.
  // Drop known analytics/ad hosts instead and read everything else.
  const NOISE = /(googletagmanager|google-analytics|googleadservices|doubleclick|gstatic\.com|clarity\.ms|mixpanel|segment\.(io|com)|sentry|hotjar|facebook|fbcdn|amplitude|intercom|crisp\.chat|cloudflareinsights|newrelic|datadoghq|bugsnag|recaptcha|hcaptcha|tiktok|klaviyo|stripe\.com)/i;
  const all = [...new Set([...srcs, ...perf])].filter(u => /^https?:/.test(u) && !NOISE.test(u))
                                              .slice(0, 60);
  out.scriptsSeen = all.length;

  const paths = new Set(), hosts = new Set(), calls = new Set();
  const H = apiHost.replace(/\./g, '\\.');
  const HOST_RE = new RegExp('https?://([a-z0-9.\\-]*' + H + ')', 'gi');
  const ABS_RE = new RegExp('https?://[a-z0-9.\\-]*' + H + '(/[A-Za-z0-9_\\-/{}$.:]*)', 'gi');

  // Bundlers keep the host in one constant and the path in another, so an absolute-URL regex finds
  // nothing. Two broader nets: any quoted absolute path, and any http-client call's first argument.
  // Single-segment paths like "/videomodel" are the norm, so no /api/ prefix may be required.
  const PATH_RE = /["'`](\/[A-Za-z][A-Za-z0-9_\-\/{}$.:]{1,58})["'`]/g;
  const CALL_RE = /\.(get|post|put|patch|delete|request)\(\s*["'`]([^"'`\s]{2,70})["'`]/gi;
  // Static assets and framework routes are not API endpoints.
  const JUNK = /\.(js|css|png|jpe?g|svg|gif|webp|woff2?|ttf|ico|map|json|mp4|webm)$|^\/(static|_next|assets|images|img|fonts|css|js|public|locales|favicon)\b|^\/\//i;

  // Bundles can be enormous and a CDN can simply not answer. Without a budget one slow script hangs
  // the whole probe and the site gets no verdict at all, which is worse than a partial read.
  const DEADLINE = 100000, PER_SCRIPT = 12000, t0 = performance.now();
  for (const u of all) {
    if (performance.now() - t0 > DEADLINE) {
      out.errors.push('time budget spent after ' + out.scripts + ' script(s)');
      break;
    }
    try {
      // 'same-origin', not 'include': a bundle on a CDN answers with wildcard CORS, and a wildcard
      // response is INVALID for a credentialed request -- the fetch dies before the network. Cookies
      // are irrelevant to a static bundle anyway, and same-origin ones are still sent.
      const ac = new AbortController();
      const tid = setTimeout(() => ac.abort(), PER_SCRIPT);
      let r;
      try { r = await fetch(u, {credentials: 'same-origin', signal: ac.signal}); }
      finally { clearTimeout(tid); }
      if (!r.ok) { out.errors.push(r.status + ' ' + u.slice(-40)); continue; }
      const txt = await r.text();
      out.scripts++; out.bytes += txt.length;
      let m;
      while ((m = ABS_RE.exec(txt))) if (!JUNK.test(m[1])) paths.add(m[1]);
      while ((m = HOST_RE.exec(txt))) hosts.add(m[1]);
      while ((m = PATH_RE.exec(txt))) if (!JUNK.test(m[1])) paths.add(m[1]);
      while ((m = CALL_RE.exec(txt))) if (!JUNK.test(m[2])) calls.add(m[1].toUpperCase() + ' ' + m[2]);

      // Payload shape: the code that BUILDS a request body sits next to the path literal. Grabbing
      // the surrounding characters is how you learn the field names without submitting anything.
      for (const needle of (needles || [])) {
        let i = -1;
        while ((i = txt.indexOf(needle, i + 1)) !== -1 && out.snippets.length < 24) {
          out.snippets.push({needle: needle,
                             text: txt.slice(Math.max(0, i - 260), i + 460)});
        }
      }
    } catch (e) { out.errors.push(String(e).slice(0, 50) + ' ' + u.slice(-30)); }
  }
  out.paths = [...paths].sort();
  out.hosts = [...hosts].sort();
  out.calls = [...calls].sort().slice(0, 120);   // method + path: the actual contract

  // Which localStorage key holds the bearer -- reported by SHAPE only. A JWT beats a chat-widget
  // session id, so rank by jwt-ness then length instead of taking whatever comes first.
  out.authKeys = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i), v = localStorage.getItem(k) || '';
      if (/token|auth|jwt|session|bearer|credential/i.test(k) && v.length > 40)
        out.authKeys.push({key: k, len: v.length, jwt: /^["']?ey[JI]/.test(v)});
    }
  } catch (e) {}
  out.authKeys.sort((a, b) => (b.jwt - a.jwt) || (b.len - a.len));
  return JSON.stringify(out);
})(%s, %s)
"""

# A read-only GET, made from inside the page so cookies and the bearer apply. Response is truncated:
# we want the SHAPE of the answer, not a data dump.
GET_JS = r"""
(async (base, path, authKey) => {
  const h = {'Accept': 'application/json'};
  try {
    const t = authKey ? localStorage.getItem(authKey) : null;
    if (t) h['Authorization'] = t.startsWith('Bearer') ? t : 'Bearer ' + t.replace(/^"|"$/g, '');
  } catch (e) {}
  try {
    const r = await fetch(base + path, {credentials: 'include', headers: h});
    const txt = await r.text();
    // Keep the whole body for the saved artifact -- a truncated model catalogue is useless for
    // pricing decisions. The console print truncates separately.
    return JSON.stringify({status: r.status, len: txt.length, body: txt.slice(0, 200000)});
  } catch (e) { return JSON.stringify({status: 0, error: String(e).slice(0, 120)}); }
})(%s, %s, %s)
"""


def scrub(s: str) -> str:
    return SECRET_RE.sub("[REDACTED]", s)


def norm_path(p: str) -> str:
    """Git Bash rewrites a bare '/videomodel' argument into 'C:/Program Files/Git/videomodel'
    before python ever sees it. Undo that, and accept 'videomodel' with no slash either."""
    m = re.match(r"^[A-Za-z]:[/\\].*?[/\\]([^/\\]+)$", p)
    if m:
        p = m.group(1)
    return p if p.startswith("/") else "/" + p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("match", help="substring identifying the already-open tab")
    ap.add_argument("--api", required=True, help="the site's API host, e.g. api.rtst.ai")
    ap.add_argument("--get", action="append", default=[],
                    help="read-only path to call, repeatable (e.g. --get /videomodel)")
    ap.add_argument("--grep", action="append", default=[],
                    help="show bundle source around this literal, repeatable -- how you learn a "
                         "request body's field names without submitting one")
    ap.add_argument("--port", type=int, default=9222)
    a = ap.parse_args()

    base = f"https://{a.api}"
    gets = [norm_path(p) for p in a.get]
    with Page(a.match, port=a.port) as pg:
        d = json.loads(pg.evaluate(DISCOVER_JS % (json.dumps(a.api), json.dumps(a.grep)),
                                   timeout=240))
        authkey = (d.get("authKeys") or [{}])[0].get("key")
        results = {}
        for path in gets:
            raw = pg.evaluate(GET_JS % (json.dumps(base), json.dumps(path),
                                        json.dumps(authkey)), timeout=90)
            results[path] = json.loads(raw)

    print(f"read {d['scripts']} script(s), {d['bytes']:,} bytes")
    print(f"auth key: {authkey or '(none found)'}  "
          f"({(d.get('authKeys') or [{}])[0].get('len')} chars, "
          f"jwt={(d.get('authKeys') or [{}])[0].get('jwt')})  -- value never read into python")
    if len(d.get("authKeys") or []) > 1:
        print(f"  other candidates: {', '.join(k['key'][:34] for k in d['authKeys'][1:6])}")
    if d.get("hosts"):
        print(f"api hosts in bundle: {', '.join(d['hosts'])}")

    if d.get("calls"):
        hotc = [c for c in d["calls"] if INTERESTING.search(c)]
        print(f"\nhttp-client calls found in bundle ({len(hotc)}/{len(d['calls'])} interesting):")
        for c in hotc[:60]:
            print("   ", c[:96])

    hot = [p for p in d["paths"] if INTERESTING.search(p)]
    print(f"\n{len(d['paths'])} path(s) found, {len(hot)} interesting:")
    for p in hot[:70]:
        print("   ", p[:96])
    other = [p for p in d["paths"] if p not in hot]
    if other:
        print(f"  (+{len(other)} uninteresting: {', '.join(o[:22] for o in other[:8])}...)")
    if d.get("errors"):
        print(f"\n{len(d['errors'])} fetch error(s): {'; '.join(d['errors'][:4])}")

    for s in d.get("snippets") or []:
        print("\n" + "=" * 78)
        print(f"-- source around {s['needle']!r}")
        print(scrub(s["text"]))

    for path, r in results.items():
        print("\n" + "-" * 78)
        print(f"GET {path}  ->  HTTP {r.get('status')}  {r.get('len')} bytes")
        print(scrub(str(r.get("body") or r.get("error") or ""))[:1300])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{a.api.replace('.', '_')}.json"
    dest.write_text(scrub(json.dumps({"discovery": d, "gets": results}, indent=1)),
                    encoding="utf-8")
    print(f"\nsaved -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
