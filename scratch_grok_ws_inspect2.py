"""scratch_grok_ws_inspect2.py — full dump of the grok ws blueprint for clues."""
import sys, json, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.loads(pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json").read_text(encoding="utf-8-sig"))
rws = d["recorded_ws"]
print("url:", rws["url"])
print("response_status:", rws.get("response_status"))
print("\n--- handshake request headers ---")
for k, v in (rws.get("handshake_headers") or {}).items():
    if k.lower() == "cookie":
        print(f"  {k}: <{len(v)} chars>")
    else:
        print(f"  {k}: {v}")
print("\n--- frames_sent (all) ---")
for i, f in enumerate(rws["frames_sent"]):
    try:
        o = json.loads(f)
        ev = o.get("event") or {}
        print(f"sent[{i}] type={ev.get('type')} keys={sorted(ev.keys())}")
        if ev.get("type") not in ("session.create", "response.create", "presence.update"):
            print("   FULL:", json.dumps(o)[:500])
    except Exception:
        print(f"sent[{i}] RAW:", f[:200])
print("\n--- frames_received: all distinct event types in order ---")
seen = []
for f in rws["frames_received"]:
    try:
        o = json.loads(f)
        t = (o.get("event") or {}).get("type")
        if t not in seen:
            seen.append(t)
    except Exception:
        pass
print(seen)
print("\n--- any recv frame mentioning move/attach/redirect ---")
for f in rws["frames_received"]:
    fl = f.lower()
    if "move" in fl or "attach" in fl or "redirect" in fl or "session.moved" in fl:
        print(f[:400])
        print("---")
