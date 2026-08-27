#!/usr/bin/env python3
"""capture_websocket_cdp.py — record the FULL websocket exchange for providers whose chat
send travels over a websocket frame (grok, copilot, meta.ai, ...).

Doctrine 3a (AGENTS.md): a WEBSOCKET capture outcome means Chrome speaks that websocket.
Chrome is doing it RIGHT NOW in the signed-in seat tab, so the capability exists and is
reachable with the cookie already in hand. The gap was never the site — the gap was that
capture_sessions_cdp.py recorded only `frameBytes` and threw away everything replay needs:
the ws URL, the handshake headers, and the frame sequence. This script records all of it.

What gets recorded (the blueprint for a stateless websocket replay client)
--------------------------------------------------------------------------
  * the websocket URL (wss://...) exactly as Chrome opened it
  * the handshake request headers (cookies, auth, subprotocol) Chrome sent
  * every frame Chrome SENT, in order (one of them carries the sentinel prompt)
  * every frame the server SENT BACK, in order (the streamed answer)
  * any sentinel-carrying HTTP POST that happened alongside (some ws protocols create the
    conversation over HTTP first, then stream over the socket)

The page is RELOADED with Network.enable already active so the websocket creation itself is
observed — a socket that was already open before capture started has no creation event, and
without it the replay client would not know the URL or the auth.

Law 5 is absolute: a captcha/card/quota wall is a FULL STOP, reported, never worked around.
Secrets land only in state/secrets/ (gitignored). STDOUT is metadata only: hosts, paths with
query stripped, frame counts, byte sizes. Never a cookie, token, or full payload.

Usage
-----
    python capture_websocket_cdp.py --port 9222 --match grok.com --name "Grok WS"
    python capture_websocket_cdp.py --port 9222 --match copilot.microsoft.com --name "Copilot WS"
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request
from typing import Any

from capture_sessions_cdp import (CDP, CDPError, JS_FOCUS_COMPOSER, JS_PAGE_TEXT, JS_READ_ACTIVE,
                                  JS_SEND, NOISE, SECRETS, SENTINEL, SENTINEL_FORMS, WALL_TEXT,
                                  has_sentinel, host_of, open_tab, slug, targets)

# A websocket frame bigger than this is almost certainly a binary blob or a giant state dump,
# not protocol. Stored truncated so the blueprint stays a protocol record, not a disk hog.
_MAX_FRAME = 200_000
# Keep at most this many received frames per socket (streamed token deltas are tiny; the cap
# only protects against a pathological firehose).
_MAX_RECV_FRAMES = 4000


def _strip_query(url: str) -> str:
    s = urllib.parse.urlsplit(url)
    return f"{s.scheme}://{s.netloc}{s.path}"


def _activate(port: int, target_id: str) -> bool:
    """Wake a discarded tab. Same pattern as capture_video_job_cdp._activate."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/activate/{target_id}", timeout=8):
            return True
    except Exception:
        return False


