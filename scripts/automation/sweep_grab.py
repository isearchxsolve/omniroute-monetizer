"""sweep_grab.py — harvest cookie + genuine request template across the WHOLE forest of provider
tabs at once, over ONE browser-level CDP connection.

The operator's plan: "i do a one shot sweep across hundreds of the chat providers doing a ping or a
chat with them once and then you sweep them across grabbing their cookies." grab_session.py handles
ONE tab; this handles ALL open tabs simultaneously without the all-target attach that wedged
Playwright — we connect to the BROWSER endpoint and use Target.setAutoAttach(flatten) so a single
websocket receives Network events from every page via per-target sessionIds.

Read-only: we only enable the Network event stream and read cookies. We never send a chat, POST,
navigate, or mutate. As the operator pings each provider once, we auto-capture, per host: the
genuine request template (headers incl. Cookie + body) and the structured cookie jar, writing a
uniform state/secrets/session_<host>.json (same schema grab_session.py / veo_session_replay use).

A "chat-like" request is detected generically (no per-provider config): a POST whose RESPONSE is
text/event-stream (the near-universal streaming-chat signal) or a sizable application/json. That is
what lets one tool sweep hundreds of unknown providers.

    python sweep_grab.py targets            # dry-run: what tabs/hosts are in the forest
    python sweep_grab.py sweep [--wait 600] [--sse-only]   # arm capture across all tabs
"""
from __future__ import annotations
import json
import pathlib
import time
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import websocket  # websocket-client, already in venv

DEFAULT_PORT = 9222
SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
# Hosts that are never chat providers — skip so we don't persist unrelated cookies.
_SKIP_HOST = ("google.com", "gstatic.com", "doubleclick.net", "youtube.com", "amazon.",
              "bing.com", "olx.", "facebook.com", "chrome://", "newtab")


def _browser_ws(port: int) -> str:
    raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=15).read()
    return json.loads(raw)["webSocketDebuggerUrl"]


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _interesting(url: str) -> bool:
    h = _host(url)
    if not h or not url.startswith("http"):
        return False
    return not any(s in h for s in _SKIP_HOST)


class Browser:
    """One websocket to the BROWSER target. Speaks flat CDP: session-scoped commands carry a
    sessionId, browser-scoped ones don't. Events are demuxed by sessionId on the caller side."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: int = 30):
        self.ws = websocket.create_connection(_browser_ws(port), timeout=timeout,
                                              max_size=96 * 1024 * 1024)
        self._id = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            self.ws.close()
        except Exception:
            pass

    def send(self, method: str, params: Optional[dict] = None,
             session_id: Optional[str] = None, timeout: int = 30) -> dict:
        self._id += 1
        mine = self._id
        msg: Dict[str, Any] = {"id": mine, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(1.0, deadline - time.time()))
            try:
                got = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if got.get("id") != mine:
                continue                                  # an event or another reply — skip here
            if "error" in got:
                raise RuntimeError(f"{method}: {got['error'].get('message')}")
            return got.get("result", {})
        raise TimeoutError(f"{method} did not answer within {timeout}s")

    def targets(self) -> List[dict]:
        return [t for t in self.send("Target.getTargets").get("targetInfos", [])
                if t.get("type") == "page"]


def cmd_targets(port: int) -> int:
    with Browser(port) as b:
        ver = b.send("Browser.getVersion")
        print(f"UA: {(ver.get('userAgent') or '')[:90]}…\n")
        pages = b.targets()
        seen: Dict[str, int] = {}
        print(f"{len(pages)} page targets:")
        for t in pages:
            h = _host(t.get("url", ""))
            tag = "chat?" if _interesting(t.get("url", "")) else "skip "
            seen[h] = seen.get(h, 0) + 1
            print(f"  [{tag}] {h:28s} {str(t.get('title',''))[:38]:38s} {t.get('url','')[:60]}")
        hosts = sorted(h for h in seen if h and _interesting("https://" + h))
        print(f"\n{len(hosts)} candidate provider hosts: {', '.join(hosts)}")
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("targets")
    s = sub.add_parser("sweep")
    s.add_argument("--wait", type=int, default=600)
    s.add_argument("--sse-only", action="store_true", help="only capture text/event-stream responses")

    a = ap.parse_args()
    if a.cmd == "targets":
        return cmd_targets(a.port)
    if a.cmd == "sweep":
        return sweep(a.port, a.wait, a.sse_only)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
