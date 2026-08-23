"""Is Flow's reCAPTCHA rejection a SCORE problem or an ACTION-LABEL problem?

WHY THIS EXISTS (measured 2026-08-23):
Flow's video RPC answers 403 PUBLIC_ERROR_UNUSUAL_ACTIVITY for every token this project mints, while
a human clicking Create in the same tab, same sitekey, same bearer, produced an accepted one. Two
explanations survive and they lead to opposite conclusions:

    SCORE  -- reCAPTCHA Enterprise scores programmatic execute() as automation. Then no amount of
              scripting fixes it and a human gesture is required per generation.
    ACTION -- the backend's assessment expects a specific action label. Then the label is all that is
              missing and Flow becomes fully scriptable.

Guessing labels cannot separate these: a wrong guess and a bad score fail identically, which is
exactly what five guesses produced. So this script takes the label from the frontend itself.

HOW, WITHOUT SPENDING CREDITS:
`arm` wraps grecaptcha.enterprise.execute to record the sitekey and options the frontend passes, and
wraps fetch so that the submit to batchAsyncGenerateVideoText is CAPTURED AND BLOCKED -- the request
never leaves the browser, so Google never sees it and no credits are spent. The operator clicks
Create once; the click is genuine, so the token it mints is a high-score token with the real action.
`verify` then replays that human-minted token from Python with an EMPTY prompt:

    ARGUMENT error -> the token is good and was the missing piece; the frontend's own action label is
                      printed, and whether a human click is needed per token is now the only question
    CAPTCHA error  -> even a human-minted token fails once we send it, so the binding is to something
                      beyond token+action and API replay is a dead end

SECRET HANDLING: tokens stay in the page and in memory. Nothing token-shaped is printed or written to
disk; only lengths, action labels and scrubbed error text are shown.

    python googleflow_click_capture.py arm      # install hooks, then click Create in the tab
    python googleflow_click_capture.py verify    # replay the human-minted token, 0 credits
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402
from googleflow_client import SUBMIT_URL, build_submit_body, classify, request, scrub, FlowSession  # noqa: E402

ARM_JS = r"""
(() => {
  const S = (window.__ORFLOW = window.__ORFLOW || {mints: [], submits: [], blocked: 0});

  // ---- wrap the captcha mint so we learn the sitekey and the action label the frontend uses
  if (!S.mintHooked) {
    const g = window.grecaptcha && window.grecaptcha.enterprise;
    if (!g || typeof g.execute !== 'function') return JSON.stringify({error: 'grecaptcha.enterprise absent'});
    const orig = g.execute.bind(g);
    g.execute = async function (key, opts) {
      const tok = await orig(key, opts);
      try {
        S.mints.push({t: Date.now(), key: key, opts: JSON.parse(JSON.stringify(opts || {})),
                      token: tok, len: (tok || '').length});
      } catch (e) {}
      return tok;
    };
    S.mintHooked = true;
  }

  // ---- wrap fetch so the generate submit is captured and NEVER SENT (zero credits)
  if (!S.fetchHooked) {
    const of = window.fetch;
    window.fetch = async function (input, init) {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (/batchAsyncGenerateVideoText/.test(url)) {
        let body = null;
        try { body = (init && init.body) || (input && input.body) || null; } catch (e) {}
        let auth = null;
        try {
          const h = new Headers((init && init.headers) || (input && input.headers) || {});
          auth = h.get('authorization') ? 'present' : 'absent';
        } catch (e) {}
        S.submits.push({t: Date.now(), url: url, auth: auth,
                        body: typeof body === 'string' ? body : String(body)});
        S.blocked++;
        // Answer the frontend ourselves. It shows an error; Google is never contacted.
        return new Response(JSON.stringify({error: {code: 499, status: 'BLOCKED_BY_LOCAL_PROBE',
                            message: 'captured locally, not sent'}}),
                            {status: 499, headers: {'Content-Type': 'application/json'}});
      }
      return of.apply(this, arguments);
    };
    S.fetchHooked = true;
  }

  // ---- and the same guard on XHR. The frontend uses fetch today, but a single missed transport
  // here means a real submit reaches Google and burns ~20 credits, so both doors get locked.
  if (!S.xhrHooked) {
    const oo = XMLHttpRequest.prototype.open;
    const os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) {
      this.__orUrl = String(u || '');
      if (/batchAsyncGenerateVideoText/.test(this.__orUrl)) {
        this.__orBlocked = true;
        // Point it somewhere inert on our own origin. Google is never contacted.
        arguments[1] = '/fx/__blocked_by_or_probe';
      }
      return oo.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (b) {
      if (this.__orBlocked) {
        S.submits.push({t: Date.now(), url: this.__orUrl, auth: 'xhr',
                        body: typeof b === 'string' ? b : String(b)});
        S.blocked++;
      }
      return os.apply(this, arguments);
    };
    S.xhrHooked = true;
  }
  return JSON.stringify({armed: true, mints: S.mints.length, submits: S.submits.length,
                         blocked: S.blocked});
})()
"""

# Prove the guard works before a human is asked to click. Both transports are aimed at the submit
# URL with a body that would be REJECTED anyway (empty prompt, no captcha) -- so even a total failure
# of the block cannot generate anything. What we are checking is that Google is never reached at all.
SELFTEST_JS = r"""
(async () => {
  const S = window.__ORFLOW;
  if (!S) return JSON.stringify({error: 'not armed'});
  const U = 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText';
  const before = S.blocked;
  const out = {};
  try {
    const r = await fetch(U, {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({probe: 'selftest'})});
    out.fetchStatus = r.status;
    out.fetchBody = (await r.text()).slice(0, 120);
  } catch (e) { out.fetchError = String(e && e.message || e); }
  await new Promise(res => {
    const x = new XMLHttpRequest();
    x.open('POST', U);
    x.onloadend = () => { out.xhrStatus = x.status; out.xhrUrl = x.responseURL || null; res(); };
    x.onerror = () => { out.xhrError = 'error'; res(); };
    try { x.send(JSON.stringify({probe: 'selftest'})); } catch (e) { out.xhrError = String(e); res(); }
  });
  out.blockedDelta = S.blocked - before;
  return JSON.stringify(out);
})()
"""

READ_JS = r"""
(() => {
  const S = window.__ORFLOW;
  if (!S) return JSON.stringify({error: 'not armed'});
  const last = S.mints[S.mints.length - 1] || null;
  const sub = S.submits[S.submits.length - 1] || null;
  let promptText = null, model = null, action = null;
  if (sub && sub.body) {
    try {
      const b = JSON.parse(sub.body);
      promptText = b.requests?.[0]?.textInput?.structuredPrompt?.parts?.[0]?.text ?? null;
      model = b.requests?.[0]?.videoModelKey ?? null;
      action = 'in-body captcha len ' + (b.clientContext?.recaptchaContext?.token || '').length;
    } catch (e) {}
  }
  return JSON.stringify({
    mints: S.mints.length, submits: S.submits.length, blocked: S.blocked,
    lastMint: last ? {key: last.key, opts: last.opts, len: last.len} : null,
    lastSubmit: sub ? {auth: sub.auth, prompt: promptText, model: model, note: action} : null,
  });
})()
"""

# Hand the frontend's own blocked submit body to Python without ever printing it. Preferred over the
# mint hook: this is verbatim what Flow was about to send, so replaying it with only the prompt
# emptied changes exactly one variable. Falls back to the mint hook if the body was not captured
# (e.g. the frontend held a reference to execute() taken before we wrapped it).
TAKE_JS = r"""
(() => {
  const S = window.__ORFLOW;
  if (!S) return JSON.stringify({error: 'not armed'});
  const sub = S.submits.filter(s => s.body && s.body.indexOf('recaptchaContext') !== -1).pop();
  if (sub) {
    try {
      const b = JSON.parse(sub.body);
      return JSON.stringify({source: 'blocked submit body', body: b, age: Date.now() - sub.t});
    } catch (e) {}
  }
  const m = S.mints[S.mints.length - 1];
  if (m) return JSON.stringify({source: 'mint hook', token: m.token, opts: m.opts,
                                age: Date.now() - m.t});
  return JSON.stringify({error: 'no frontend captcha captured -- click Create in the Flow tab'});
})()
"""


def cmd_arm(a) -> int:
    with Page("tools/flow") as p:
        r = json.loads(p.evaluate(ARM_JS, timeout=60))
        if r.get("error"):
            print(f"!! {r['error']}")
            return 1
        print("Hooks installed:")
        print("  - grecaptcha.enterprise.execute  -> records sitekey + action, passes the token through")
        print("  - fetch(batchAsyncGenerateVideoText) -> CAPTURED AND BLOCKED, never reaches Google")
        print("  - XMLHttpRequest to the same path  -> redirected to an inert same-origin path")
        print()
        print("Self-testing the guard (both transports, bodies that could not generate anyway)...")
        t = json.loads(p.evaluate(SELFTEST_JS, timeout=90))

    if t.get("error"):
        print(f"!! selftest: {t['error']}")
        return 1
    fetch_ok = t.get("fetchStatus") == 499
    xhr_ok = t.get("xhrStatus") in (0, 404) or "__blocked_by_or_probe" in str(t.get("xhrUrl") or "")
    print(f"  fetch -> HTTP {t.get('fetchStatus')} {scrub(t.get('fetchBody', ''))[:60]}"
          f"   {'BLOCKED' if fetch_ok else 'NOT BLOCKED'}")
    print(f"  xhr   -> HTTP {t.get('xhrStatus')} url={str(t.get('xhrUrl'))[-40:]}"
          f"   {'BLOCKED' if xhr_ok else 'NOT BLOCKED'}")
    print(f"  guard counted {t.get('blockedDelta')} blocked submit(s)")
    print()
    if not (fetch_ok and xhr_ok):
        print("=" * 78)
        print("  GUARD NOT PROVEN. Do NOT click Create -- a real submit could reach Google and spend")
        print("  credits. Fix the hook first.")
        print("=" * 78)
        return 1
    print("=" * 78)
    print("  GUARD PROVEN on both transports. Nothing aimed at the generate RPC can leave the tab.")
    print("=" * 78)
    print()
    print("Now, in the Flow tab: type any prompt and click the Create arrow ONCE.")
    print("Flow will show an error. That error IS this probe blocking the request -- expected, and it")
    print("means zero credits were spent. Then run:")
    print("    python googleflow_click_capture.py verify")
    return 0


def cmd_verify(a) -> int:
    with Page("tools/flow") as p:
        info = json.loads(p.evaluate(READ_JS, timeout=60))
        if info.get("error"):
            print(f"!! {info['error']} -- run `arm` first")
            return 1
        print(f"mints={info['mints']}  submits={info['submits']}  blocked={info['blocked']}")
        if info.get("lastMint"):
            m = info["lastMint"]
            print(f"frontend minted with sitekey={m['key']}  opts={json.dumps(m['opts'])}  "
                  f"token {m['len']} chars")
        if info.get("lastSubmit"):
            s = info["lastSubmit"]
            print(f"blocked submit: auth={s['auth']}  model={s['model']}  prompt={s['prompt']!r}")
        taken = json.loads(p.evaluate(TAKE_JS, timeout=60))

    if taken.get("error"):
        print()
        print(f"!! {taken['error']}")
        return 1
    print(f"source: {taken['source']}   age {taken['age'] / 1000:.0f}s")
    print()

    sess = FlowSession().refresh()
    if not sess.project_id:
        print("!! no projectId in the tab url")
        return 1

    if taken["source"] == "blocked submit body":
        # Replay Flow's own body verbatim, with the prompt emptied so nothing can generate.
        body = taken["body"]
        try:
            body["requests"][0]["textInput"]["structuredPrompt"]["parts"] = [{"text": ""}]
        except Exception:
            print("!! captured body has an unexpected shape; not replaying")
            return 1
        body["mediaGenerationContext"]["batchId"] = str(uuid.uuid4())
        cap_len = len(body.get("clientContext", {}).get("recaptchaContext", {}).get("token", ""))
        print(f"Replaying Flow's OWN body verbatim, prompt emptied (captcha {cap_len} chars, "
              f"0 credits)...")
    else:
        body = build_submit_body("", taken["token"], sess.project_id)
        print("Replaying the mint-hook token in our own body, empty prompt (0 credits)...")

    status, text = request(SUBMIT_URL, sess.token, body)
    kind = classify(text)
    print(f"  HTTP {status}  {kind}")
    print(f"  {scrub(text)[:400].replace(chr(10), ' ')}")
    print()
    print("=" * 78)
    if kind == "ARGUMENT":
        print("  A HUMAN-MINTED TOKEN IS ACCEPTED FROM PYTHON. The blocker is the SCORE, not the")
        print("  transport: Flow can be driven server-side, but each submit needs a token earned by a")
        print("  real gesture. Design follows: one human click mints, the shim spends it.")
    elif kind == "CAPTCHA":
        print("  EVEN FLOW'S OWN BODY FAILS WHEN WE SEND IT. Same bytes, same captcha, only the")
        print("  sender changed -- so the assessment binds to the browser request itself, not just to")
        print("  token+action. Replaying the API is a dead end; Flow can only be driven via its UI.")
    else:
        print(f"  INCONCLUSIVE: {kind}. Read the response above before concluding.")
    print("=" * 78)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("arm").set_defaults(fn=cmd_arm)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    try:
        return a.fn(a)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {scrub(str(exc))[:400]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
