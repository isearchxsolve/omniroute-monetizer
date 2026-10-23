"""veoaifree_client.py -- drive veoaifree.com's Veo/Seedance generator from its own logged-in tab.

WHY THIS EXISTS (measured 2026-08-23):
OmniRoute ships a built-in `veoaifree-web` provider (models `veo`, `seedance`) with
`authType: none`. It cannot ever work, and this is structural rather than a misconfiguration:

    MASTER_WORKLOG: veoaifree-web/veo -> ReadTimeout at 1502s, no HTTP status, twice.
    The host is alive (GET / -> 200 in 2.2s, 235k of HTML), so the site is not the problem.

Reading the site's own generator (wp-content/themes/really-simple-child/logic.js) explains it.
veoaifree is WordPress, and every generate call is an admin-ajax POST carrying a **per-session
WordPress nonce** plus the logged-in session cookie:

    POST https://veoaifree.com/wp-admin/admin-ajax.php     (form-encoded, cookies required)
      action=veo_video_generator
      nonce=<ajax_object.nonce>          10 chars, minted per session, tied to the cookie
      actionType=full-video-generate
      prompt=<text>
      totalVariations=1|2                <input type=number value=1 min=1 max=2>
      aspectRatio=VIDEO_ASPECT_RATIO_LANDSCAPE | VIDEO_ASPECT_RATIO_PORTRAIT
      video_quality=720p|1080p
    -> BARE TEXT: an opaque `sceneData` handle

    POST .../admin-ajax.php                                (the site waits 85s, then every 20s)
      action=veo_video_generator  nonce=..  actionType=final-video-results  sceneData=<handle>
    -> ""  means STILL PENDING          <- the whole reason a naive poller hangs forever
    -> otherwise a video URL; the site rewrites "videos/" to "video/" before playing it

MEASURED, and it dictates every timeout in this file: **one poll blocks ~100 seconds** before it
answers. Twice in a row, on a scene handle that does not exist: 101.4s -> pending, 102.6s -> pending.
That is the site's normal behaviour, not a stall, so any CDP timeout below ~150s will look like a
hang that is really just an unfinished request. It also explains OmniRoute's 1502s ReadTimeout:
a poll loop where every iteration costs 100s cannot reach a terminal state inside a client budget.

A provider with `authType: none` sends no cookie, so it can never hold a valid nonce. And the
built-in handler does not even try: de-minified from open-sse_1y8z7i0._.js, `veoaifree-web` routes
to a handler that treats the site as a CHAT executor --

    ex.execute({body: {...body, messages: [{role:'system', content:'aspect_ratio: 16:9'},
                                           {role:'user',   content: prompt}]},
                credentials: credentials || {connectionId:'noauth'}, signal: null})
    // then requires data.length===1 && p.b64_json non-empty && p.format==='mp4' && !p.url

-- so it posts chat messages, expects an OpenAI-shaped MP4 artifact back, never calls
admin-ajax.php, and passes `signal: null` so the wait is unbounded. It also receives no
providerConfig, so unlike `comfyui` there is no baseUrl to point somewhere else. Nothing an
operator can configure fixes that. So we do what we did for Google Flow: keep the credential
where it already lives -- in a logged-in browser tab -- and drive the site's real protocol.

Every request is executed INSIDE the page via CDP, not replayed from Python. That is deliberate:
the session cookie and the nonce never leave the browser, so there is nothing here to leak.

    python veoaifree_client.py whoami                  # plan, totals, login state
    python veoaifree_client.py doctor                  # prove the chain without generating
    python veoaifree_client.py submit "<prompt>" [--aspect 16:9] [--quality 720p] [--variations 1]
    python veoaifree_client.py poll <sceneData>
    python veoaifree_client.py gen "<prompt>" [--out FILE]      # submit, wait, download

Generation on this site is FREE, so unlike the Flow path nothing here spends money. What it can
spend is a rate-limit slot: the site refuses a second concurrent job with "In Progress", and a
free account eventually answers "Limit"/"Rate Limit". Both are reported, never retried in a loop.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import pathlib

from cdp import Page, DEFAULT_PORT

MATCH = "veoaifree.com"
AJAX_ACTION = "veo_video_generator"
GEN_URL = "https://veoaifree.com/veo-video-generator/"

ASPECTS = {
    "16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "landscape": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "portrait": "VIDEO_ASPECT_RATIO_PORTRAIT",
}
QUALITIES = ("720p", "1080p")

# The site signals failure only by substring -- there is no status field anywhere in the protocol.
# Taken from logic.js, which tests: 'In Progress', 'Error', 'failed', 'retry', 'Limit', 'Rate Limit'.
BUSY_RE = re.compile(r"in\s*progress", re.I)
LIMIT_RE = re.compile(r"\b(rate\s*limit|limit\s*(reached|exceeded)?)\b", re.I)
ERROR_RE = re.compile(r"\b(error|failed|failure|retry|invalid|denied|unauthorized)\b", re.I)

# Anything token-shaped that must never reach a log. The nonce is a session credential.
SECRET_RE = re.compile(r"(ya29\.[\w\-.]+|AIza[\w\-]{10,}|1//[\w\-]{10,}|0cA[\w\-]{20,})")


def scrub(s: str) -> str:
    return SECRET_RE.sub("<redacted>", s or "")


class VeoFreeError(RuntimeError):
    """A reportable outcome from the site: busy, rate-limited, or an explicit error string."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


