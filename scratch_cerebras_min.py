import json, sys
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient
from curl_cffi.requests import Session as CCSession

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
c = UniversalSessionClient(str(SEATDIR / "session_cerebras_inference_chat.json"))
s = CCSession(impersonate="chrome")

def fire(body_obj, label):
    r = s.request("POST", c.url, headers=c.headers, data=json.dumps(body_obj).encode(), timeout=60)
    print(f"  [{label}] status={r.status_code} body[:200]={r.text[:200]!r}")
    return r

# Test 1: minimal single-turn, same model
fire({"messages":[{"role":"user","content":"Reply exactly one word: Omni."}],
      "model":"gemma-4-31b","stream":False,"temperature":0.7,"top_p":0.9}, "minimal same-model")

# Test 2: minimal, no stream
fire({"messages":[{"role":"user","content":"Reply exactly one word: Omni."}],
      "model":"gemma-4-31b"}, "minimal no-params")

# Test 3: try a known cerebras model
for m in ["llama-3.3-70b", "llama3.1-8b", "qwen-3-32b"]:
    fire({"messages":[{"role":"user","content":"Reply exactly one word: Omni."}],
          "model":m}, f"model={m}")
