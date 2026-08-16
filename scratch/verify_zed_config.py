"""Verify new Zed settings.json + tool_choice:'auto' works on the new default model."""
import json, os, sys, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"

# 1. JSON validity + key fields
ZED = os.path.join(os.environ["APPDATA"], "Zed", "settings.json")
with open(ZED, encoding="utf-8") as f:
    zed = json.load(f)
omni = zed["language_models"]["openai_compatible"]["OmniRoute"]
print("JSON valid: True")
print("api_url:", omni["api_url"])
print("default_model:", zed["agent"]["default_model"])
print("models:", len(omni["available_models"]))
print("TokenRouter preserved:", "TokenRouter" in zed["language_models"]["openai_compatible"])
print("agent permissions preserved:", "tool_permissions" in zed.get("agent", {}))

# 2. tool_choice:"auto" test on the new default (Zed Agent attaches tools every turn)
body = {
    "model": "auto/best-coding",
    "messages": [{"role": "user", "content": "What is 2+2? Use the calculator tool."}],
    "max_tokens": 200, "stream": False,
    "tools": [{"type": "function", "function": {
        "name": "calculator", "description": "Evaluate a math expression",
        "parameters": {"type": "object", "properties": {"expr": {"type": "string"}}, "required": ["expr"]}}}],
    "tool_choice": "auto",
}
t0 = time.time()
r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=90)
dt = time.time() - t0
print(f"\ntool_choice:auto on auto/best-coding -> {r.status_code} in {dt:.1f}s")
if r.status_code == 200:
    j = r.json()
    msg = j["choices"][0]["message"]
    tc = msg.get("tool_calls")
    print("  tool_calls:", json.dumps(tc)[:200] if tc else "(none — plain text reply)")
    print("  content:", (msg.get("content") or "")[:80])
else:
    print("  ", r.text[:300])
