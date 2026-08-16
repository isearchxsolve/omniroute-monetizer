"""Poll the mail.tm inbox for the HuggingFace verification email."""
import json
import sys
import time

sys.path.insert(0, r"C:\god_ai\api_money_bot_complete\universal_harvester")
import requests  # noqa: E402

with open(r"d:\omniroute-monetizer\state\hf_experiment_mail.json") as f:
    mail = json.load(f)

token = mail["mail_tm_token"]
headers = {"Authorization": f"Bearer {token}"}

deadline = time.time() + 180
found = None
while time.time() < deadline:
    r = requests.get("https://api.mail.tm/messages", headers=headers, timeout=30)
    msgs = r.json().get("hydra:member", []) if r.status_code == 200 else []
    print(f"[{int(time.time())}] {len(msgs)} message(s)")
    for m in msgs:
        print("  from:", m.get("from", {}).get("address"), "| subject:", m.get("subject"))
        if "huggingface" in (m.get("subject", "") + m.get("from", {}).get("address", "")).lower() or "hugging" in m.get("subject", "").lower():
            found = m
            break
    if found:
        break
    time.sleep(10)

if not found:
    print("NO HF email arrived within 180s")
    sys.exit(1)

# fetch full message
r = requests.get(f"https://api.mail.tm/messages/{found['id']}", headers=headers, timeout=30)
full = r.json()
html = full.get("html") or []
text = full.get("text") or ""
body = "\n".join(html) if html else text

import re
links = re.findall(r'https?://[^\s"\'<>]+', body)
verify_links = [l for l in links if "huggingface" in l]
print("\n--- verification links ---")
for l in verify_links[:10]:
    print(l)

out = {
    "message_id": found["id"],
    "subject": found.get("subject"),
    "from": found.get("from", {}).get("address"),
    "links": verify_links,
    "text_preview": text[:500],
}
with open(r"d:\omniroute-monetizer\state\hf_verify_email.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nsaved to state/hf_verify_email.json")
