# -*- coding: utf-8 -*-
"""Inspect the chatgpt recorded exchange request shape (secrets redacted)."""
import json, pathlib

raw = json.loads(pathlib.Path("state/secrets/session_chatgpt_free_web.json").read_text(encoding="utf-8"))
re_ = raw["recorded_exchange"]
print("url:", re_.get("url"))
print("method:", re_.get("method"))
print("host:", re_.get("host"))
hdrs = re_.get("request_headers") or {}
print("header names:", sorted(hdrs.keys()))
for k in ("authorization", "x-conduit-token", "content-type", "openai-sentinel",
          "oai-device-id", "chatgpt-account-id", "origin", "referer"):
    v = hdrs.get(k) or hdrs.get(k.title())
    if v:
        if k in ("authorization", "x-conduit-token"):
            print("  ", k, "=", str(v)[:16] + "...REDACTED")
        else:
            print("  ", k, "=", v)
body = re_.get("request_body")
print("body type:", type(body).__name__)
if isinstance(body, str):
    try:
        body = json.loads(body)
    except Exception:
        pass
if isinstance(body, dict):
    print("body keys:", list(body.keys()))
    print("body model:", body.get("model"))
    msgs = body.get("messages") or body.get("input")
    if isinstance(msgs, list):
        print("msg roles:", [m.get("role") for m in msgs][:5])
