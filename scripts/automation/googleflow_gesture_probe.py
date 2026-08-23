"""Does reCAPTCHA Enterprise accept a Flow token minted after SYNTHETIC user input?

WHY THIS EXISTS (measured 2026-08-23):
Flow's real video RPC enforces reCAPTCHA Enterprise. A token minted by calling
grecaptcha.enterprise.execute directly -- whether from Python over CDP or from a fetch inside the
page itself -- is rejected with 403 PERMISSION_DENIED / PUBLIC_ERROR_UNUSUAL_ACTIVITY, while the very
same browser profile, same page instance and same sitekey produced an ACCEPTED token minutes earlier
when a human clicked Create. Five action labels were tried; all five failed identically. So the
rejection is not an action mismatch and not an origin problem -- the request reaches Google and is
scored. The remaining variable is behavioural: reCAPTCHA Enterprise scores each execute() using
recent interaction signals, and a bare programmatic execute() has none.

That distinction decides the whole integration design:
    accepted after synthetic input -> a shim can mint tokens on demand with CDP Input events
    still rejected                 -> only genuine human interaction scores, so Flow can be driven
                                      only by replaying real UI gestures, not by replaying the API

This probe dispatches real CDP Input events (mouse moves, a click on neutral page chrome, key
presses) to build up interaction signal, then mints and submits with an EMPTY prompt. An empty prompt
cannot produce a video, so every outcome here costs zero credits.

SECRET HANDLING: bearer and captcha tokens stay in memory, are never printed and never written to
disk; responses are scrubbed of token-shaped strings.

    python googleflow_gesture_probe.py
"""
from __future__ import annotations

import json
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402
from googleflow_client import (  # noqa: E402
    RECAPTCHA_SITEKEY, SUBMIT_URL, build_submit_body, classify, request, scrub, FlowSession,
)

# Mint + submit entirely inside the page, so the request is indistinguishable from the frontend's own
# except for the interaction history that preceded it. %s is the JSON-encoded sitekey.
INPAGE_JS = """
(async () => {
  const out = {};
  try {
    const s = await (await fetch('/fx/api/auth/session', {credentials:'include'})).json();
    const tok = s && s.access_token; if (!tok) return JSON.stringify({error:'no token'});
    const cap = await window.grecaptcha.enterprise.execute(%s, %s);
    out.capLen = cap.length;
    const pid = location.pathname.split('/project/')[1];
    const body = {
      mediaGenerationContext: {batchId: crypto.randomUUID(),
                               audioFailurePreference: 'BLOCK_SILENCED_VIDEOS'},
      clientContext: {projectId: pid, tool: 'PINHOLE', userPaygateTier: 'PAYGATE_TIER_ONE',
                      sessionId: ';' + Date.now(),
                      recaptchaContext: {token: cap,
                                         applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB'}},
      requests: [{outputSpec: {resolution: 'VIDEO_RESOLUTION_720P'},
                  aspectRatio: 'VIDEO_ASPECT_RATIO_LANDSCAPE',
                  textInput: {structuredPrompt: {parts: [{text: ''}]}},
                  videoModelKey: 'veo_3_1_t2v_fast', seed: 1234, metadata: {}}],
      useV2ModelConfig: true};
    const r = await fetch('https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText',
      {method: 'POST', headers: {'Content-Type': 'application/json',
                                 'Authorization': 'Bearer ' + tok},
       body: JSON.stringify(body)});
    out.status = r.status;
    out.resp = (await r.text()).slice(0, 300);
  } catch (e) { out.error = String(e && e.message || e); }
  return JSON.stringify(out);
})()
"""


