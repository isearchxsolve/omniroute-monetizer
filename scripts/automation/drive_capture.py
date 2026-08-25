"""drive_capture.py -- hand-driven CDP primitives for the universal-replay harvest.

Unlike autonomous_harvester.py (which hands a static element dump to a rigid LLM
prompt and fumbles), these are dumb, observable primitives. The judgement -- which
button is "Continue with Google", which box is the chat input -- is supplied by the
operator/agent between calls, one step at a time.

The capture step is the part that was missing/broken: it grabs the GENUINE request
by matching the one whose POST body contains the injected SENTINEL, then fetches the
body (inline or via Network.getRequestPostData) AND the cookie jar (Network.getCookies),
and writes state/secrets/session_<host>.json in the exact schema universal_replay wants:

    { host, modality, sentinel,
      recorded_exchange: { url, method, request_headers, request_body },
      cookie_header }

Safety: never types a password, never touches a captcha/paywall. Cookie values and
request bodies are written to the gitignored secrets file ONLY -- stdout gets shapes,
lengths, and header KEYS, never values.

    python drive_capture.py els     --match HOST                 # dump interactive elements (I read)
    python drive_capture.py state   --match HOST                 # login / captcha / paywall hints
    python drive_capture.py open    <url>                        # open a new tab
    python drive_capture.py click   --match HOST --id N          # click element data-dc=N
    python drive_capture.py type    --match HOST --id N --text T # type into element N (no submit)
    python drive_capture.py capture --match HOST --input-id A (--submit-id B | --enter) [--sentinel S]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
import time
import urllib.request
from urllib.parse import urlsplit

import websocket  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402

# Windows consoles default to cp1252; provider UIs are full of em-dashes/emoji.
# Never let a print() crash the driver mid-harvest.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_PORT = 9222
SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
SENTINEL = "Reply exactly one word: Omni."

_DROP_HDR = {"cookie", "content-length", "host", "accept-encoding", "connection"}
_WALL_WORDS = ("captcha", "verify you are human", "cloudflare", "are you a robot",
               "enter your card", "payment method", "add a card", "credit card",
               "upgrade to", "subscribe", "start free trial", "out of credits",
               "verification code", "enter the code", "phone number")


def host_slug(url: str) -> str:
    h = (urlsplit(url).hostname or "unknown").lower()
    return "session_" + h.replace(".", "_") + ".json"


# ---- element dump: tags data-dc=N onto each interactive, visible element -----------
JS_ELS = r"""
(() => {
  let out = [], n = 0;
  const sel = 'a,button,input,textarea,select,[role=button],[role=textbox],[contenteditable=true]';
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    const txt = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
    const isInput = el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable
                    || el.getAttribute('role') === 'textbox';
    const isBtn = el.tagName === 'BUTTON' || el.getAttribute('role') === 'button'
                  || (el.tagName === 'INPUT' && ['submit', 'button', 'image'].includes(el.type));
    let label = txt;
    if (!label && (isBtn || el.tagName === 'A')) {
      const g = el.querySelector('svg,img');
      label = g ? (g.getAttribute('aria-label') || g.getAttribute('alt') || '<icon>') : '<icon>';
    }
    if (!label && !isInput) continue;
    el.setAttribute('data-dc', n);
    out.push({i: n, tag: el.tagName.toLowerCase(), type: (el.type || ''),
              role: (el.getAttribute('role') || ''), ce: !!el.isContentEditable,
              text: label.slice(0, 90).replace(/\s+/g, ' ')});
    n++;
  }
  return out;
})()
"""

JS_INJECT = r"""
(() => {
  const val = __VAL__, inSel = __INSEL__, btnSel = __BTNSEL__;
  const input = document.querySelector(inSel);
  if (!input) return 'NO_INPUT';
  input.focus();
  if (input.isContentEditable) {
    input.textContent = val;
    input.dispatchEvent(new InputEvent('input', {bubbles: true, data: val, inputType: 'insertText'}));
  } else {
    const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                                               : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(input, val);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  if (btnSel) {
    const btn = document.querySelector(btnSel);
    if (!btn) return 'BTN_NOT_FOUND';
    btn.scrollIntoView({block: 'center'});
    btn.click();
    return 'CLICKED_BTN';
  }
  for (const t of ['keydown', 'keyup']) {
    input.dispatchEvent(new KeyboardEvent(t, {bubbles: true, key: 'Enter', code: 'Enter',
                                              keyCode: 13, which: 13}));
  }
  return 'ENTER';
})()
"""


def _open_tab(url: str, port: int) -> str:
    for method in ("PUT", "GET"):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method=method)
            res = json.loads(urllib.request.urlopen(req, timeout=15).read())
            return res.get("id", "")
        except Exception as e:
            last = e
    raise SystemExit(f"open failed: {last}")


def cmd_els(a) -> int:
    with Page(a.match, port=a.port) as p:
        els = p.evaluate(JS_ELS) or []
    for e in els:
        flag = "IN" if (e["tag"] in ("textarea",) or e["ce"] or e["role"] == "textbox"
                        or (e["tag"] == "input" and e["type"] in ("", "text", "search"))) else "  "
        print(f'  [{e["i"]:>3}] {flag} {e["tag"]:<9}{("/" + e["type"]) if e["type"] else "":<9} '
              f'{e["text"]}')
    print(f"--- {len(els)} elements (IN = likely text input)")
    return 0


def cmd_state(a) -> int:
    with Page(a.match, port=a.port) as p:
        txt = (p.evaluate("document.body ? document.body.innerText : ''") or "").lower()
        has_in = p.evaluate("!!document.querySelector('textarea,[contenteditable=true],"
                            "input[type=text],[role=textbox]')")
        url = p.evaluate("location.href")
    walls = sorted({w for w in _WALL_WORDS if w in txt})
    login = any(s in txt for s in ("sign in", "log in", "sign up", "continue with google"))
    print(f"  url={url[:80]}")
    print(f"  has_text_input={has_in}  login_words={login}")
    print(f"  WALL_HINTS={walls if walls else 'none'}")
    return 0


def cmd_click(a) -> int:
    js = ("(() => { const el = document.querySelector('[data-dc=\"%d\"]'); if (!el) return 'NOT_FOUND'; "
          "el.scrollIntoView({block:'center'}); el.click(); return 'CLICKED: ' + "
          "(el.innerText||el.value||el.getAttribute('aria-label')||el.tagName).slice(0,60); })()" % a.id)
    with Page(a.match, port=a.port) as p:
        print(p.evaluate(js))
        time.sleep(a.after)
        print("now at:", p.evaluate("location.href"))
    return 0


def cmd_type(a) -> int:
    js = (JS_INJECT.replace("__VAL__", json.dumps(a.text))
          .replace("__INSEL__", json.dumps(f'[data-dc="{a.id}"]'))
          .replace("__BTNSEL__", "null"))
    # strip the Enter dispatch for a pure type: reuse inject but with no submit is 'ENTER';
    # for type-only we still want no submit, so swap the trailing return path:
    js = js.replace("input.dispatchEvent(new KeyboardEvent(t,", "0 && input.dispatchEvent(new KeyboardEvent(t,")
    js = js.replace("return 'ENTER';", "return 'TYPED';")
    with Page(a.match, port=a.port) as p:
        print(p.evaluate(js))
    return 0


def _get_post_data(p: Page, rid: str) -> str | None:
    try:
        r = p.send("Network.getRequestPostData", {"requestId": rid}, timeout=10)
        return r.get("postData")
    except Exception:
        return None


def _genuine_insert(p: Page, in_sel: str, val: str) -> str:
    """Type via CDP Input.insertText -- the only way that works on framework-controlled
    contenteditable editors (Lexical/Slate/ProseMirror). Setting .textContent makes the
    text appear visually while the editor's internal model stays empty, so the send
    button no-ops and we capture zero POSTs. Returns the text read back from the DOM."""
    ok = p.evaluate("(() => { const i = document.querySelector(%s); if (!i) return false; "
                    "i.focus(); if (i.isContentEditable) { i.textContent = ''; } "
                    "else { i.value = ''; } return true; })()" % json.dumps(in_sel))
    if not ok:
        return "NO_INPUT"
    time.sleep(0.25)
    p.send("Input.insertText", {"text": val})
    time.sleep(0.4)
    return p.evaluate("(() => { const i = document.querySelector(%s); "
                      "return i ? (i.value || i.innerText || i.textContent || '') : ''; })()"
                      % json.dumps(in_sel)) or ""


def _genuine_enter(p: Page) -> None:
    """Real Enter keypress. Synthetic `new KeyboardEvent` has isTrusted=false and most
    editors ignore it for submit; dispatchKeyEvent is delivered as a trusted event."""
    for ev in (
        {"type": "rawKeyDown", "key": "Enter", "code": "Enter",
         "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
        {"type": "char", "text": "\r", "key": "Enter", "code": "Enter",
         "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
        {"type": "keyUp", "key": "Enter", "code": "Enter",
         "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
    ):
        try:
            p.send("Input.dispatchKeyEvent", ev)
        except Exception:
            pass
        time.sleep(0.05)


def cmd_capture(a) -> int:
    sentinel = a.sentinel
    in_sel = f'[data-dc="{a.input_id}"]'
    btn_sel = f'[data-dc="{a.submit_id}"]' if a.submit_id is not None else None
    with Page(a.match, port=a.port, timeout=90) as p:
        p.send("Network.enable")
        # drain buffered events
        p.ws.settimeout(0.3)
        while True:
            try:
                p.ws.recv()
            except Exception:
                break
        inj = (JS_INJECT.replace("__VAL__", json.dumps(sentinel))
               .replace("__INSEL__", json.dumps(in_sel))
               .replace("__BTNSEL__", json.dumps(btn_sel) if btn_sel else "null"))
        verb = p.evaluate(inj)
        print(f"  inject -> {verb}")
        if verb in ("NO_INPUT", "BTN_NOT_FOUND"):
            print("  !! aborting capture: element not found (re-run `els`).")
            return 1

        reqs: dict[str, dict] = {}
        order: list[str] = []
        hit = None
        deadline = time.time() + a.wait
        while time.time() < deadline and hit is None:
            p.ws.settimeout(min(1.0, max(0.1, deadline - time.time())))
            try:
                msg = json.loads(p.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            if msg.get("method") != "Network.requestWillBeSent":
                continue
            pr = msg["params"]
            r = pr["request"]
            if r.get("method") != "POST" or not str(r.get("url", "")).startswith("http"):
                continue
            rid = pr["requestId"]
            pd = r.get("postData")
            reqs[rid] = {"url": r["url"], "method": r["method"], "headers": r.get("headers", {}),
                         "postData": pd, "has": r.get("hasPostData", bool(pd))}
            order.append(rid)
            if pd and sentinel in pd:
                hit = rid

        # recover bodies not delivered inline
        if hit is None:
            for rid in order:
                if reqs[rid]["postData"] is None and reqs[rid]["has"]:
                    pd = _get_post_data(p, rid)
                    if pd:
                        reqs[rid]["postData"] = pd
                        if sentinel in pd:
                            hit = rid
                            break

        if hit is None:
            print(f"  !! sentinel not found in any of {len(order)} POST bodies.")
            for rid in order[:12]:
                print(f"     candidate POST {urlsplit(reqs[rid]['url']).path[:60]} "
                      f"body={'inline' if reqs[rid]['postData'] else ('lazy' if reqs[rid]['has'] else 'none')}")
            return 1

        ex = reqs[hit]
        body = ex["postData"]
        # cookie jar for the exact URL (httpOnly included) -> cookie_header
        try:
            cj = p.send("Network.getCookies", {"urls": [ex["url"]]}, timeout=10).get("cookies", [])
        except Exception:
            cj = []
        cookie_header = "; ".join(f'{c["name"]}={c["value"]}' for c in cj)
        headers = {k: v for k, v in ex["headers"].items()
                   if not k.startswith(":") and k.lower() not in _DROP_HDR}

    host = urlsplit(ex["url"]).hostname or a.match
    doc = {
        "host": host,
        "captured_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "modality": a.modality,
        "sentinel": sentinel,
        "recorded_exchange": {
            "url": ex["url"], "method": ex["method"],
            "request_headers": headers, "request_body": body,
        },
        "cookie_header": cookie_header,
    }
    SECRETS.mkdir(parents=True, exist_ok=True)
    out = SECRETS / host_slug(ex["url"])
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [+] SAVED {out.name}")
    print(f"      url_path={urlsplit(ex['url']).path[:70]}  method={ex['method']}")
    print(f"      body_len={len(body)}  sentinel_in_body=YES  header_keys={sorted(headers)}")
    print(f"      cookies={len(cj)}  cookie_header_len={len(cookie_header)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("els"); e.add_argument("--match", default=""); e.set_defaults(fn=cmd_els)
    s = sub.add_parser("state"); s.add_argument("--match", default=""); s.set_defaults(fn=cmd_state)
    o = sub.add_parser("open"); o.add_argument("url"); o.set_defaults(fn=lambda a: (print(_open_tab(a.url, a.port)), 0)[1])
    c = sub.add_parser("click"); c.add_argument("--match", default=""); c.add_argument("--id", type=int, required=True)
    c.add_argument("--after", type=float, default=3.0); c.set_defaults(fn=cmd_click)
    t = sub.add_parser("type"); t.add_argument("--match", default=""); t.add_argument("--id", type=int, required=True)
    t.add_argument("--text", required=True); t.set_defaults(fn=cmd_type)
    cap = sub.add_parser("capture"); cap.add_argument("--match", default="")
    cap.add_argument("--input-id", dest="input_id", type=int, required=True)
    cap.add_argument("--submit-id", dest="submit_id", type=int, default=None)
    cap.add_argument("--enter", action="store_true")
    cap.add_argument("--sentinel", default=SENTINEL)
    cap.add_argument("--modality", default="chat")
    cap.add_argument("--wait", type=int, default=25)
    cap.set_defaults(fn=cmd_capture)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {str(exc)[:400]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
