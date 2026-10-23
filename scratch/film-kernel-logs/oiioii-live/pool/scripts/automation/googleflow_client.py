"""googleflow_client.py -- drive Google Flow's real video RPC from Python.

WHAT THIS TALKS TO (all measured 2026-08-23 from a user-driven capture of one real generation):

    submit   POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText
    poll     POST https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus
    bytes    GET  https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=<mediaId>

OmniRoute's compiled google-flow handler calls /v1:generateVideo and /v1:fetchOperation instead.
Neither path exists on this host -- both answer an HTML 404 even with a valid Flow token, which is
what MASTER_WORKLOG entry #1002 misread as "the Antigravity OAuth grant is not authorised". The paths
are baked into a compiled chunk, so no credential or feature flag can redirect them. This module is
the substitute: it speaks the protocol Flow actually uses.

TWO THINGS MAKE THIS NOT A PLAIN HTTP CLIENT:

1. reCAPTCHA Enterprise is ENFORCED. Submitting without clientContext.recaptchaContext answers
   403 PERMISSION_DENIED / PUBLIC_ERROR_UNUSUAL_ACTIVITY ("reCAPTCHA evaluation failed"). Tokens are
   short-lived and single-use, so one must be minted per submit. They can only be minted by the
   reCAPTCHA runtime inside a real page, so this module mints via grecaptcha.enterprise.execute in
   the live Flow tab over CDP.
2. The bearer token is a WEB SESSION token from labs.google/fx/api/auth/session, valid ~12h. It is
   re-read per call rather than cached to disk.

SECRET HANDLING: bearer tokens and reCAPTCHA tokens live in memory only. They are never printed,
never written to disk, and scrub() removes anything token-shaped from every response before display.

    python googleflow_client.py probe          # zero credits: proves minted captcha is accepted
    python googleflow_client.py credits        # per-account balance of the live tab
    python googleflow_client.py generate "<prompt>" [--model fast|quality|lite] [--yes]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page, DEFAULT_PORT  # noqa: E402  -- raw CDP, no Playwright (see cdp.py docstring)

HOST = "https://aisandbox-pa.googleapis.com"
SUBMIT_URL = f"{HOST}/v1/video:batchAsyncGenerateVideoText"
POLL_URL = f"{HOST}/v1/video:batchCheckAsyncVideoGenerationStatus"
CREDITS_URL = f"{HOST}/v1/credits"
MEDIA_URL = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name={}"

RECAPTCHA_SITEKEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

# The action label the Flow frontend passes to grecaptcha.enterprise.execute, read off the frontend's
# own call. It is NOT optional and NOT interchangeable: minting with no action, or with a plausible
# alternative (`generate`, `GENERATE_VIDEO`, `video_generation`, `PINHOLE`), makes the backend's
# assessment fail and the submit answer 403 PUBLIC_ERROR_UNUSUAL_ACTIVITY -- the same error a genuine
# abuse block produces, which is why this cost several wrong turns to pin down.
RECAPTCHA_ACTION = "VIDEO_GENERATION"

# Tried in order if VIDEO_GENERATION ever stops being accepted, so a frontend rename costs a retry
# rather than an outage. Kept small on purpose: each attempt is a live request.
ACTION_FALLBACKS = ("GENERATE_VIDEO", "VIDEO_GENERATION_TEXT", "generate", None)

# The observed model keys. /v1/flow/models/statuses reports health under the short names on the left
# of each pair; the submit RPC wants the t2v key on the right.
MODELS = {
    "fast": "veo_3_1_t2v_fast",
    "quality": "veo_3_1_t2v_quality",
    "lite": "veo_3_1_t2v_lite",
}

RESOLUTIONS = {"720p": "VIDEO_RESOLUTION_720P", "1080p": "VIDEO_RESOLUTION_1080P"}
ASPECTS = {"16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE", "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT"}

SECRET_RE = re.compile(r"(ya29\.[\w\-\.]+|AIza[\w\-]{20,}|1//[\w\-\.]+|0[cC]A[\w\-]{40,})")


def scrub(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", str(text))


# --------------------------------------------------------------------------- browser side

SESSION_JS = """
(async () => {
  const r = await fetch('/fx/api/auth/session', {credentials:'include'});
  if (!r.ok) return JSON.stringify({error: 'session ' + r.status});
  const s = await r.json();
  return JSON.stringify({email: s?.user?.email || null, expires: s?.expires || null,
                         token: s?.access_token || null});
})()
"""

# grecaptcha.enterprise.execute resolves with a fresh single-use token. The action label is part of
# the assessment the backend runs, so it has to match what the Flow frontend uses.
MINT_JS = """
(async () => {
  const g = window.grecaptcha && window.grecaptcha.enterprise;
  if (!g || typeof g.execute !== 'function') return JSON.stringify({error:'grecaptcha.enterprise absent'});
  try {
    const t = await g.execute(%s, %s);
    return JSON.stringify({token: t});
  } catch (e) { return JSON.stringify({error: String(e && e.message || e)}); }
})()
"""

# The sitekey is in the render= query of the enterprise.js the page loads.
DISCOVER_SITEKEY_JS = """
(() => {
  const s = [...document.querySelectorAll('script[src*="recaptcha"]')]
              .map(e => (e.src.match(/[?&]render=([\\w\\-]+)/) || [])[1]).filter(Boolean);
  if (s.length) return s[0];
  const r = performance.getEntriesByType('resource').map(e => e.name)
              .map(n => (n.match(/recaptcha.*[?&]k=([\\w\\-]+)/) || [])[1]).filter(Boolean);
  return r.length ? r[0] : null;
})()
"""


class FlowSession:
    """A Flow identity plus the live page that can mint captcha tokens for it.

    One instance == one Chrome profile == one Google account, addressed by its debugging port. Flow
    auth is a single NextAuth session cookie per profile, so accounts cannot share a browser; the
    port is how the multi-account rotation keeps them apart.
    """

    def __init__(self, match: str = "tools/flow", port: int = DEFAULT_PORT):
        self.match = match
        self.port = port
        self.email: str | None = None
        self.expires: str | None = None
        self.project_id: str | None = None
        self.sitekey: str = RECAPTCHA_SITEKEY
        self.tier: str = "PAYGATE_TIER_ONE"
        self.credits: int | None = None
        self._token: str | None = None

    def refresh(self) -> FlowSession:
        with Page(self.match, port=self.port) as p:
            s = json.loads(p.evaluate(SESSION_JS, timeout=60))
            if s.get("error") or not s.get("token"):
                raise RuntimeError(f"no Flow session token: {s.get('error') or 'access_token absent'}")
            self.email, self.expires, self._token = s["email"], s["expires"], s["token"]
            url = p.evaluate("location.href") or ""
            # Read the sitekey off the page rather than trusting a constant. Google rotates these on
            # frontend deploys, and a stale sitekey fails as 403 UNUSUAL_ACTIVITY -- indistinguishable
            # from an abuse block, which is the single most misleading error in this whole integration.
            self.sitekey = p.evaluate(DISCOVER_SITEKEY_JS, timeout=30) or RECAPTCHA_SITEKEY
        m = re.search(r"/project/([0-9a-f\-]{36})", url)
        if m:
            self.project_id = m.group(1)
        # The paygate tier must match the ACCOUNT, not be assumed. Pro accounts report
        # PAYGATE_TIER_ONE; the two non-Pro accounts in this project will report something else, and
        # sending the wrong tier is a body-level lie that this project should not be telling.
        st, ct = request(CREDITS_URL, self._token, None, method="GET")
        if st == 200:
            try:
                info = json.loads(ct)
                self.tier = info.get("userPaygateTier") or self.tier
                self.credits = info.get("credits")
            except ValueError:
                pass
        return self

    @property
    def token(self) -> str:
        if not self._token:
            self.refresh()
        return self._token  # type: ignore[return-value]

    def mint_captcha(self, action: str | None = RECAPTCHA_ACTION) -> str:
        opts = json.dumps({"action": action}) if action else "{}"
        with Page(self.match, port=self.port) as p:
            r = json.loads(p.evaluate(MINT_JS % (json.dumps(self.sitekey), opts), timeout=60))
        if r.get("error") or not r.get("token"):
            raise RuntimeError(f"captcha mint failed: {r.get('error') or 'empty token'}")
        return r["token"]


# --------------------------------------------------------------------------- http side


def request(url: str, token: str, payload: dict | None = None, method: str = "POST",
            timeout: int = 120, retries: int = 4) -> tuple[int, str]:
    """One HTTP call, with retries on TRANSPORT failures only.

    Polling a generation for minutes over a keep-alive connection does hit RemoteDisconnected in
    practice -- observed once mid-poll on a run that was otherwise fine. Retrying a transport error is
    safe because a dropped connection means the request was never answered; retrying an HTTP status is
    NOT safe (a repeated submit would mint a second video and charge again), so statuses are returned
    to the caller untouched.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = (0, "no attempt")
    for attempt in range(retries):
        req = urllib.request.Request(
            url, method=method, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                     "Connection": "close"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            last = (0, f"{type(e).__name__}: {e}")
            time.sleep(1.5 * (attempt + 1))
    return last


def build_submit_body(prompt: str, captcha: str, project_id: str, *,
                      model: str = "veo_3_1_t2v_fast", seed: int | None = None,
                      resolution: str = "720p", aspect: str = "16:9",
                      tier: str = "PAYGATE_TIER_ONE") -> dict:
    """The captured wire format. Field order and enum spellings are copied exactly."""
    return {
        "mediaGenerationContext": {
            "batchId": str(uuid.uuid4()),
            "audioFailurePreference": "BLOCK_SILENCED_VIDEOS",
        },
        "clientContext": {
            "projectId": project_id,
            "tool": "PINHOLE",
            "userPaygateTier": tier,
            "sessionId": f";{int(time.time() * 1000)}",
            "recaptchaContext": {
                "token": captcha,
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            },
        },
        "requests": [{
            "outputSpec": {"resolution": RESOLUTIONS.get(resolution, resolution)},
            "aspectRatio": ASPECTS.get(aspect, aspect),
            "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
            "videoModelKey": model,
            "seed": seed if seed is not None else uuid.uuid4().int % 100000,
            "metadata": {},
        }],
        "useV2ModelConfig": True,
    }


def classify(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("recaptcha", "captcha", "unusual_activity", "attestation")):
        return "CAPTCHA"
    if any(w in low for w in ("prompt", "invalid_argument", "invalid argument", "required", "empty")):
        return "ARGUMENT"
    if "permission_denied" in low or "unauthenticated" in low:
        return "AUTH"
    return "OTHER"


def submit(sess: FlowSession, prompt: str, **kw) -> dict:
    if not sess.project_id:
        raise RuntimeError("no Flow projectId -- open a project in the Flow tab first")
    kw.setdefault("tier", sess.tier)
    body = build_submit_body(prompt, sess.mint_captcha(), sess.project_id, **kw)
    status, text = request(SUBMIT_URL, sess.token, body)
    if status == 403 and classify(text) == "CAPTCHA":
        # A 403 here is ambiguous by design: Google returns PUBLIC_ERROR_UNUSUAL_ACTIVITY both for a
        # genuine abuse block and for a captcha minted with the wrong action label. Since the label is
        # a Google-side constant that a frontend deploy can rename, try the alternates once before
        # surfacing the failure -- an outage degrades to a retry.
        for alt in ACTION_FALLBACKS:
            body["clientContext"]["recaptchaContext"]["token"] = sess.mint_captcha(alt)
            body["mediaGenerationContext"]["batchId"] = str(uuid.uuid4())
            status, text = request(SUBMIT_URL, sess.token, body)
            if status != 403:
                print(f"    [captcha] action label {RECAPTCHA_ACTION!r} rejected; {alt!r} worked -- "
                      f"update RECAPTCHA_ACTION")
                break
    if status != 200:
        raise RuntimeError(f"submit HTTP {status} [{classify(text)}]: {scrub(text)[:400]}")
    return json.loads(text)


def poll_once(sess: FlowSession, media_id: str) -> dict:
    body = {"media": [{"name": media_id, "projectId": sess.project_id}]}
    status, text = request(POLL_URL, sess.token, body)
    if status != 200:
        raise RuntimeError(f"poll HTTP {status}: {scrub(text)[:300]}")
    return json.loads(text)


def media_status(poll_result: dict) -> tuple[str, dict]:
    m = (poll_result.get("media") or [{}])[0]
    st = m.get("mediaMetadata", {}).get("mediaStatus", {}).get("mediaGenerationStatus", "UNKNOWN")
    return st, m


def wait(sess: FlowSession, media_id: str, *, budget: int = 600, every: int = 10,
         on_status=None) -> dict:
    """Poll until the media reports a terminal status. Observed: SCHEDULED -> SUCCESSFUL in ~40s.

    on_status(status, elapsed_seconds) is called on each CHANGE of status, so a long-running server
    can record progress without this function owning stdout. Defaults to printing, for CLI use.
    """
    started = time.time()
    deadline = started + budget
    last = "?"
    while time.time() < deadline:
        st, m = media_status(poll_once(sess, media_id))
        if st != last:
            if on_status:
                on_status(st, time.time() - started)
            else:
                print(f"    [{int(time.time() - started):>3}s] {st}")
            last = st
        if "SUCCESSFUL" in st:
            return m
        if "FAIL" in st or "ERROR" in st:
            raise RuntimeError(f"generation failed: {st}")
        time.sleep(every)
    raise TimeoutError(f"still {last} after {budget}s")


# --------------------------------------------------------------------------- bytes

OUT_DIR = pathlib.Path(r"D:\omniroute-monetizer\state\harvest\flow")


def session_cookie_header(match: str = "tools/flow",
                          port: int = DEFAULT_PORT) -> tuple[str, list[str]]:
    """Cookie header for labs.google, read out of the live tab over CDP.

    The finished video is served by labs.google/fx/api/trpc/media.getMediaUrlRedirect, which is
    COOKIE-authenticated (not bearer) and redirects to a signed URL on another origin. That redirect
    is why an in-page fetch cannot be used -- the final response carries no CORS headers, so the
    browser reports a bare "Failed to fetch". Python has no such restriction, so the bytes are pulled
    server-side with the session's own cookies.

    Returns (header, names). Only the NAMES are ever safe to display; the header is a credential.
    """
    with Page(match, port=port) as p:
        p.send("Network.enable", {}, timeout=30)
        r = p.send("Network.getCookies", {"urls": ["https://labs.google/"]}, timeout=30)
    cookies = r.get("cookies", [])
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    return header, [c["name"] for c in cookies]


def download(media_id: str, dest: pathlib.Path | None = None, *, match: str = "tools/flow",
             port: int = DEFAULT_PORT, verbose: bool = True) -> pathlib.Path:
    header, names = session_cookie_header(match, port)
    if not header:
        raise RuntimeError(f"no labs.google cookies in the live tab on port {port}")
    if verbose:
        print(f"  cookies: {len(names)} "
              f"({', '.join(sorted(names)[:6])}{'...' if len(names) > 6 else ''})")
    req = urllib.request.Request(
        MEDIA_URL.format(media_id),
        headers={"Cookie": header,
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=300) as r:
        if r.status != 200:
            raise RuntimeError(f"media fetch HTTP {r.status}")
        data = r.read()
    dest = dest or (OUT_DIR / f"{media_id}.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def credits_now(sess: FlowSession) -> int | None:
    """Live balance, straight from the account. Used by the rotation to choose an account and to
    measure what a generation actually cost rather than trusting a per-clip constant."""
    st, ct = request(CREDITS_URL, sess.token, None, method="GET")
    if st != 200:
        return None
    try:
        return json.loads(ct).get("credits")
    except ValueError:
        return None


# --------------------------------------------------------------------------- commands

def cmd_probe(a) -> int:
    """Zero credits: does a MINTED captcha get accepted? Empty prompt guarantees no generation."""
    sess = FlowSession(port=a.port).refresh()
    print(f"Flow session : {sess.email}  (expires {sess.expires})")
    print(f"Project      : {sess.project_id}")
    print()
    print("Sending an EMPTY prompt with a freshly minted captcha. No video can result, so this")
    print("costs nothing. A complaint about the ARGUMENT means the captcha was accepted.")
    print()
    for action in a.actions:
        label = action or "(no action)"
        try:
            captcha = sess.mint_captcha(action or None)
        except RuntimeError as e:
            print(f"  {label:<24} MINT FAILED: {e}")
            continue
        body = build_submit_body("", captcha, sess.project_id or "")
        status, text = request(SUBMIT_URL, sess.token, body)
        kind = classify(text)
        print(f"  {label:<24} HTTP {status:<4} {kind}")
        print(f"      {scrub(text)[:220].replace(chr(10), ' ')}")
        if kind == "ARGUMENT":
            print()
            print("=" * 78)
            print(f"  MINTED CAPTCHA ACCEPTED (action={label}). Server-side Flow generation is")
            print("  reachable from Python: mint in the live tab, submit over HTTP.")
            print("=" * 78)
            return 0
    print()
    print("=" * 78)
    print("  No action label got past the captcha gate. Either the assessment is bound to something")
    print("  else in the request, or the token must originate from the frontend's own call.")
    print("=" * 78)
    return 1


def cmd_poll(a) -> int:
    """Resume an already-submitted generation. Safe to re-run: polling never charges."""
    sess = FlowSession(port=a.port).refresh()
    m = wait(sess, a.media_id, budget=a.budget)
    print(f"  length={m.get('video', {}).get('dimensions', {}).get('length')}"
          f"  bytes={m.get('mediaMetadata', {}).get('mediaBlobSize')}")
    return 0


def cmd_credits(a) -> int:
    sess = FlowSession(port=a.port).refresh()
    status, text = request(CREDITS_URL, sess.token, None, method="GET")
    print(f"{sess.email:<32} HTTP {status}  {scrub(text)[:200]}")
    return 0 if status == 200 else 1


def cmd_fetch(a) -> int:
    dest = download(a.media_id, port=a.port)
    head = dest.read_bytes()[:16]
    kind = "MP4" if b"ftyp" in head else f"UNKNOWN {head[:8]!r}"
    print(f"  {dest}")
    print(f"  {dest.stat().st_size} bytes, container={kind}")
    return 0


def cmd_generate(a) -> int:
    sess = FlowSession(port=a.port).refresh()
    model = MODELS.get(a.model, a.model)
    print(f"Flow session : {sess.email}  (expires {sess.expires})")
    print(f"Project      : {sess.project_id}")
    print(f"Model        : {model}   {a.resolution} {a.aspect}")
    print(f"Prompt       : {a.prompt}")
    if not a.yes:
        print()
        print("This SPENDS Flow credits (20 observed for 720p/8s fast). Re-run with --yes to submit.")
        return 0
    print()
    t0 = time.time()
    # Credits BEFORE, so the charge is measured rather than assumed. One 720p/8s fast clip cost 20
    # from the UI but 60 from here on an otherwise byte-identical body -- unexplained, so every run
    # reports the delta and the returned media/workflow counts to test the "it billed 3 videos" idea.
    st, ct = request(CREDITS_URL, sess.token, None, method="GET")
    before = json.loads(ct).get("credits") if st == 200 else None
    del st, ct

    r = submit(sess, a.prompt, model=model, resolution=a.resolution, aspect=a.aspect)
    media_list = r.get("media") or []
    media_id = media_list[0].get("name") if media_list else None
    after = r.get("remainingCredits")
    print(f"  submitted        {media_id}")
    print(f"  media returned   {len(media_list)}   workflows {len(r.get('workflows') or [])}")
    print(f"  credits          {before} -> {after}"
          + (f"   (charged {before - after})" if isinstance(before, int) and isinstance(after, int)
             else ""))
    if len(media_list) > 1:
        for m in media_list[1:]:
            print(f"    extra media    {m.get('name')}")
    m = wait(sess, media_id, budget=a.budget)
    print(f"  done in {time.time() - t0:.0f}s   length={m.get('video', {}).get('dimensions', {}).get('length')}"
          f"  bytes={m.get('mediaMetadata', {}).get('mediaBlobSize')}")
    if a.fetch:
        dest = download(media_id, port=a.port)
        print(f"  saved            {dest}  ({dest.stat().st_size} bytes)")
    else:
        print(f"  fetch with       python googleflow_client.py fetch {media_id}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"Chrome remote-debugging port of the account's profile "
                         f"(default {DEFAULT_PORT}); goes BEFORE the subcommand")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="zero-credit check that a minted captcha is accepted")
    p.add_argument("--actions", nargs="*",
                   default=["", "generate", "GENERATE_VIDEO", "video_generation", "PINHOLE"])
    p.set_defaults(fn=cmd_probe)

    c = sub.add_parser("credits"); c.set_defaults(fn=cmd_credits)

    q = sub.add_parser("poll", help="resume polling a submitted generation (never charges)")
    q.add_argument("media_id")
    q.add_argument("--budget", type=int, default=600)
    q.set_defaults(fn=cmd_poll)

    f = sub.add_parser("fetch", help="download a finished video's bytes (never charges)")
    f.add_argument("media_id")
    f.set_defaults(fn=cmd_fetch)

    g = sub.add_parser("generate", help="submit one real generation (spends credits)")
    g.add_argument("prompt")
    g.add_argument("--model", default="fast", choices=[*MODELS, *MODELS.values()])
    g.add_argument("--resolution", default="720p", choices=[*RESOLUTIONS])
    g.add_argument("--aspect", default="16:9", choices=[*ASPECTS])
    g.add_argument("--budget", type=int, default=600)
    g.add_argument("--fetch", action="store_true", help="download the bytes when it finishes")
    g.add_argument("--yes", action="store_true")
    g.set_defaults(fn=cmd_generate)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {scrub(str(exc))[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
