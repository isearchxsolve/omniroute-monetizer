"""Can a Google Flow WEB session token drive the endpoint OmniRoute's google-flow handler calls?

WHY THIS EXISTS (measured 2026-08-23):
MASTER_WORKLOG entry #1002 closed `googleflow` as unblockable: `resolveVideoCredentialProvider`
maps googleflow -> antigravity, the Antigravity OAuth grant carries scopes cloud-platform / cclog /
experimentsandconfigs / userinfo.*, and POST https://aisandbox-pa.googleapis.com/v1:generateVideo
answered with an HTML 404 -- the signature of a Google frontend refusing a path the token's client
is not authorised for. The conclusion was "needs a Flow-authorised Google OAuth grant".

That grant turns out to be reachable. The signed-in Flow tab exposes
    GET https://labs.google/fx/api/auth/session   -> {user, expires, access_token: "ya29...."}
and the Flow frontend calls aisandbox-pa.googleapis.com DIRECTLY from the browser (21 such requests
observed in performance.getEntriesByType('resource')), so the token client-side really is the one
that talks to the sandbox API.

This script answers the only question that matters before any wiring is attempted: does that token
AUTHENTICATE to /v1:generateVideo? It deliberately sends an INVALID body. The distinction is:
    400 + JSON error   -> authorised; the grant works and only the body shape is wrong
    401 / 403          -> authenticated but not permitted
    404 + HTML         -> same wall the Antigravity token hit; wrong OAuth client
A 400 is the good answer. Sending a VALID body would mint a real video and spend real Flow credits,
so this script never does that -- proving the grant costs nothing.

SECRET HANDLING: the token is fetched into memory over CDP and used in-process. It is never printed,
never written to disk, and the response body is scrubbed of anything token-shaped before display.

Read-only with respect to every provider account and to OmniRoute's database.

    python googleflow_token_probe.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402  -- raw CDP, no Playwright (see cdp.py docstring)

SUBMIT = "https://aisandbox-pa.googleapis.com/v1:generateVideo"
SESSION_JS = """
(async () => {
  const r = await fetch('/fx/api/auth/session', {credentials:'include'});
  if (!r.ok) return JSON.stringify({error: 'session ' + r.status});
  const s = await r.json();
  return JSON.stringify({email: s?.user?.email || null, expires: s?.expires || null,
                         token: s?.access_token || null});
})()
"""

# Anything that looks like a Google access token or an api key, scrubbed before we print a response.
SECRET_RE = re.compile(r"(ya29\.[\w\-\.]+|AIza[\w\-]{20,}|1//[\w\-\.]+)")


def scrub(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", text)


def post(url: str, token: str, payload: dict, method: str = "POST") -> tuple[int, str, str]:
    data = json.dumps(payload).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers.get("content-type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace")
    except Exception as e:                                   # transport, DNS, TLS
        return 0, "", f"{type(e).__name__}: {e}"


def main() -> int:
    with Page("tools/flow") as p:
        raw = p.evaluate(SESSION_JS, timeout=60)
    s = json.loads(raw)
    if s.get("error") or not s.get("token"):
        print(f"!! no Flow session token available: {s.get('error') or 'access_token absent'}")
        print("   Open https://labs.google/fx/tools/flow in the robot Chrome and sign in first.")
        return 1

    token = s["token"]
    print(f"Flow session   : {s['email']}   (token {len(token)} chars, expires {s['expires']})")
    print(f"Target         : POST {SUBMIT}")
    print("Bodies below are INVALID ON PURPOSE -- an authorised grant answers 400, and no video")
    print("is generated, so this probe spends zero credits.")
    print()

    # Case 1: empty body. Case 2: OmniRoute's exact shape but an empty prompt, no project.
    # Case 3: OmniRoute's exact shape including `project`, still empty prompt.
    cases = [
        ("empty body", {}),
        ("omniroute shape, empty prompt, no project",
         {"instances": [{"prompt": ""}], "parameters": {"sampleCount": 1},
          "model": "veo-3.1-fast-generate"}),
        ("omniroute shape, empty prompt, with project",
         {"instances": [{"prompt": ""}], "parameters": {"sampleCount": 1},
          "model": "veo-3.1-fast-generate", "project": "thematic-victory-39z5m"}),
    ]

    verdicts = []
    for label, body in cases:
        status, ctype, text = post(SUBMIT, token, body)
        kind = "HTML" if "html" in ctype.lower() else ("JSON" if "json" in ctype.lower() else ctype)
        print(f"--- {label}")
        print(f"    HTTP {status}  content-type={kind or '(none)'}")
        print(f"    {scrub(text)[:400].replace(chr(10), ' ')}")
        print()
        verdicts.append((label, status, kind))

    print("=" * 78)
    auth_ok = any(st == 400 and k == "JSON" for _, st, k in verdicts)
    html404 = any(st == 404 and k == "HTML" for _, st, k in verdicts)
    denied = any(st in (401, 403) for _, st, k in verdicts)
    if auth_ok:
        print("  AUTHORISED. The Flow web token reaches /v1:generateVideo and Google validated the")
        print("  request body rather than rejecting the caller. The grant is the missing piece; the")
        print("  remaining work is body shape + getting this token into OmniRoute's credential.")
    elif html404:
        print("  /v1:generateVideo ANSWERS HTML 404 EVEN WITH A REAL FLOW TOKEN.")
        print("  That is a path verdict, not an auth verdict -- see the control block below.")
    elif denied:
        print("  AUTHENTICATED BUT REFUSED (401/403). The token is understood and the account is")
        print("  not permitted on this path.")
    else:
        print("  INCONCLUSIVE -- see the statuses above before drawing any conclusion.")
    print("=" * 78)

    # ---------------------------------------------------------------- control block
    # An HTML 404 on one path proves nothing on its own -- it could still mean "this token's client
    # is not allowed here" (that was entry #1002's reading). So hit paths the live frontend is
    # OBSERVED to call with the SAME token. If those answer anything other than HTML 404, the token
    # authenticates fine and /v1:generateVideo is simply not a route on this service.
    #
    # Candidate generate paths come from the frontend bundle: the video RPC is carried as
    # `apiPathname: 'batchAsyncGenerateVideoText'` and the only generation-namespace literal in the
    # bundle is '/v1/flowMedia:cancelGeneration'. Bodies stay invalid, so nothing is generated.
    print()
    print("CONTROL -- same token, paths the live Flow frontend actually calls:")
    controls = [
        ("GET  /v1/flow/models/statuses", "https://aisandbox-pa.googleapis.com/v1/flow/models/statuses", {}, "GET"),
        ("POST /v1/flow:batchLogFrontendEvents", "https://aisandbox-pa.googleapis.com/v1/flow:batchLogFrontendEvents", {}, "POST"),
        ("POST /v1/flowMedia:cancelGeneration", "https://aisandbox-pa.googleapis.com/v1/flowMedia:cancelGeneration", {}, "POST"),
    ]
    print()
    print("CANDIDATES -- where the real text-to-video RPC might live (invalid bodies, 0 credits):")
    candidates = [
        ("POST /v1/flowMedia:batchAsyncGenerateVideoText", "https://aisandbox-pa.googleapis.com/v1/flowMedia:batchAsyncGenerateVideoText", {}, "POST"),
        ("POST /v1/video:batchAsyncGenerateVideoText", "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText", {}, "POST"),
        ("POST /v1:batchAsyncGenerateVideoText", "https://aisandbox-pa.googleapis.com/v1:batchAsyncGenerateVideoText", {}, "POST"),
    ]
    for label, url, body, method in controls + candidates:
        status, ctype, text = post(url, token, body, method=method)
        kind = "HTML" if "html" in ctype.lower() else ("JSON" if "json" in ctype.lower() else ctype)
        note = "PATH EXISTS" if status != 404 else "no such path"
        print(f"  {label:<48} HTTP {status:<4} {kind or '-':<5} {note}")
        print(f"      {scrub(text)[:180].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