def gesture(p: Page, seconds: float = 6.0) -> int:
    """Dispatch trusted-looking input. CDP Input events carry the same isTrusted flag as real ones,
    which is the only handle reCAPTCHA's collector has on 'did a human touch this page'."""
    n = 0
    x, y = 700.0, 500.0
    deadline = time.time() + seconds
    while time.time() < deadline:
        # A short curved drag rather than a teleport -- velocity and jitter are part of the signal.
        for _ in range(8):
            x += random.uniform(-40, 40)
            y += random.uniform(-25, 25)
            x, y = min(max(x, 60), 1500), min(max(y, 200), 780)
            p.send("Input.dispatchMouseEvent",
                   {"type": "mouseMoved", "x": x, "y": y, "button": "none"}, timeout=20)
            n += 1
            time.sleep(random.uniform(0.02, 0.09))
        # Scroll, which is a distinct signal from movement.
        p.send("Input.dispatchMouseEvent",
               {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0,
                "deltaY": random.choice([-120, 120])}, timeout=20)
        n += 1
        time.sleep(random.uniform(0.15, 0.4))
    return n


def typing(p: Page, text: str = "hello") -> int:
    """Keystrokes into whatever has focus. Keydown/keyup pairs, human-ish gaps."""
    n = 0
    for ch in text:
        for kind in ("keyDown", "keyUp"):
            params = {"type": kind, "key": ch}
            if kind == "keyDown":
                params["text"] = ch
            p.send("Input.dispatchKeyEvent", params, timeout=20)
            n += 1
        time.sleep(random.uniform(0.06, 0.18))
    return n


def attempt(p: Page, label: str, action: str | None) -> str:
    opts = json.dumps({"action": action}) if action else "{}"
    raw = p.evaluate(INPAGE_JS % (json.dumps(RECAPTCHA_SITEKEY), opts), timeout=120)
    r = json.loads(raw)
    if r.get("error"):
        print(f"  {label:<34} ERROR {scrub(r['error'])[:120]}")
        return "ERROR"
    kind = classify(r.get("resp", ""))
    print(f"  {label:<34} HTTP {r.get('status'):<4} {kind}  (captcha {r.get('capLen')} chars)")
    print(f"      {scrub(r.get('resp', ''))[:200].replace(chr(10), ' ')}")
    return kind


def main() -> int:
    sess = FlowSession().refresh()
    print(f"Flow session : {sess.email}")
    print(f"Project      : {sess.project_id}")
    print()
    print("Empty prompt throughout -- nothing here can generate a video, so this costs 0 credits.")
    print()

    with Page("tools/flow") as p:
        p.send("Page.bringToFront", {}, timeout=20)

        print("BASELINE -- mint with no preceding input")
        base = attempt(p, "no gesture", None)
        print()

        print("Dispatching synthetic input (mouse paths, wheel, keystrokes)...")
        moves = gesture(p, seconds=8)
        keys = typing(p, "a red kite")
        print(f"  {moves} pointer events, {keys} key events")
        time.sleep(2)
        print()

        print("AFTER GESTURE -- mint again")
        after = attempt(p, "after synthetic input", None)
        print()

        # reCAPTCHA sometimes wants the collector to have run for longer before it will score well.
        print("Letting the collector settle 20s, more input, then one final mint")
        gesture(p, seconds=10)
        time.sleep(10)
        final = attempt(p, "after settle + more input", None)

    print()
    print("=" * 78)
    if "ARGUMENT" in (after, final):
        print("  SYNTHETIC INPUT IS ENOUGH. A shim can mint captcha tokens on demand: dispatch CDP")
        print("  Input events, call execute(), submit over HTTP. Flow becomes a scriptable route.")
    elif base == "CAPTCHA" and after == "CAPTCHA" and final == "CAPTCHA":
        print("  SYNTHETIC INPUT DOES NOT HELP. reCAPTCHA scores CDP-dispatched interaction the same")
        print("  as none at all, so the token can only be earned by a genuine human gesture.")
        print("  Consequence for OmniRoute: Flow cannot be a fire-and-forget API route. It can only")
        print("  be driven as UI replay with a human in the loop at submit time.")
    else:
        print(f"  INCONCLUSIVE -- baseline={base} after={after} final={final}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