# One in-page POST to admin-ajax. The nonce is read from window.ajax_object inside the page and
# never crosses into Python; params are injected as JSON so no quoting can go wrong.
# A poll legitimately takes ~100s, so the in-page AbortController is generous -- but it exists so a
# genuinely wedged request is cancelled in the page instead of being abandoned there while Python
# walks away, which would leak a pending fetch per attempt.
POST_JS = """
(async () => {
  const p = %s;
  const ms = %d;
  const a = window.ajax_object;
  if (!a || !a.ajax_url) return JSON.stringify({fatal: 'ajax_object missing -- not a generator page'});
  if (!a.nonce) return JSON.stringify({fatal: 'ajax_object.nonce missing -- probably logged out'});
  const body = new URLSearchParams();
  body.set('action', %s);
  body.set('nonce', a.nonce);
  for (const k in p) body.set(k, String(p[k]));
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(a.ajax_url, {
      method: 'POST',
      credentials: 'include',
      signal: ctl.signal,
      headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'},
      body: body.toString(),
    });
    return JSON.stringify({status: r.status, text: (await r.text()).slice(0, 8000)});
  } catch (e) {
    const aborted = ctl.signal.aborted;
    return JSON.stringify({fatal: (aborted ? 'aborted after ' + ms + 'ms: ' : 'fetch threw: ')
                                  + String(e && e.message || e), aborted: aborted});
  } finally { clearTimeout(timer); }
})()
"""

WHOAMI_JS = """
(() => {
  const cls = document.body ? (document.body.className || '') : '';
  const t = (document.body ? document.body.innerText : '') || '';
  const grab = (label) => {
    const i = t.indexOf(label);
    if (i < 0) return null;
    return t.slice(i + label.length, i + label.length + 40).split('\\n')
             .map(s => s.trim()).filter(Boolean)[0] || null;
  };
  const a = window.ajax_object || {};
  return JSON.stringify({
    url: location.href,
    logged_in: /logged-in/.test(cls),
    has_nonce: !!a.nonce,
    nonce_len: a.nonce ? String(a.nonce).length : 0,
    ajax_url: a.ajax_url || null,
    plan: grab('CURRENT PLAN'),
    total_success: grab('TOTAL SUCCESS'),
    total_failed: grab('TOTAL FAILED'),
  });
})()
"""


