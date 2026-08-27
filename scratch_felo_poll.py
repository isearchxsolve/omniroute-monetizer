"""Poll the Felo stream endpoint with the stream_key from the bootstrap response."""
import json, pathlib, time, requests

ROOT = pathlib.Path(__file__).resolve().parent
p = ROOT / "state/secrets/session_felo_ai_web.json"
d = json.loads(p.read_text(encoding="utf-8"))
cookie = d.get("cookie_header", "")

# The stream_key from the bootstrap we got earlier
stream_key = "da6817c3-3422-4c8b-9e5c-db42a81e98c4"
url = f"https://felo.ai/api/message/v1/stream/{stream_key}?offset=0"

headers = {
    "cookie": cookie,
    "Accept": "text/event-stream",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://felo.ai/",
}

print("polling:", url[:80])
r = requests.get(url, headers=headers, timeout=30, stream=True)
print("status:", r.status_code)
print("content-type:", r.headers.get("Content-Type"))

# Read up to 5s of stream
text = ""
start = time.time()
for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
    text += chunk
    if time.time() - start > 8:
        break
    if "58" in text or len(text) > 3000:
        break

print("\n--- stream content (first 1500 chars) ---")
print(text[:1500])
