"""cdp.py -- talk to the already-running robot Chrome over RAW Chrome DevTools Protocol.

WHY THIS EXISTS (measured 2026-08-23):
drive.py drives Chrome through Playwright's connect_over_cdp. That attaches to EVERY target in the
browser, and it has now wedged twice on heavy pages -- the websocket connects and then dies with
"Timeout 20000ms exceeded" plus a flood of `socket.send() raised exception`. Meanwhile plain HTTP to
http://127.0.0.1:9222/json/list answered instantly and correctly, proving Chrome itself was healthy
and only Playwright's all-target attach was the problem.

The blunt fix would be to kill Chrome. That is exactly the wrong move here: this profile holds the
Google session that came back on its own via one-tap, and the operator is watching the window. So
this module attaches to ONE page target and speaks CDP directly -- no Playwright, no all-target
enumeration, nothing to wedge, and nothing killed.

Deliberately read-mostly. It can navigate and click, because those are needed to reach an API-key
page, but it never types a password and never touches a CAPTCHA or a payment form.

    python cdp.py url                       # which page are we on
    python cdp.py text [--grep X] [--max N] # visible text of the page
    python cdp.py eval "<js>"               # evaluate an expression, print the value
    python cdp.py nav <url>                 # navigate and wait for the URL to settle
    python cdp.py shot <tag>                # png into state/harvest/shots/
    python cdp.py click "<visible text>"    # click the first element whose text matches
    python cdp.py targets                   # list every page target
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.request

import websocket  # websocket-client 1.9.0, already in the venv

DEVTOOLS = "http://127.0.0.1:9222"
SHOTS = pathlib.Path(r"D:\omniroute-monetizer\state\harvest\shots")


def list_targets() -> list[dict]:
    raw = urllib.request.urlopen(f"{DEVTOOLS}/json/list", timeout=20).read()
    return json.loads(raw)


def pick_page(match: str = "") -> dict:
    pages = [t for t in list_targets() if t.get("type") == "page"]
    if not pages:
        raise SystemExit("no page targets; is the robot Chrome running with --remote-debugging-port?")
    if match:
        for t in pages:
            if match.lower() in (t.get("url", "") + t.get("title", "")).lower():
                return t
        raise SystemExit(f"no page target matching {match!r}; have: "
                         + ", ".join(t.get("url", "")[:60] for t in pages))
    return pages[0]


class Page:
    """One websocket to one page target. Context-managed so it always closes."""

    def __init__(self, match: str = "", timeout: int = 45):
        self.t = pick_page(match)
        self.ws = websocket.create_connection(self.t["webSocketDebuggerUrl"],
                                              timeout=timeout, max_size=64 * 1024 * 1024)
        self._id = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            self.ws.close()
        except Exception:
            pass

    def send(self, method: str, params: dict | None = None, timeout: int = 45):
        self._id += 1
        mine = self._id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(1.0, deadline - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get("id") != mine:
                continue                      # an event or another reply -- ignore
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error'].get('message')}")
            return msg.get("result", {})
        raise TimeoutError(f"{method} did not answer within {timeout}s")

    def evaluate(self, expr: str, timeout: int = 45):
        r = self.send("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True,
                       "userGesture": True}, timeout=timeout)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise RuntimeError("JS threw: " + str(d.get("exception", {}).get("description")
                                                 or d.get("text"))[:400])
        return r.get("result", {}).get("value")


def cmd_url(a) -> int:
    with Page(a.match) as p:
        print(p.evaluate("location.href"))
        print(p.evaluate("document.title"))
    return 0


def cmd_targets(a) -> int:
    for t in list_targets():
        if t.get("type") != "page" and not a.all:
            continue
        print(f"[{t.get('type')}] {str(t.get('title'))[:60]}")
        print(f"      {str(t.get('url'))[:150]}")
    return 0


def cmd_text(a) -> int:
    with Page(a.match) as p:
        txt = p.evaluate("document.body ? document.body.innerText : ''") or ""
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    if a.grep:
        needle = a.grep.lower()
        lines = [ln for ln in lines if needle in ln.lower()]
    for ln in lines[: a.max]:
        print(ln)
    print(f"--- {len(lines)} non-empty lines"
          + (f" matching {a.grep!r}" if a.grep else "")
          + (f", showed {a.max}" if len(lines) > a.max else ""))
    return 0


def cmd_eval(a) -> int:
    with Page(a.match) as p:
        v = p.evaluate(a.expr, timeout=a.timeout)
    print(v if isinstance(v, str) else json.dumps(v, indent=1, default=str))
    return 0


def cmd_nav(a) -> int:
    with Page(a.match) as p:
        p.send("Page.navigate", {"url": a.url}, timeout=60)
        # Don't wait on the load event -- these SPAs keep loading forever. Poll readyState.
        for _ in range(a.wait):
            time.sleep(1)
            try:
                if p.evaluate("document.readyState", timeout=15) in ("interactive", "complete"):
                    break
            except Exception:
                continue
        time.sleep(2)
        print(p.evaluate("location.href"))
        print(p.evaluate("document.title"))
    return 0


def cmd_shot(a) -> int:
    with Page(a.match) as p:
        r = p.send("Page.captureScreenshot", {"format": "png"}, timeout=90)
    SHOTS.mkdir(parents=True, exist_ok=True)
    dest = SHOTS / f"cdp-{a.tag}.png"
    dest.write_bytes(base64.b64decode(r["data"]))
    print(f"[+] {dest}")
    return 0


CLICK_JS = """
(() => {
  const want = %s.toLowerCase().trim();
  const els = [...document.querySelectorAll('button,a,[role=button],input[type=submit],div[tabindex]')];
  const hit = els.find(e => (e.innerText||e.value||e.getAttribute('aria-label')||'')
                              .toLowerCase().trim().includes(want));
  if (!hit) return 'NOT_FOUND: ' + els.length + ' clickable elements scanned';
  hit.scrollIntoView({block:'center'});
  hit.click();
  return 'CLICKED: ' + (hit.innerText||hit.value||hit.getAttribute('aria-label')||hit.tagName)
           .slice(0,80).replace(/\\s+/g,' ');
})()
"""


def cmd_click(a) -> int:
    with Page(a.match) as p:
        print(p.evaluate(CLICK_JS % json.dumps(a.text), timeout=45))
        time.sleep(a.after)
        print("now at:", p.evaluate("location.href"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--match", default="", help="substring of the target page url/title")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("url").set_defaults(fn=cmd_url)
    t = sub.add_parser("targets"); t.add_argument("--all", action="store_true")
    t.set_defaults(fn=cmd_targets)
    x = sub.add_parser("text"); x.add_argument("--grep", default="")
    x.add_argument("--max", type=int, default=120); x.set_defaults(fn=cmd_text)
    e = sub.add_parser("eval"); e.add_argument("expr")
    e.add_argument("--timeout", type=int, default=45); e.set_defaults(fn=cmd_eval)
    n = sub.add_parser("nav"); n.add_argument("url")
    n.add_argument("--wait", type=int, default=25); n.set_defaults(fn=cmd_nav)
    s = sub.add_parser("shot"); s.add_argument("tag"); s.set_defaults(fn=cmd_shot)
    c = sub.add_parser("click"); c.add_argument("text")
    c.add_argument("--after", type=float, default=3.0); c.set_defaults(fn=cmd_click)

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