class VeoFreeSession:
    """A handle on one logged-in veoaifree tab. Stateless apart from which tab/port to talk to."""

    def __init__(self, match: str = MATCH, port: int = DEFAULT_PORT):
        self.match = match
        self.port = port

    # ---- plumbing -------------------------------------------------------------------------
    def _post(self, params: dict, timeout: int = 240) -> str:
        """timeout must stay well above the measured ~100s poll latency, or a normal pending
        response reads as a hang. The in-page abort fires slightly earlier so the page cleans up
        its own fetch before the CDP call gives up on us."""
        js = POST_JS % (json.dumps(params), max(1, timeout - 20) * 1000, json.dumps(AJAX_ACTION))
        with Page(self.match, port=self.port) as pg:
            raw = pg.evaluate(js, timeout=timeout)
        if not raw:
            raise VeoFreeError("TRANSPORT", "the page returned nothing (tab closed or navigated?)")
        d = json.loads(raw)
        if d.get("fatal"):
            raise VeoFreeError("ABORTED" if d.get("aborted") else "SESSION", d["fatal"])
        if d.get("status") != 200:
            raise VeoFreeError("HTTP", f"admin-ajax answered {d.get('status')}")
        text = (d.get("text") or "").strip()
        # WordPress dies with a bare -1 / 0 when check_ajax_referer or the action lookup fails.
        if text in ("-1", "0"):
            raise VeoFreeError(
                "NONCE",
                f"admin-ajax returned {text!r} -- the nonce was rejected. Reload the generator tab "
                f"so WordPress mints a fresh one, and confirm the tab is still logged in.")
        return text

    def whoami(self, timeout: int = 60) -> dict:
        with Page(self.match, port=self.port) as pg:
            raw = pg.evaluate(WHOAMI_JS, timeout=timeout)
        return json.loads(raw or "{}")

    def reload(self, settle: float = 6.0) -> None:
        """Re-mint the nonce. A WordPress nonce is tied to the session and does age out."""
        with Page(self.match, port=self.port) as pg:
            pg.send("Page.reload", {"ignoreCache": False}, timeout=60)
        time.sleep(settle)

    # ---- protocol -------------------------------------------------------------------------
    @staticmethod
    def classify(text: str) -> tuple[str, str]:
        """Map a bare-text response onto a state. The site has no status field; this is all we get."""
        if text == "":
            return "pending", ""
        if BUSY_RE.search(text):
            return "busy", text[:300]
        if LIMIT_RE.search(text):
            return "limit", text[:300]
        # An error string is prose or HTML. A handle/URL is short and has no spaces or tags.
        if ERROR_RE.search(text) and (" " in text or "<" in text):
            return "error", text[:300]
        return "ok", text

    def submit(self, prompt: str, aspect: str = "16:9", quality: str = "720p",
               variations: int = 1) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("prompt is empty")
        if aspect not in ASPECTS:
            raise ValueError(f"aspect must be one of {sorted(ASPECTS)}, got {aspect!r}")
        if quality not in QUALITIES:
            raise ValueError(f"quality must be one of {QUALITIES}, got {quality!r}")
        if variations not in (1, 2):
            raise ValueError(f"variations must be 1 or 2 (the site's input caps at 2), got {variations}")
        text = self._post({
            "actionType": "full-video-generate",
            "prompt": prompt.strip(),
            "totalVariations": variations,
            "aspectRatio": ASPECTS[aspect],
            "video_quality": quality,
        })
        state, detail = self.classify(text)
        if state == "busy":
            raise VeoFreeError("BUSY", f"a generation is already running on this account: {detail}")
        if state == "limit":
            raise VeoFreeError("LIMIT", f"the free account is rate-limited: {detail}")
        if state == "error":
            raise VeoFreeError("UPSTREAM", detail)
        if state == "pending":
            raise VeoFreeError("UPSTREAM", "submit returned an empty body -- no sceneData handle")
        return text

    def poll(self, scene: str) -> str | None:
        """None means still rendering. A string is the final video URL."""
        text = self._post({"actionType": "final-video-results", "sceneData": scene})
        state, detail = self.classify(text)
        if state == "pending":
            return None
        if state == "limit":
            raise VeoFreeError("LIMIT", detail)
        if state in ("error", "busy"):
            raise VeoFreeError("UPSTREAM", detail)
        url = text.strip()
        # logic.js does exactly this rewrite before handing the URL to a <video> element.
        if "videos/" in url:
            url = url.replace("videos/", "video/")
        if not url.startswith("http"):
            raise VeoFreeError("UPSTREAM", f"poll returned a non-URL: {url[:200]!r}")
        return url

    def wait(self, scene: str, timeout: int = 1200, first_delay: int = 85,
             interval: int = 5, on_status=None) -> str:
        """The site's own cadence is 85s before the first poll, then every 20s.

        We keep the 85s but drop the gap to 5s, because the server paces us anyway: a single poll
        blocks ~100s, so the real cycle time is the request itself, not our sleep. A 20s gap on top
        of that would only add dead time. The 85s head start is kept because it is the site's own
        number and it costs one wasted request to find out otherwise.
        """
        t0 = time.time()
        if on_status:
            on_status("submitted", 0.0)
        slept = 0.0
        while slept < first_delay and time.time() - t0 < timeout:
            time.sleep(min(5.0, first_delay - slept))
            slept += 5.0
        last = None
        while time.time() - t0 < timeout:
            url = self.poll(scene)
            el = round(time.time() - t0, 1)
            if url:
                if on_status:
                    on_status("succeeded", el)
                return url
            if on_status and last != "pending":
                on_status("pending", el)
                last = "pending"
            time.sleep(interval)
        raise VeoFreeError("TIMEOUT", f"no video after {timeout}s (sceneData still pending)")

    def download(self, url: str, dest: pathlib.Path | None = None, *, verbose: bool = True) -> bytes:
        """Fetch in-page first so any cookie/referer requirement is satisfied; fall back to plain HTTP.

        The site warns "We Don't host or save the video so please download this video", so the
        caller should persist these bytes immediately rather than keep the URL around.
        """
        js = """
        (async () => {
          try {
            const r = await fetch(%s, {credentials: 'include'});
            if (!r.ok) return JSON.stringify({fatal: 'HTTP ' + r.status});
            const b = new Uint8Array(await r.arrayBuffer());
            let s = '';
            const CH = 0x8000;
            for (let i = 0; i < b.length; i += CH) s += String.fromCharCode.apply(null, b.subarray(i, i + CH));
            return JSON.stringify({b64: btoa(s), bytes: b.length});
          } catch (e) { return JSON.stringify({fatal: 'fetch threw: ' + String(e && e.message || e)}); }
        })()
        """ % json.dumps(url)
        blob: bytes | None = None
        try:
            with Page(self.match, port=self.port) as pg:
                raw = pg.evaluate(js, timeout=300)
            d = json.loads(raw or "{}")
            if d.get("b64"):
                blob = base64.b64decode(d["b64"])
            elif verbose:
                print(f"    in-page fetch said {d.get('fatal')!r}; trying plain HTTP")
        except Exception as exc:
            if verbose:
                print(f"    in-page fetch failed ({type(exc).__name__}); trying plain HTTP")
        if blob is None:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": GEN_URL})
            blob = urllib.request.urlopen(req, timeout=300).read()
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            if verbose:
                print(f"[+] {dest}  {len(blob)} bytes")
        return blob


