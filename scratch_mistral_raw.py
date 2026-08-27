"""Inspect Mistral raw response after messageId fix."""
import json, pathlib, sys, requests
sys.path.insert(0, "scripts/automation")
from universal_replay import UniversalSessionClient
from multistep_replay import apply_preflight

p = pathlib.Path("state/secrets/session_mistral_le_chat.json")
client = UniversalSessionClient(str(p))
new_body = client._inject_prompt("Reply with only the number: 41 + 17")
new_body = apply_preflight("chat.mistral.ai", new_body)

r = requests.post(client.url, headers=client.headers, data=new_body.encode("utf-8"), timeout=60, stream=True)
print("status:", r.status_code)
print("content-type:", r.headers.get("content-type"))
raw = r.content.decode("utf-8", errors="replace")
print("raw len:", len(raw))
print("raw first 2000:")
print(raw[:2000])
print("...")
print("raw last 500:")
print(raw[-500:])
