"""P2 recon part 2: full meta.ai recorded_exchange structure + seat Chrome registry (no secret VALUES printed)."""
import io, json, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

raw = json.loads(pathlib.Path("state/secrets/session_meta_ai_web.json").read_text(encoding="utf-8-sig"))
rec = raw["recorded_exchange"]
print("recorded_exchange keys:", sorted(rec.keys()))
print("url:", rec.get("url"))
print("method:", rec.get("method"))
rh = rec.get("request_headers") or {}
print("request_headers names:", sorted(rh.keys()))
body = rec.get("request_body") or rec.get("body") or rec.get("post_data") or ""
if isinstance(body, (dict, list)):
    body = json.dumps(body)
print("request_body len:", len(str(body)))
print("request_body head:", str(body)[:600])
resp = rec.get("response") or {}
if isinstance(resp, dict):
    print("response keys:", sorted(resp.keys()))
    print("response status:", resp.get("status") or resp.get("status_code"))
    rb = resp.get("body") or ""
    print("response body head:", str(rb)[:300])

# chrome port for the video seat + any seat registry
v = json.loads(pathlib.Path("state/secrets/session_video_meta.json").read_text(encoding="utf-8-sig"))
print("\nsession_video_meta chrome_port:", v.get("chrome_port"), "| context:", v.get("context"), "| notes:", str(v.get("notes"))[:200])

# seat registry / chrome ports map
for cand in ["state/seats.json", "state/seat_registry.json", "state/chrome_ports.json", "state/seat_chromes.json"]:
    p = pathlib.Path(cand)
    if p.exists():
        print("\nFOUND registry:", cand)
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        print(json.dumps(d, indent=1)[:1500])