# ---- CLI ---------------------------------------------------------------------------------

def _sess(a) -> VeoFreeSession:
    return VeoFreeSession(a.match, port=a.port)


def cmd_whoami(a) -> int:
    print(json.dumps(_sess(a).whoami(), indent=1))
    return 0


def cmd_submit(a) -> int:
    scene = _sess(a).submit(a.prompt, a.aspect, a.quality, a.variations)
    print(f"sceneData: {scene}")
    return 0


def cmd_poll(a) -> int:
    url = _sess(a).poll(a.scene)
    print(url if url else "(pending -- still rendering)")
    return 0


def cmd_gen(a) -> int:
    s = _sess(a)
    scene = s.submit(a.prompt, a.aspect, a.quality, a.variations)
    print(f"sceneData: {scene}")
    url = s.wait(scene, timeout=a.timeout,
                 on_status=lambda st, el: print(f"    [{el:7.1f}s] {st}"))
    print(f"video url host: {url.split('/')[2] if '://' in url else '?'}")
    dest = pathlib.Path(a.out) if a.out else pathlib.Path(
        r"D:\omniroute-monetizer\state\video_proofs") / "veoaifree_latest.mp4"
    blob = s.download(url, dest)
    is_mp4 = len(blob) > 12 and blob[4:8] == b"ftyp"
    print(f"bytes={len(blob)} mp4={is_mp4}")
    return 0 if is_mp4 else 1


