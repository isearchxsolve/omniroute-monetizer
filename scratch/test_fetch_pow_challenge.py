import urllib.request
import urllib.parse
import json
import sys
import pathlib

# Try to get authorization from the captured session
session_file = pathlib.Path("state/secrets/session_deepseek_chat.json")
if not session_file.exists():
    print("Session file not found")
    sys.exit(1)

session = json.loads(session_file.read_text(encoding="utf-8"))
req_info = session.get("recorded_exchange", {}).get("request", {})
headers = session.get("recorded_exchange", {}).get("request_headers", {})
cookie_str = session.get("cookie_header", "")

# We need the authorization token, usually in the headers
auth_token = headers.get("authorization")

req_headers = {
    "authorization": auth_token,
    "content-type": "application/json",
    "user-agent": headers.get("user-agent", "Mozilla/5.0"),
    "cookie": cookie_str
}

print("Fetching PoW challenge...")
payload = json.dumps({"target_path": "/api/v0/chat/completion"}).encode("utf-8")
req = urllib.request.Request(
    "https://chat.deepseek.com/api/v0/chat/create_pow_challenge",
    method="POST",
    data=payload,
    headers=req_headers
)

try:
    with urllib.request.urlopen(req) as response:
        body = response.read().decode("utf-8")
        print("Response:", body)
except Exception as e:
    print("Failed:", e)
    if hasattr(e, 'read'):
        print("Error body:", e.read().decode("utf-8"))
