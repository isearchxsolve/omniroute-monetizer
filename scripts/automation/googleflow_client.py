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
from cdp import Page  # noqa: E402  -- raw CDP, no Playwright (see cdp.py docstring)

HOST = "https://aisandbox-pa.googleapis.com"
SUBMIT_URL = f"{HOST}/v1/video:batchAsyncGenerateVideoText"
POLL_URL = f"{HOST}/v1/video:batchCheckAsyncVideoGenerationStatus"
CREDITS_URL = f"{HOST}/v1/credits"
MEDIA_URL = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name={}"

RECAPTCHA_SITEKEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

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


class FlowSession:
    """A Flow identity plus the live page that can mint captcha tokens for it."""

    def __init__(self, match: str = "tools/flow"):
        self.match = match
        self.email: str | None = None
        self.expires: str | None = None
        self.project_id: str | None = None
        self._token: str | None = None

    def refresh(self) -> FlowSession:
        with Page(self.match) as p:
            s = json.loads(p.evaluate(SESSION_JS, timeout=60))
            if s.get("error") or not s.get("token"):
                raise RuntimeError(f"no Flow session token: {s.get('error') or 'access_token absent'}")
            self.email, self.expires, self._token = s["email"], s["expires"], s["token"]
            url = p.evaluate("location.href") or ""
        m = re.search(r"/project/([0-9a-f\-]{36})", url)
        if m:
            self.project_id = m.group(1)
        return self

    @property
    def token(self) -> str:
        if not self._token:
            self.refresh()
        return self._token  # type: ignore[return-value]

    def mint_captcha(self, action: str | None = None) -> str:
        opts = json.dumps({"action": action}) if action else "{}"
        with Page(self.match) as p:
            r = json.loads(p.evaluate(MINT_JS % (json.dumps(RECAPTCHA_SITEKEY), opts), timeout=60))
        if r.get("error") or not r.get("token"):
            raise RuntimeError(f"captcha mint failed: {r.get('error') or 'empty token'}")
        return r["token"]


# --------------------------------------------------------------------------- http side


def request(url: str, token: str, payload: dict | None = None, method: str = "POST",
            timeout: int = 120) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


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
    body = build_submit_body(prompt, sess.mint_captcha(), sess.project_id, **kw)
    status, text = request(SUBMIT_URL, sess.token, body)
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


def wait(sess: FlowSession, media_id: str, *, budget: int = 600, every: int = 10) -> dict:
    """Poll until the media reports a terminal status. Observed: SCHEDULED -> SUCCESSFUL in ~40s."""
    deadline = time.time() + budget
    last = "?"
    while time.time() < deadline:
        st, m = media_status(poll_once(sess, media_id))
        if st != last:
            print(f"    [{int(time.time() - (deadline - budget)):>3}s] {st}")
            last = st
        if "SUCCESSFUL" in st:
            return m
        if "FAIL" in st or "ERROR" in st:
            raise RuntimeError(f"generation failed: {st}")
        time.sleep(every)
    raise TimeoutError(f"still {last} after {budget}s")


# --------------------------------------------------------------------------- commands


def cmd_probe(a) -> int:
    """Zero credits: does a MINTED captcha get accepted? Empty prompt guarantees no generation."""
    sess = FlowSession().refresh()
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


def cmd_credits(a) -> int:
    sess = FlowSession().refresh()
    status, text = request(CREDITS_URL, sess.token, None, method="GET")
    print(f"{sess.email:<32} HTTP {status}  {scrub(text)[:200]}")
    return 0 if status == 200 else 1


def cmd_generate(a) -> int:
    sess = FlowSession().refresh()
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
    r = submit(sess, a.prompt, model=model, resolution=a.resolution, aspect=a.aspect)
    media_id = (r.get("media") or [{}])[0].get("name")
    print(f"  submitted        {media_id}   remainingCredits={r.get('remainingCredits')}")
    m = wait(sess, media_id, budget=a.budget)
    print(f"  done in {time.time() - t0:.0f}s   length={m.get('video', {}).get('dimensions', {}).get('length')}"
          f"  bytes={m.get('mediaMetadata', {}).get('mediaBlobSize')}")
    print(f"  fetch with       GET {MEDIA_URL.format(media_id)}")
    print("                   (labs.google cookie auth -- same profile as the tab)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="zero-credit check that a minted captcha is accepted")
    p.add_argument("--actions", nargs="*",
                   default=["", "generate", "GENERATE_VIDEO", "video_generation", "PINHOLE"])
    p.set_defaults(fn=cmd_probe)

    c = sub.add_parser("credits"); c.set_defaults(fn=cmd_credits)

    g = sub.add_parser("generate", help="submit one real generation (spends credits)")
    g.add_argument("prompt")
    g.add_argument("--model", default="fast", choices=[*MODELS, *MODELS.values()])
    g.add_argument("--resolution", default="720p", choices=[*RESOLUTIONS])
    g.add_argument("--aspect", default="16:9", choices=[*ASPECTS])
    g.add_argument("--budget", type=int, default=600)
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
