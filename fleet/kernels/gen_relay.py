import json
import os

def make_cell(source_lines):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source_lines}

def make_notebook(cells):
    return {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
            "accelerator": "none"
        },
        "cells": cells
    }

RELAY_CODE = r'''
# OMNIROUTE RELAY -- the new door, runs on Kaggle CPU. Laptop OUT of delivery path.
# Endpoints (token GOLD24):
#   GET  /health?token=            -> {"ok": true}
#   POST /say?token=  {body,text}  -> append message to ledger(body)
#   GET  /say?token=&body=X&limit= -> {"orders":[...]} newest-last for body X
#   POST /relay-url (no auth)      -> internal: publish helper
import os, json, time, threading, subprocess, re, base64, urllib.request
from collections import defaultdict

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn"])
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn

TOK = "GOLD24"
GH_TOKEN = "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"
GH_REPO = "isearchxsolve/omniroute-monetizer"
LEDGER = defaultdict(list)   # body -> [ {at, text} ]
LOCK = threading.Lock()

app = FastAPI()

@app.get("/health")
def health(token: str = ""):
    if token != TOK:
        return JSONResponse({"ok": False, "err": "bad token"}, status_code=403)
    return {"ok": True, "service": "omniroute-relay", "bodies": list(LEDGER.keys()),
            "ts": time.time()}

@app.post("/say")
async def say_post(request: Request, token: str = ""):
    if token != TOK:
        return JSONResponse({"ok": False}, status_code=403)
    data = await request.json()
    body = str(data.get("body", "KILO"))[:64]
    text = str(data.get("text", ""))[:20000]
    with LOCK:
        LEDGER[body].append({"at": time.time(), "text": text})
        LEDGER[body] = LEDGER[body][-2000:]
    return {"ok": True, "queued": len(LEDGER[body])}

@app.get("/say")
def say_get(token: str = "", body: str = "KILO", limit: int = 20):
    if token != TOK:
        return JSONResponse({"ok": False}, status_code=403)
    with LOCK:
        orders = LEDGER.get(body, [])[-int(limit):]
    return {"orders": orders, "count": len(orders)}

def publish_url(url):
    api = f"https://api.github.com/repos/{GH_REPO}/contents/relay-url.txt"
    hdrs = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github+json",
            "User-Agent": "kaggle-relay"}
    sha = None
    try:
        req = urllib.request.Request(api, headers=hdrs)
        sha = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("sha")
    except Exception:
        sha = None
    body = {"message": "relay url update", "content": base64.b64encode(url.encode()).decode()}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdrs, method="PUT")
    urllib.request.urlopen(req, timeout=20).read()
    print(">>> RELAY PUBLIC URL PUBLISHED:", url, flush=True)

# install cloudflared
CF = "/usr/local/bin/cloudflared"
if not os.path.exists(CF):
    subprocess.run(["wget", "-q", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "-O", CF], check=True)
    subprocess.run(["chmod", "+x", CF], check=True)
print("cloudflared ready", flush=True)

def run_relay():
    uvicorn.run(app, host="0.0.0.0", port=8788, log_level="warning")

t = threading.Thread(target=run_relay, daemon=True)
t.start()
time.sleep(5)
print("RELAY listening on 8788", flush=True)

def run_tunnel():
    proc = subprocess.Popen([CF, "tunnel", "--url", "http://localhost:8788", "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            publish_url(m.group(0))

t2 = threading.Thread(target=run_tunnel, daemon=True)
t2.start()
time.sleep(20)

# self-test + keep-alive
import urllib.request as _u
beat = 0
while True:
    try:
        r = _u.urlopen("http://127.0.0.1:8788/health?token=" + TOK, timeout=5)
        if beat % 30 == 0:
            print(f"[RELAY-HEARTBEAT] beat={beat} status={r.status}", flush=True)
    except Exception as e:
        print(f"[RELAY-ERR] {e}", flush=True)
    beat += 1
    time.sleep(60)
'''

cells = [
    make_cell(["# OmniRoute Relay -- the new permanent-ish door on Kaggle CPU\n", RELAY_CODE]),
]

nb = make_notebook(cells)

d = r"C:\kaggle\working\kaggle_notebooks\omniroute-relay"
os.makedirs(d, exist_ok=True)

with open(os.path.join(d, "omniroute-relay.ipynb"), "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
print("Wrote notebook")

meta = {
    "id": "isearchxsolve/omniroute-relay",
    "title": "Omniroute relay",
    "code_file": "omniroute-relay.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": False,
    "enable_internet": True,
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": [],
    "model_sources": []
}
with open(os.path.join(d, "kernel-metadata.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print("Wrote kernel-metadata.json")

with open(os.path.join(d, "omniroute-relay.ipynb"), encoding="utf-8") as f:
    json.load(f)
print("Valid JSON - relay code len =", len(RELAY_CODE))
