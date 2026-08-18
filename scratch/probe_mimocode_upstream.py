"""Replicate mimocode bootstrap flow directly to probe upstream Xiaomi endpoint.
Evidence goal: find which model names the upstream actually accepts.
JWT never printed (T11)."""
import hashlib, platform, socket, getpass, json, requests

BASE = "https://api.xiaomimimo.com"
MARKER = "You are MiMoCode, an interactive CLI tool that helps users with software engineering tasks."

# Replicate generateFingerprint: sha256(hostname|platform|arch|cpu|username)
hostname = socket.gethostname()
plat = platform.system().lower()  # node os.platform() -> "win32"
if plat == "windows":
    plat = "win32"
arch = platform.machine().lower()  # node os.arch() -> "x64"
if arch in ("amd64", "x86_64"):
    arch = "x64"
cpu = "unknown-cpu"
try:
    cpu = platform.processor().strip() or "unknown-cpu"
except Exception:
    pass
username = getpass.getuser()
fp = hashlib.sha256(f"{hostname}|{plat}|{arch}|{cpu}|{username}".encode()).hexdigest()
print(f"fingerprint seed: {hostname}|{plat}|{arch}|{cpu[:30]}|{username}")

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

# 1. Bootstrap
r = s.post(f"{BASE}/api/free-ai/bootstrap", json={"client": fp}, timeout=20)
print("bootstrap:", r.status_code, r.text[:150])
if r.status_code != 200:
    raise SystemExit("bootstrap failed")
jwt = r.json().get("jwt")
print("jwt acquired:", bool(jwt), "len", len(jwt) if jwt else 0)

# 2. Probe model names
candidates = ["mimo-auto", "mimo-v2.5", "mimo-v2.5-pro", "MiMo-V2.5", "MiMo-V2.5-Pro",
              "XiaomiMiMo/MiMo-V2.5", "XiaomiMiMo/MiMo-V2.5-Pro", "mimo", "auto",
              "mimo-code", "mimocode", "mimo-v2", "mimo-v1"]
for m in candidates:
    body = {
        "model": m,
        "messages": [
            {"role": "system", "content": MARKER},
            {"role": "user", "content": "Reply with exactly: OK"},
        ],
        "max_tokens": 60,
        "stream": False,
    }
    try:
        rr = s.post(f"{BASE}/api/free-ai/openai/chat", json=body, timeout=60,
                    headers={"Authorization": f"Bearer {jwt}", "X-Mimo-Source": "mimocode-cli-free"})
        txt = rr.text[:180].replace("\n", " ")
        print(f"  {m:30s} -> {rr.status_code} {txt}")
        if rr.status_code == 200:
            print("  *** FOUND WORKING MODEL:", m)
            break
    except Exception as e:
        print(f"  {m:30s} -> EXC {e}")