def capture_ws(port: int, match: str, name: str, wait: float = 120.0,
               ready_wait: float = 30.0, url: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"site": name, "transport": "websocket"}

    tabs = [t for t in targets(port) if match.lower() in (t.get("url", "") + t.get("title", "")).lower()]
    if not tabs and url:
        t = open_tab(port, url)
        if t:
            tabs = [t]
            time.sleep(3.0)
    if not tabs:
        row.update(status="NO_TAB", note=f"no page target matching {match!r} on port {port}")
        return row
    t = tabs[0]
    row["tabUrl"] = _strip_query(t.get("url", ""))

    row["activated"] = _activate(port, t.get("id") or "")
    if row["activated"]:
        time.sleep(2.0)

    c = CDP(t["webSocketDebuggerUrl"], timeout=max(60.0, wait + 30))
    try:
        try:
            c.call("Runtime.enable", timeout=25)
        except CDPError:
            c.call("Page.enable", timeout=15)
            c.call("Page.bringToFront", timeout=15)
            time.sleep(3.0)
            c.call("Runtime.enable", timeout=25)
            row["neededWake"] = True
        c.call("Page.enable")
        try:
            c.call("Page.bringToFront", timeout=12)
        except CDPError:
            pass

        # ---- Law 5 first ---------------------------------------------------------------------
        page_text = (c.evaluate(JS_PAGE_TEXT) or "").lower()
        wall = next((w for w in WALL_TEXT if w in page_text), None)
        if wall:
            row.update(status="WALL", wall=wall,
                       note="wall text on the page -- STOP, never solve, never pay")
            return row

        # ---- Network on BEFORE the reload so the websocket creation is observed --------------
        c.call("Network.enable")

        # Reload: a socket opened before capture has no creation event, and without it the replay
        # client gets neither URL nor handshake auth. The reload costs nothing (no credits) and
        # guarantees both are observed.
        c.call("Page.reload", {"ignoreCache": False})
        row["reloaded"] = True

        # Poll for the composer on the fresh page instead of guessing a sleep.
        focus: dict = {}
        deadline = time.monotonic() + ready_wait + 15.0   # reload adds boot time
        while time.monotonic() < deadline:
            if (c.evaluate("document.readyState") or "") == "complete":
                focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
                if focus.get("ok"):
                    break
            time.sleep(1.5)
        row["readyState"] = c.evaluate("document.readyState")
        if not focus.get("ok"):
            pt = (c.evaluate(JS_PAGE_TEXT) or "").lower()
            inline = next((w for w in WALL_TEXT if w in pt), None)
            if inline:
                row.update(status="WALL", wall=inline, note="inline wall after reload -- STOP")
                return row
            row.update(status="NO_COMPOSER", detail=(focus or {}).get("error") or "page never ready")
            return row
        row["composer"] = {k: focus.get(k) for k in ("tag", "editable", "candidates")}

        # ---- type the sentinel and READ IT BACK ----------------------------------------------
        c.call("Input.insertText", {"text": SENTINEL})
        time.sleep(0.4)
        back = c.evaluate(JS_READ_ACTIVE) or {}
        landed = SENTINEL.split(":")[0] in (back.get("text") or "")
        row["textLanded"] = bool(landed)
        if not landed:
            row.update(status="TEXT_REJECTED", note="composer did not accept the prompt")
            return row

        # ---- submit: try each strategy, verified against the network --------------------------
        seen = {"requests": 0, "posts": 0, "wsCreated": 0, "wsSent": 0, "wsRecv": 0}
        handled_rids: set[str] = set()
        http_hit: dict[str, Any] | None = None

        # websocket bookkeeping: requestId -> connection record
        ws_conns: dict[str, dict[str, Any]] = {}
        sentinel_ws: str | None = None          # requestId whose SENT frame carries the sentinel
        sentinel_frame_idx: int | None = None

        def drain(seconds: float, until_quiet: float = 0.0) -> None:
            """Pump CDP events, folding network/websocket events into the records.

            until_quiet>0: keep going until no new ws-received frame arrived for that many
            seconds (answer stream finished), bounded by `seconds`.
            """
            nonlocal sentinel_ws, sentinel_frame_idx, http_hit
            end = time.monotonic() + seconds
            last_recv = time.monotonic()
            got_post_submit_recv = False
            while time.monotonic() < end:
                c.pump(0.8)
                for ev in list(c.events):
                    m = ev.get("method")
                    p = ev.get("params") or {}
                    rid = str(p.get("requestId") or "")
                    if m == "Network.webSocketCreated":
                        seen["wsCreated"] += 1
                        ws_conns[rid] = {"url": p.get("url") or "",
                                         "handshake_headers": None,
                                         "response_headers": None,
                                         "sent": [], "recv": [],
                                         "created": time.monotonic(), "closed": None}
                    elif m == "Network.webSocketWillSendHandshakeRequest":
                        if rid in ws_conns:
                            ws_conns[rid]["handshake_headers"] = {
                                k: v for k, v in ((p.get("request") or {}).get("headers") or {}).items()
                                if not k.startswith(":")}
                    elif m == "Network.webSocketHandshakeResponseReceived":
                        if rid in ws_conns:
                            ws_conns[rid]["response_headers"] = {
                                k: v for k, v in ((p.get("response") or {}).get("headers") or {}).items()
                                if not k.startswith(":")}
                            ws_conns[rid]["status"] = (p.get("response") or {}).get("status")
                    elif m == "Network.webSocketFrameSent":
                        seen["wsSent"] += 1
                        pl = str((p.get("response") or {}).get("payloadData") or "")
                        conn = ws_conns.setdefault(rid, {"url": "", "handshake_headers": None,
                                                         "response_headers": None, "sent": [],
                                                         "recv": [], "preexisting": True,
                                                         "created": time.monotonic(), "closed": None})
                        conn["sent"].append(pl[:_MAX_FRAME])
                        if has_sentinel(pl) and sentinel_ws is None:
                            sentinel_ws = rid
                            sentinel_frame_idx = len(conn["sent"]) - 1
                    elif m == "Network.webSocketFrameReceived":
                        seen["wsRecv"] += 1
                        pl = str((p.get("response") or {}).get("payloadData") or "")
                        conn = ws_conns.setdefault(rid, {"url": "", "handshake_headers": None,
                                                         "response_headers": None, "sent": [],
                                                         "recv": [], "preexisting": True,
                                                         "created": time.monotonic(), "closed": None})
                        if len(conn["recv"]) < _MAX_RECV_FRAMES:
                            conn["recv"].append(pl[:_MAX_FRAME])
                        if sentinel_ws is not None and rid == sentinel_ws:
                            last_recv = time.monotonic()
                            got_post_submit_recv = True
                    elif m == "Network.webSocketClosed":
                        if rid in ws_conns:
                            ws_conns[rid]["closed"] = time.monotonic()
                    elif m == "Network.requestWillBeSent":
                        if not rid or rid in handled_rids:
                            continue
                        handled_rids.add(rid)
                        seen["requests"] += 1
                        req = p.get("request") or {}
                        rurl = req.get("url") or ""
                        if req.get("method") not in ("POST", "PUT", "PATCH"):
                            continue
                        if any(n in rurl.lower() for n in NOISE):
                            continue
                        seen["posts"] += 1
                        body = req.get("postData") or ""
                        if not body and req.get("hasPostData"):
                            try:
                                body = (c.call("Network.getRequestPostData", {"requestId": rid},
                                               timeout=10).get("postData") or "")
                            except CDPError:
                                body = ""
                        if body and has_sentinel(body) and http_hit is None:
                            rh = {k: v for k, v in (req.get("headers") or {}).items()
                                  if not k.startswith(":")}
                            http_hit = {"url": rurl, "method": req.get("method"),
                                        "request_headers": rh, "request_body": body}
                c.events.clear()
                if until_quiet and got_post_submit_recv and (time.monotonic() - last_recv) > until_quiet:
                    break

        def _key(key: str, code: str, vk: int, modifiers: int = 0, text: str | None = None) -> None:
            base = {"key": key, "code": code, "windowsVirtualKeyCode": vk,
                    "nativeVirtualKeyCode": vk, "modifiers": modifiers}
            down = dict(base, type="keyDown")
            if text is not None:
                down["text"] = text
                down["unmodifiedText"] = text
            c.call("Input.dispatchKeyEvent", down, timeout=8)
            c.call("Input.dispatchKeyEvent", dict(base, type="keyUp"), timeout=8)

        def press_enter() -> None:
            _key("Enter", "Enter", 13, text="\r")

        def strat_enter() -> None:
            press_enter()

        def strat_js_click() -> None:
            r = c.evaluate(JS_SEND.replace("__CLICK__", "true")) or {}
            if not r.get("ok"):
                raise CDPError(f"send control: {r.get('error') or 'not found'}")

        def strat_mouse_send() -> None:
            r = c.evaluate(JS_SEND.replace("__CLICK__", "false")) or {}
            if not r.get("ok") or r.get("x") is None:
                raise CDPError(f"send control: {r.get('error') or 'not found'}")
            for kind, clicks in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 1)):
                c.call("Input.dispatchMouseEvent", {"type": kind, "x": r["x"], "y": r["y"],
                                                    "button": "left", "clickCount": clicks})

        def strat_retype() -> None:
            f2 = c.evaluate(JS_FOCUS_COMPOSER) or {}
            if not f2.get("ok"):
                raise CDPError("composer vanished before retype")
            time.sleep(0.2)
            _key("a", "KeyA", 65, modifiers=2)
            _key("Backspace", "Backspace", 8)
            for ch in SENTINEL:
                _key(ch, "", 0, text=ch)
            time.sleep(0.3)
            press_enter()

        # Drain pre-submit traffic (page-load websockets, hello frames) so the blueprint holds
        # the socket's full life, then submit and watch until the answer stream goes quiet.
        drain(6.0)
        per = max(8.0, wait / 6.0)
        row["strategiesTried"] = []
        submitted = False
        for label, fn in (("enter", strat_enter), ("js_click_send", strat_js_click),
                          ("mouse_send", strat_mouse_send), ("retype_keys", strat_retype)):
            try:
                fn()
            except CDPError as e:
                row.setdefault("strategySkipped", {})[label] = str(e)[:90]
                continue
            row["strategiesTried"].append(label)
            drain(per, until_quiet=6.0)
            if sentinel_ws is not None or http_hit is not None:
                row["submitStrategy"] = label
                submitted = True
                break

        # Give a late answer stream a final grace window.
        if submitted:
            drain(10.0, until_quiet=5.0)

        row.update(requestsSeen=seen["requests"], postsSeen=seen["posts"],
                   wsCreated=seen["wsCreated"], wsSent=seen["wsSent"], wsRecv=seen["wsRecv"])

        # ---- verdict --------------------------------------------------------------------------
        if sentinel_ws is None and http_hit is None:
            row.update(status="NO_SENTINEL_TRANSPORT",
                       note="submit produced no sentinel-carrying ws frame or HTTP POST -- "
                            "find where Chrome actually sends before anything else")
            return row

        # Cookies for replay: the jar of the page, exactly as the HTTP capture does it.
        jar = c.call("Network.getCookies", {"urls": [t.get("url", "")]}).get("cookies", [])
        cookie_header = "; ".join(f"{k['name']}={k['value']}" for k in jar)

        host = host_of(t.get("url", ""))
        payload: dict[str, Any] = {
            "host": host,
            "modality": "chat",
            "site": name,
            "transport": "websocket",
            "sentinel": SENTINEL,
            "updated_at": int(time.time()),
            "cookie_header": cookie_header,
            "status": {"alive": True,
                       "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "reason": "capture_websocket_cdp"},
        }
        if http_hit is not None:
            payload["recorded_exchange"] = dict(http_hit, host=host_of(http_hit["url"]),
                                                cookie_header=cookie_header)
        if sentinel_ws is not None:
            conn = ws_conns.get(sentinel_ws) or {}
            payload["recorded_ws"] = {
                "url": conn.get("url") or "",
                "urlHost": host_of(conn.get("url") or ""),
                "handshake_headers": conn.get("handshake_headers"),
                "response_status": conn.get("status"),
                "frames_sent": conn.get("sent") or [],
                "frames_received": (conn.get("recv") or [])[:_MAX_RECV_FRAMES],
                "sentinel_frame_index": sentinel_frame_idx,
                "preexisting_socket": bool(conn.get("preexisting")),
                "counts": {"sent": len(conn.get("sent") or []), "recv": len(conn.get("recv") or [])},
            }
            # Other sockets opened during the exchange are protocol context (e.g. a presence
            # channel). Keep their URL + counts, never their payloads.
            others = {rid: {"url": _strip_query(v.get("url") or ""),
                            "sent": len(v.get("sent") or []), "recv": len(v.get("recv") or [])}
                      for rid, v in ws_conns.items() if rid != sentinel_ws}
            if others:
                payload["recorded_ws"]["other_sockets"] = others

        # Merge into the existing seat file (preserve context/status fields written by other
        # tools); the blueprint keys above win.
        SECRETS.mkdir(parents=True, exist_ok=True)
        out = SECRETS / f"session_{slug(name)}.json"
        if out.exists():
            try:
                existing = json.loads(out.read_text(encoding="utf-8-sig"))
                existing.update(payload)
                payload = existing
            except Exception:
                pass
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        wsinfo = payload.get("recorded_ws") or {}
        row.update(status="CAPTURED_WS",
                   file=str(out),
                   wsUrl=_strip_query(wsinfo.get("url") or ""),
                   wsPreexisting=wsinfo.get("preexisting_socket"),
                   framesSent=wsinfo.get("counts", {}).get("sent"),
                   framesRecv=wsinfo.get("counts", {}).get("recv"),
                   sentinelFrame=wsinfo.get("sentinel_frame_index"),
                   httpPost=bool(http_hit),
                   cookieCount=len(jar))
        return row
    except CDPError as e:
        row.update(status="CDP_ERROR", detail=str(e)[:140])
        return row
    except Exception as e:
        row.update(status="CDP_ERROR", detail=f"{type(e).__name__}: {str(e)[:120]}")
        return row
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--match", required=True, help="substring of the tab url/title")
    ap.add_argument("--name", required=True, help="seat display name; file = session_<slug>.json")
    ap.add_argument("--wait", type=float, default=120.0, help="max seconds to watch after submit")
    ap.add_argument("--ready-wait", type=float, default=30.0)
    ap.add_argument("--url", default="", help="open a tab at this URL if none matches")
    a = ap.parse_args()
    row = capture_ws(a.port, a.match, a.name, a.wait, a.ready_wait, a.url)
    safe = {k: v for k, v in row.items()}
    print(json.dumps(safe, indent=2, ensure_ascii=False, default=str))
    return 0 if row.get("status") == "CAPTURED_WS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
