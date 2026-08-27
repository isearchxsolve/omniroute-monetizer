"""Dump the full DeepSeek live sequence bodies (challenge + completion SSE)."""
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

d = json.load(open("_ds_live_sequence.json", encoding="utf-8"))
for rid, req in d["requests"].items():
    if "create_pow_challenge" in req["url"] and rid in d["bodies"]:
        print("=== CHALLENGE RESPONSE (full) ===")
        print(d["bodies"][rid])
        print()
for rid, req in d["requests"].items():
    if req["url"].endswith("/completion") and rid in d["bodies"]:
        print("=== COMPLETION REQUEST HEADERS ===")
        for k, v in req["headers"].items():
            if k.lower() in ("x-ds-pow-response", "authorization", "content-type"):
                print(f"  {k}: {v[:200]}")
        print("=== COMPLETION REQUEST BODY ===")
        print(req.get("postData", "")[:400])
        print("=== COMPLETION RESPONSE BODY (full) ===")
        print(d["bodies"][rid])
