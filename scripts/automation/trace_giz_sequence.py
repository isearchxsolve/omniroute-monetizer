#!/usr/bin/env python3
"""One-use, metadata-only trace of a single Giz chat submission on an attested seat."""
from __future__ import annotations

import json
import pathlib
import time
import urllib.parse

from capture_sessions_cdp import CDP, JS_FOCUS_COMPOSER, JS_READ_ACTIVE, SENTINEL, has_sentinel, targets
from tab_graduation_sweep import assert_automation_seat

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "state" / "giz_sequence_trace.json"


def body_shape(body: str) -> dict:
    try:
        obj = json.loads(body)
    except ValueError:
        return {"json": False, "bytes": len(body), "sentinel": has_sentinel(body)}
    return {"json": True, "bytes": len(body), "sentinel": has_sentinel(body),
            "topKeys": sorted(obj) if isinstance(obj, dict) else [],
            "hasResponseSchema": isinstance(obj, dict) and "responseSchema" in obj,
            "hasSubscribeId": isinstance(obj, dict) and "subscribeId" in obj,
            "hasInstanceId": isinstance(obj, dict) and "instanceId" in obj}


def main() -> int:
    port = 9224
    owner = assert_automation_seat(port)
    tab = next((t for t in targets(port) if urllib.parse.urlsplit(t.get("url", "")).hostname == "www.giz.ai"), None)
    if not tab:
        raise SystemExit("refused: no current Giz page on attested Seat2")
    c = CDP(tab["webSocketDebuggerUrl"])
    try:
        focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
        if not focus.get("ok"):
            raise SystemExit("refused: no visible Giz composer")
        c.call("Network.enable")
        c.call("Input.insertText", {"text": SENTINEL})
        readback = c.evaluate(JS_READ_ACTIVE) or {}
        if SENTINEL.split(":")[0] not in (readback.get("text") or ""):
            raise SystemExit("refused: sentinel did not land in composer")
        base = {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                "nativeVirtualKeyCode": 13, "type": "keyDown", "text": "\r", "unmodifiedText": "\r"}
        c.call("Input.dispatchKeyEvent", base)
        c.call("Input.dispatchKeyEvent", {k:v for k,v in base.items() if k not in ("text", "unmodifiedText")} | {"type":"keyUp"})
        # Keep the one-shot trace below the command runner's 30s envelope so
        # metadata is flushed even when the UI itself has already answered.
        end, rows, handled, responses, sockets, posts_seen = time.monotonic() + 18, [], set(), [], [], 0
        while time.monotonic() < end:
            c.pump(0.8)
            buffered, c.events[:] = list(c.events), []
            for event in buffered:
                method = event.get("method") or ""
                params = event.get("params") or {}
                if method == "Network.responseReceived":
                    response = params.get("response") or {}; u = urllib.parse.urlsplit(response.get("url") or "")
                    if u.hostname == "www.giz.ai": responses.append({"path":u.path,"status":response.get("status"),"mimeType":response.get("mimeType")})
                    continue
                if method in ("Network.webSocketCreated", "Network.webSocketFrameReceived", "Network.webSocketFrameSent"):
                    sockets.append({"event":method, "requestId":str(params.get("requestId") or "")})
                    continue
                if event.get("method") != "Network.requestWillBeSent": continue
                p=event.get("params") or {}; rid=str(p.get("requestId") or "")
                if not rid or rid in handled: continue
                handled.add(rid); req=p.get("request") or {}; body=req.get("postData") or ""
                if req.get("method") not in ("POST","PUT","PATCH"): continue
                posts_seen += 1
                if not body and req.get("hasPostData"):
                    try: body=c.call("Network.getRequestPostData", {"requestId":rid}, timeout=8).get("postData") or ""
                    except Exception: pass
                if has_sentinel(body):
                    u=urllib.parse.urlsplit(req.get("url") or "")
                    rows.append({"order":len(rows)+1,"host":u.hostname,"path":u.path,"shape":body_shape(body)})
        OUT.write_text(json.dumps({"port":port,"profile":str(owner.user_data_dir),"site":"Giz AI","readbackLanded":True,"postsSeen":posts_seen,"requests":rows,"responses":responses,"websocketEvents":sockets},indent=2)+"\n",encoding="utf-8")
        print(f"trace requests: {len(rows)}  report: {OUT}")
        for r in rows: print(r["order"],r["host"],r["path"],r["shape"])
    finally:
        c.close()
    return 0

if __name__ == "__main__": raise SystemExit(main())
