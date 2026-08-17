#!/usr/bin/env python3
"""Compare: direct HTTP (known-good) vs OpenAILike client for the same key."""
import json
import os
import urllib.request
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
MODELS_JSON = os.path.join(WORKDIR, "models.json")


def redact(k):
    return k[:6] + "****" + k[-4:] if k and len(k) > 12 else "****"


with open(MODELS_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)
entry = data["items"]["tokenrouter-qwen38max-key1"]
args = {}
for opt in entry["llama_index"]["args"]:
    args[opt["name"]] = opt["value"]

key = args["api_key"]
base = args["api_base"]
model = args["model"]
print("key:", redact(key), "len:", len(key))

# --- Direct HTTP (the method that worked before) ---
url = base.rstrip("/") + "/chat/completions"
payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
}).encode()
req = urllib.request.Request(url, data=payload, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Bearer " + key)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode())
        print("[direct HTTP] status:", r.status)
        print("[direct HTTP] content:", repr(body["choices"][0]["message"]["content"]))
except Exception as e:
    print("[direct HTTP] ERROR:", e)

# --- OpenAI SDK client (what llama_index uses under the hood) ---
from openai import OpenAI
client = OpenAI(api_key=key, base_url=base)
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    print("[openai SDK] content:", repr(resp.choices[0].message.content))
except Exception as e:
    print("[openai SDK] ERROR:", e)