CHAIN = [
    ("chrome debug port", "start the automation Chrome with --remote-debugging-port=<port>"),
    ("veoaifree tab", f"open {GEN_URL} in that Chrome"),
    ("logged in", "sign in to veoaifree.com in that tab (a login wall here is a real finding, "
                  "not something to work around)"),
    ("ajax_object + nonce", "reload the generator page so WordPress localises a fresh nonce"),
    ("nonce accepted", "reload the tab; if it still fails the session cookie has expired"),
]


def cmd_doctor(a) -> int:
    """Prove every link without generating anything. Costs nothing -- generation here is free,
    but a needless submit would still burn a rate-limit slot."""
    s = _sess(a)
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            detail = fn()
            print(f"  [ok]   {name}: {detail}")
            return True
        except Exception as exc:
            print(f"  [FAIL] {name}: {type(exc).__name__}: {scrub(str(exc))[:300]}")
            fix = dict(CHAIN).get(name)
            if fix:
                print(f"         FIX: {fix}")
            ok = False
            return False

    print(f"veoaifree doctor  (port {a.port}, match {a.match!r})")
    info: dict = {}

    def _tab():
        info.update(s.whoami())
        return info.get("url", "?")

    if not step("veoaifree tab", _tab):
        print("\nverdict: BROKEN at the first link.")
        return 1
    step("logged in", lambda: "yes" if info.get("logged_in")
         else (_ for _ in ()).throw(RuntimeError("body has no 'logged-in' class")))
    step("ajax_object + nonce", lambda: f"nonce present, {info.get('nonce_len')} chars"
         if info.get("has_nonce") else (_ for _ in ()).throw(RuntimeError("no ajax_object.nonce")))
    step("plan", lambda: f"{info.get('plan')} (success {info.get('total_success')}, "
                         f"failed {info.get('total_failed')})")

    # Zero-cost nonce proof: poll a handle that cannot exist. A bad nonce dies as -1; a good one
    # gets to the handler, which answers empty (pending) or an error string. Either proves auth.
    def _nonce():
        try:
            s.poll("doctor-probe-not-a-real-scene")
            return "accepted (handler answered a real URL, unexpected but fine)"
        except VeoFreeError as exc:
            if exc.kind == "NONCE":
                raise
            return f"accepted (handler reached; it said {exc.kind})"
    step("nonce accepted", _nonce)

    print(f"\nverdict: {'READY' if ok else 'BROKEN'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--match", default=MATCH, help="substring of the veoaifree tab url/title")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"Chrome remote-debugging port (default {DEFAULT_PORT})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami").set_defaults(fn=cmd_whoami)
    d = sub.add_parser("doctor"); d.set_defaults(fn=cmd_doctor)

    def gen_args(p):
        p.add_argument("prompt")
        p.add_argument("--aspect", default="16:9", choices=sorted(ASPECTS))
        p.add_argument("--quality", default="720p", choices=list(QUALITIES))
        p.add_argument("--variations", type=int, default=1, choices=(1, 2))

    sb = sub.add_parser("submit"); gen_args(sb); sb.set_defaults(fn=cmd_submit)
    pl = sub.add_parser("poll"); pl.add_argument("scene"); pl.set_defaults(fn=cmd_poll)
    g = sub.add_parser("gen"); gen_args(g)
    g.add_argument("--out", default=""); g.add_argument("--timeout", type=int, default=1200)
    g.set_defaults(fn=cmd_gen)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except VeoFreeError as exc:
        print(f"!! {exc.kind}: {scrub(exc.message)[:500]}")
        return 2
    except SystemExit:
        raise
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {scrub(str(exc))[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
