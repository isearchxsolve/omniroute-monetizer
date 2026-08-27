import sys, json, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(p.read_text(encoding="utf-8-sig"))
ws = d.get("recorded_ws") or {}
print("host:", d.get("host"), "| transport:", d.get("transport"))
print("ws url:", ws.get("url"))
print("preexisting:", ws.get("preexisting_socket"), "| counts:", ws.get("counts"))
print("sentinel_frame_index:", ws.get("sentinel_frame_index"))
print("cookie_header len:", len(d.get("cookie_header") or ""))
hh = ws.get("handshake_headers") or {}
print("handshake header names:", sorted(hh.keys()))

print("\n===== FRAMES SENT (Chrome -> grok) =====")
for i, f in enumerate(ws.get("frames_sent") or []):
    print(f"\n--- sent[{i}] ({len(f)}B) ---")
    print(f[:1200])

print("\n===== FRAMES RECEIVED (grok -> Chrome) — first 12 =====")
for i, f in enumerate((ws.get("frames_received") or [])[:12]):
    print(f"\n--- recv[{i}] ({len(f)}B) ---")
    print(f[:800])

print("\n===== LAST 3 RECEIVED =====")
for i, f in enumerate((ws.get("frames_received") or [])[-3:]):
    print(f"\n--- recv[-{3-i}] ({len(f)}B) ---")
    print(f[:800])
