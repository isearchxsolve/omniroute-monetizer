"""Diagnose HF signup state: (1) is mail.tm token alive? (2) any messages? (3) does the HF account exist?"""
import json, sys
import requests

with open(r"d:\omniroute-monetizer\state\hf_experiment_mail.json") as f:
    mail = json.load(f)
with open(r"d:\omniroute-monetizer\state\hf_experiment_account.json") as f:
    acct = json.load(f)

# ---- 1. mail.tm token health ----
r = requests.get("https://api.mail.tm/me",
                 headers={"Authorization": f"Bearer {mail['mail_tm_token']}"}, timeout=30)
print(f"[mail.tm] GET /me with stored token -> {r.status_code}")
token = mail["mail_tm_token"]
if r.status_code != 200:
    print("  token dead/expired — re-authenticating with password")
    r2 = requests.post("https://api.mail.tm/token",
                       json={"address": mail["email"], "password": mail["mail_tm_password"]},
                       timeout=30)
    print(f"  POST /token -> {r2.status_code}")
    if r2.status_code == 200:
        token = r2.json()["token"]
        mail["mail_tm_token"] = token
        with open(r"d:\omniroute-monetizer\state\hf_experiment_mail.json", "w") as f:
            json.dump(mail, f, indent=2)
        print("  refreshed token saved")
    else:
        print("  re-auth FAILED:", r2.text[:200])

# ---- 2. messages ----
r = requests.get("https://api.mail.tm/messages",
                 headers={"Authorization": f"Bearer {token}"}, timeout=30)
print(f"[mail.tm] GET /messages -> {r.status_code}")
if r.status_code == 200:
    msgs = r.json().get("hydra:member", [])
    print(f"  {len(msgs)} message(s)")
    for m in msgs:
        print("   from:", m.get("from", {}).get("address"), "| subj:", m.get("subject"),
              "| at:", m.get("createdAt"))

# ---- 3. does the HF account exist? try login ----
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"})
r = s.post("https://huggingface.co/login",
           data={"username": acct["email"], "password": acct["password"]},
           allow_redirects=False, timeout=30)
print(f"\n[HF] POST /login -> {r.status_code} location={r.headers.get('location')!r}")
if r.status_code == 200:
    body = r.text
    for marker in ["Invalid username or password", "verify your email", "Confirm your email",
                   "email", "captcha", "error"]:
        if marker.lower() in body.lower():
            # extract a snippet around the marker
            i = body.lower().find(marker.lower())
            print(f"  marker {marker!r}: ...{body[max(0,i-80):i+120]!r}...")
            break
cookies = {c.name for c in s.cookies}
print("  cookies set:", sorted(cookies)[:10])
