"""Complete Felo multi-step replay: POST bootstrap -> GET stream -> read to completion -> extract answer."""
import json, pathlib, time, requests, re

ROOT = pathlib.Path(__file__).resolve().parent
p = ROOT / "state/secrets/session_felo_ai_web.json"
d = json.loads(p.read_text(encoding="utf-8"))
ex = d.get("recorded_exchange") or {}
hdrs = ex.get("request_headers") or {}
auth = hdrs.get("Authorization") or hdrs.get("authorization") or ""
cookie = d.get("cookie_header", "")

PROMPT = "Reply with only the number: 41 + 17"

# Step 1: POST bootstrap
body = json.loads(ex["request_body"])
body["query"] = PROMPT

post_headers = {k: v for k, v in hdrs.items() if not k.startswith(":") and k.lower() != "content-length"}
post_headers["cookie"] = cookie

r1 = requests.post(ex["url"], json=body, headers=post_headers, timeout=30)
boot = r1.json()
stream_key = boot.get("stream_key") or boot.get("message_id")
print(f"bootstrap: status={r1.status_code} stream_key={stream_key}")

# Step 2: GET stream, read to completion
url = f"https://felo.ai/api/message/v1/stream/{stream_key}?offset=0"
get_headers = {
    "Accept": "text/event-stream",
    "Authorization": auth,
    "Referer": "https://felo.ai/",
    "User-Agent": hdrs.get("User-Agent", "Mozilla/5.0"),
}
r2 = requests.get(url, headers=get_headers, timeout=60, stream=True)
print(f"stream: status={r2.status_code}")

# Parse SSE events, accumulate the answer text
answer_parts = []
is_complete = False
start = time.time()
buf = ""
for chunk in r2.iter_content(chunk_size=None, decode_unicode=True):
    buf += chunk
    # process complete SSE events
    while "\n\n" in buf:
        event_block, buf = buf.split("\n\n", 1)
        for line in event_block.split("\n"):
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                except Exception:
                    continue
                if data.get("is_complete"):
                    is_complete = True
                content_str = data.get("content", "")
                if content_str:
                    try:
                        content = json.loads(content_str)
                    except Exception:
                        continue
                    # The answer text lives in various nested structures
                    ctype = content.get("type", "")
                    cdata = content.get("data", {})
                    if isinstance(cdata, dict):
                        # Look for the actual answer text
                        text = cdata.get("text", "")
                        if text and ctype == "message" and cdata.get("status") not in ("initializing",):
                            answer_parts.append(text)
                        # Also check nested 'data' for answer chunks
                        inner = cdata.get("data", {})
                        if isinstance(inner, dict):
                            t2 = inner.get("text", "") or inner.get("content", "")
                            if t2:
                                answer_parts.append(t2)
    if is_complete or (time.time() - start > 45):
        break

full_answer = "".join(answer_parts)
print(f"\nis_complete: {is_complete}")
print(f"answer length: {len(full_answer)}")
print(f"contains '58': {'58' in full_answer}")
print(f"\n--- answer (first 500) ---")
print(full_answer[:500])
