"""Re-inspect the 6 seats with the CORRECT recording schema keys."""
import json, pathlib, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SEATS = [
    "session_cerebras_inference_chat",
    "session_deepseek_chat",
    "session_google_gemini_web",
    "session_meta_ai_web",
    "session_v0_app",
    "session_zhipu_glm_chat",
]

sec = pathlib.Path("state/secrets")
for name in SEATS:
    f = sec / (name + ".json")
    raw = json.loads(f.read_text(encoding="utf-8-sig"))
    rec = raw.get("recorded_exchange") or {}
    hdrs = rec.get("request_headers") or {}
    print("=" * 70)
    print("SEAT:", name, "| host:", raw.get("host"), "| status:", raw.get("status"))
    print("  url:", (rec.get("url") or "")[:120])
    print("  method:", rec.get("method"))
    print("  header NAMES:", sorted(hdrs.keys()) if isinstance(hdrs, dict) else type(hdrs).__name__)
    print("  cookie_header len:", len(rec.get("cookie_header") or raw.get("cookie_header") or ""))
    body = rec.get("request_body")
    print("  body type:", type(body).__name__, "| len:", len(str(body)) if body else 0)
    if isinstance(body, str):
        print("  body head:", body[:200].replace("\n", " "))
    elif isinstance(body, dict):
        print("  body keys:", sorted(body.keys()))
    print("  sentinel:", repr(raw.get("sentinel"))[:80])
