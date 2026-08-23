"""Is Google Flow's reCAPTCHA token ENFORCED on the real video RPC?

WHY THIS EXISTS (measured 2026-08-23):
googleflow_token_probe.py proved the Flow web token authenticates and found the live endpoint:
    POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText
A user-driven capture of one real generation (20 credits, 1050 -> 1030) then gave the exact body.
That body carries a reCAPTCHA Enterprise token:
    clientContext.recaptchaContext = {token: "0cAFcWeA...", applicationType: RECAPTCHA_APPLICATION_TYPE_WEB}

Everything about wiring Flow into OmniRoute hinges on one question: is that token CHECKED? If it is
not, a plain server-side HTTP shim can drive Flow with nothing but a bearer token. If it is, the shim
must mint a fresh token per request, which means keeping a real browser page alive and calling
grecaptcha.enterprise.execute over CDP -- a much heavier design.

STAGE A (default, ZERO CREDITS): send a body with NO recaptchaContext and an EMPTY prompt. Both are
invalid, so no video can be produced either way, and the error text tells us which check fires first:
    complains about captcha / verification  -> ENFORCED
    complains about the prompt / argument   -> the captcha gate did not stop us
STAGE B (--live, SPENDS ~20 CREDITS): only worth running if stage A points at "not enforced". Sends a
valid body with no recaptchaContext. A 200 here is proof a pure server-side shim works.

SECRET HANDLING: the bearer token is fetched into memory over CDP, never printed, never written to
disk. Responses are scrubbed of token-shaped strings before display.

Read-only with respect to OmniRoute's database and service.

    python googleflow_submit_probe.py           # zero-credit discriminator
    python googleflow_submit_probe.py --live     # spends ~20 Flow credits, proves end-to-end
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402  -- raw CDP, no Playwright (see cdp.py docstring)

HOST = "https://aisandbox-pa.googleapis.com"
SUBMIT = f"{HOST}/v1/video:batchAsyncGenerateVideoText"
POLL = f"{HOST}/v1/video:batchCheckAsyncVideoGenerationStatus"

# The Flow project the captured generation ran in. clientContext.projectId must be a project the
# signed-in account actually owns, so this is reused rather than invented.
PROJECT_ID = "0db18532-cdf2-4d16-a2d4-c3d69e0202c2"

SESSION_JS = """
(async () => {
  const r = await fetch('/fx/api/auth/session', {credentials:'include'});
  if (!r.ok) return JSON.stringify({error: 'session ' + r.status});
  const s = await r.json();
  return JSON.stringify({email: s?.user?.email || null, expires: s?.expires || null,
                         token: s?.access_token || null});
})()
"""

SECRET_RE = re.compile(r"(ya29\.[\w\-\.]+|AIza[\w\-]{20,}|1//[\w\-\.]+|0cAFcWeA[\w\-]{40,})")


def scrub(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", text)


def build_body(prompt: str, *, model: str = "veo_3_1_t2v_fast", seed: int = 22448,
               recaptcha: str | None = None) -> dict:
    """The captured wire format, verbatim except for the fields this probe varies."""
    client_context = {
        "projectId": PROJECT_ID,
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_ONE",
        "sessionId": ";1787489037003",
    }
    if recaptcha:
        client_context["recaptchaContext"] = {
            "token": recaptcha, "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"}
    return {
        "mediaGenerationContext": {
            "batchId": str(uuid.uuid4()),
            "audioFailurePreference": "BLOCK_SILENCED_VIDEOS",
        },
        "clientContext": client_context,
        "requests": [{
            "outputSpec": {"resolution": "VIDEO_RESOLUTION_720P"},
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
            "videoModelKey": model,
            "seed": seed,
            "metadata": {},
        }],
        "useV2ModelConfig": True,
    }


def post(url: str, token: str, payload: dict) -> tuple[int, str, str]:
    req = urllib.request.Request(
        url, method="POST", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.headers.get("content-type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "", f"{type(e).__name__}: {e}"


def classify(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("recaptcha", "captcha", "verification", "abuse", "attestation")):
        return "CAPTCHA"
    if any(w in low for w in ("prompt", "invalid_argument", "invalid argument", "required")):
        return "ARGUMENT"
    return "OTHER"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="send a VALID body with no captcha -- spends ~20 Flow credits")
    a = ap.parse_args()

    with Page("tools/flow") as p:
        s = json.loads(p.evaluate(SESSION_JS, timeout=60))
    if s.get("error") or not s.get("token"):
        print(f"!! no Flow session token: {s.get('error') or 'access_token absent'}")
        return 1
    token = s["token"]
    print(f"Flow session : {s['email']}  (expires {s['expires']})")
    print(f"Target       : POST {SUBMIT}")
    print()

    # ---- Stage A: no captcha, empty prompt. Cannot generate anything, so it costs nothing.
    print("STAGE A -- no recaptchaContext, empty prompt (zero credits)")
    status, ctype, text = post(SUBMIT, token, build_body(""))
    kind = classify(text)
    print(f"  HTTP {status}  content-type={'JSON' if 'json' in ctype.lower() else ctype or '-'}")
    print(f"  verdict={kind}")
    print(f"  {scrub(text)[:600].replace(chr(10), ' ')}")
    print()

    if kind == "CAPTCHA":
        print("=" * 78)
        print("  reCAPTCHA IS ENFORCED. A pure HTTP shim cannot submit; the shim must mint a fresh")
        print("  Enterprise token per request via grecaptcha.enterprise.execute in a live page.")
        print("=" * 78)
        return 0
    if status == 200:
        print("  !! unexpected 200 on an empty prompt -- inspect the response above before going on.")
        return 0
    print("=" * 78)
    print("  The captcha gate did NOT stop this request -- Google validated the body instead.")
    print("  Re-run with --live to confirm a valid captcha-less body actually generates.")
    print("=" * 78)

    if not a.live:
        return 0

    # ---- Stage B: valid body, still no captcha. This one really generates and really costs.
    print()
    print("STAGE B -- valid body, no recaptchaContext (SPENDS ~20 CREDITS)")
    status, ctype, text = post(SUBMIT, token, build_body("a red kite over a wheat field at noon."))
    print(f"  HTTP {status}")
    if status != 200:
        print(f"  verdict={classify(text)}")
        print(f"  {scrub(text)[:600].replace(chr(10), ' ')}")
        return 0
    data = json.loads(text)
    media = (data.get("media") or [{}])[0]
    print(f"  remainingCredits : {data.get('remainingCredits')}")
    print(f"  mediaId          : {media.get('name')}")
    print(f"  status           : {media.get('mediaMetadata', {}).get('mediaStatus')}")
    print()
    print("  SERVER-SIDE SUBMIT WORKS WITH NO CAPTCHA. Poll it with:")
    print(f"    POST {POLL}")
    print(f'    {{"media":[{{"name":"{media.get("name")}","projectId":"{PROJECT_ID}"}}]}}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
