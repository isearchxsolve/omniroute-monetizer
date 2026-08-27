"""Full Felo multi-step replay proof: POST bootstrap -> GET stream with Authorization header."""
import json, pathlib, time, requests

ROOT = pathlib.Path(__file__).resolve().parent
p = ROOT / "state/secrets/session_felo_ai_web.json"
d = json.loads(p.read_text(encoding="utf-8"))
ex = d.get("recorded_exchange") or {}
hdrs = ex.get("request_headers") or {}
auth = hdrs.get("Authorization") or hdrs.get("authorization") or ""
cookie = d.get("cookie_header", "")

# Step 1: POST the bootstrap with the new prompt
body = json.loads(ex["request_body"])
body["query"] = "Reply with only the number: 41 + 17"
body["query_from"] = "followup"

post_headers = {k: v for k, v in hdrs.items() if not k.startswith(":") and k.lower() != "content-length"}
post_headers["cookie"] = cookie

print("step 1: POST bootstrap")
r1 = requests.post(ex["url"], json=body, headers=post_headers, timeout=30)
print("  status:", r1.status_code)
boot = r1.json()
stream_key = boot.get("stream_key") or boot.get("message_id")
print("  stream_key:", stream_key)

if not stream_key:
    print("  no stream_key, body:", r1.text[:300])
    raise SystemExit(1)

# Step 2: GET the stream with Authorization
print("\nstep 2: GET stream")
url = f"https://felo.ai/api/message/v1/stream/{stream_key}?offset=0"
get_headers = {
    "Accept": "text/event-stream",
    "Authorization": auth,
    "Referer": "https://felo.ai/",
    "User-Agent": hdrs.get("User-Agent", "Mozilla/5.0"),
}
r2 = requests.get(url, headers=get_headers, timeout=30, stream=True)
print("  status:", r2.status_code)

text = ""
start = time.time()
for chunk in r2.iter_content(chunk_size=None, decode_unicode=True):
    text += chunk
    if time.time() - start > 15:
        break
    if len(text) > 5000:
        break

print("\n--- stream (first 2000 chars) ---")
print(text[:2000])
print("\n--- contains 58?", "58" in text)
