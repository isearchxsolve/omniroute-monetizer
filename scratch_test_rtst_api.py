import json, urllib.request

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MTY2Mzk4OCwiZW1haWwiOiJrdW5hbC5jb2xhYkBnbWFpbC5jb20iLCJtb2JpbGUiOm51bGwsIm5hbWUiOiJLdW5hbCBEYXMiLCJjcmVkaXRzIjoyMCwicHJvZmlsZV9waWN0dXJlIjoiaHR0cHM6Ly9jZG4ucnRzdC5haS9wcm9maWxlLXBpY3R1cmVzL3VzZXItMTY2Mzk4OC0xNzg3NjkyODYzMjY4LmpwZyIsImlhdCI6MTc4NzkyMTIxNywiZXhwIjoxNzkwNTEzMjE3fQ.AdnOn5LMwRTkFkuLMpn9vi7tfMbAEEPFkEPXz1Y2AJg"

req = urllib.request.Request(
    "https://api.rtst.ai/v1/user/credits",
    headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
)
try:
    with urllib.request.urlopen(req) as resp:
        print("rtst API check:", resp.status, resp.read().decode('utf-8'))
except Exception as e:
    print("rtst API check error:", e)
