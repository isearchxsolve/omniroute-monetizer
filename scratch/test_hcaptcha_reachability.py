"""Test reachability of hCaptcha asset/API domains from this machine."""
import socket
import urllib.request

domains = [
    "hcaptcha.com",
    "assets.hcaptcha.com",
    "newassets.hcaptcha.com",
    "js.hcaptcha.com",
    "api.hcaptcha.com",
    "imgs.hcaptcha.com",
    "huggingface.co",
]

print("=== DNS resolution ===")
for d in domains:
    try:
        ip = socket.gethostbyname(d)
        print(f"  {d}: {ip}")
    except Exception as e:
        print(f"  {d}: DNS FAIL -> {e}")

print("\n=== HTTPS reachability ===")
for d in ["https://hcaptcha.com", "https://js.hcaptcha.com", "https://newassets.hcaptcha.com", "https://huggingface.co"]:
    try:
        req = urllib.request.Request(d, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  {d}: HTTP {r.status}")
    except Exception as e:
        print(f"  {d}: FAIL -> {e}")
