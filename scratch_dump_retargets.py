# -*- coding: utf-8 -*-
"""Dump the key fields of the four class-(c) re-capture target secrets."""
import json, pathlib

SECRETS = pathlib.Path("state/secrets")
TARGETS = ["session_chatgpt_free_web.json", "session_meta_ai_web.json",
           "session_you_com_chat.json", "session_digen_ai.json"]

for name in TARGETS:
    p = SECRETS / name
    if not p.exists():
        print(f"== {name}: MISSING"); continue
    raw = json.loads(p.read_text(encoding="utf-8"))
    print(f"== {name}")
    print(f"   host: {raw.get('host')}")
    print(f"   modality: {raw.get('modality')}")
    print(f"   status: {json.dumps(raw.get('status'))[:200]}")
    rec = raw.get("recorded_exchange")
    if rec:
        req = rec.get("request") or {}
        print(f"   recorded_exchange: method={req.get('method')} url={req.get('url')}")
        hdrs = req.get("headers") or {}
        print(f"   headers keys: {sorted(hdrs.keys())[:15]}")
        body = req.get("body") or req.get("json")
        print(f"   body preview: {str(body)[:150]}")
        resp = rec.get("response") or {}
        print(f"   response status: {resp.get('status')}")
    else:
        print("   recorded_exchange: NONE")
    if raw.get("recorded_job"):
        print(f"   recorded_job: present ({len(json.dumps(raw['recorded_job']))} bytes)")
    if raw.get("api"):
        api = raw["api"]
        print(f"   api: kind={api.get('kind')} base={api.get('base_url') or api.get('base')}")
    ctx = raw.get("context") or {}
    print(f"   context: {json.dumps(ctx)[:150]}")
    print()
