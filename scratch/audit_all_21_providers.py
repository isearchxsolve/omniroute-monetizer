import sqlite3
import requests
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# The 21 Connected Providers from the UI
connected_providers = [
    "kimi-coding",
    "amazon-q",
    "antigravity",
    "cline",
    "clinepass",
    "github",
    "grok-cli",
    "kilocode",
    "kiro",
    "codex",
    "qoder",
    "windsurf",
    "zai-web",
    "lmarena",
    "agnes",
    "ainative",
    "aion",
    "alibaba",
    "nara",
    "cerebras",
    "cloudflare-ai",
    "cohere"
]

print("=" * 80, flush=True)
print("COMPREHENSIVE AUDIT OF ALL 21 CONNECTED PROVIDERS FROM UI", flush=True)
print("=" * 80, flush=True)

# 1. First ensure all 21 are set to is_active = 1 in database
for p in connected_providers:
    c.execute("UPDATE provider_connections SET is_active = 1 WHERE provider = ?", (p,))
conn.commit()

provider_models = {}
for p in connected_providers:
    c.execute("SELECT id, name, auth_type, is_active, length(api_key), length(access_token) FROM provider_connections WHERE provider = ?", (p,))
    rows = c.fetchall()
    
    # Get all models for this provider from key_value
    models = []
    for r in rows:
        pid = r[0]
        c.execute("SELECT value FROM key_value WHERE key = ? OR key = ?", (f"{p}:{pid}", pid))
        kv = c.fetchone()
        if kv:
            try:
                m_list = json.loads(kv[0])
                for item in m_list:
                    mid = item.get('id') if isinstance(item, dict) else item
                    if mid and mid not in models:
                        models.append(mid)
            except:
                pass
    provider_models[p] = {"connections": rows, "models": models}

conn.close()

# Print inventory
for p, data in provider_models.items():
    conns = data["connections"]
    models = data["models"]
    print(f"\n[{p.upper()}] Connections: {len(conns)} | Cataloged Models: {len(models)}", flush=True)
    for c_info in conns:
        print(f"   Connection ID: {c_info[0][:8]} | Name: {c_info[1]} | Auth: {c_info[2]} | Active: {c_info[3]}", flush=True)
    if models:
        print(f"   Top models: {models[:6]}", flush=True)

# 2. Live Probe of Top Models for EACH of the 21 Providers
print("\n" + "=" * 80, flush=True)
print("LIVE TESTING TOP MODELS FOR EACH OF THE 21 PROVIDERS", flush=True)
print("=" * 80, flush=True)

results = {}

for p in connected_providers:
    models = provider_models[p]["models"]
    if not models:
        # If no models stored in KV, try generic or default
        models = [f"{p}-default", "default"]
    
    # Test first 2 models for this provider
    test_subset = models[:2]
    results[p] = []
    
    for m in test_subset:
        model_name = f"{p}/{m}" if not m.startswith(f"{p}/") else m
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "1+1="}],
            "max_tokens": 5,
            "stream": True
        }
        start = time.time()
        try:
            resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=6)
            chunks = []
            ttft = None
            for line in resp.iter_lines():
                if line:
                    if ttft is None:
                        ttft = round(time.time() - start, 2)
                    chunk_str = line.decode('utf-8', errors='replace')
                    if chunk_str.startswith('data: ') and not chunk_str.startswith('data: [DONE]'):
                        try:
                            d = json.loads(chunk_str[6:])
                            delta = d.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if delta:
                                chunks.append(delta)
                        except:
                            pass
                    if len(chunks) >= 2:
                        break
            elapsed = round(time.time() - start, 2)
            if resp.status_code == 200:
                reply = "".join(chunks).strip()
                status_str = f"PASS (TTFT: {ttft}s, Reply: '{reply[:20]}')"
                print(f"  [PASS] {model_name:<45} | Status: 200 | TTFT: {ttft}s | Reply: '{reply[:20]}'", flush=True)
                results[p].append((model_name, "PASS", ttft, reply))
            else:
                err_text = resp.text[:70].replace('\n', ' ')
                print(f"  [FAIL] {model_name:<45} | Status: {resp.status_code} | Err: {err_text}", flush=True)
                results[p].append((model_name, f"FAIL ({resp.status_code})", elapsed, err_text))
        except Exception as e:
            err_msg = str(e)[:60]
            print(f"  [ERR]  {model_name:<45} | Timeout/Error: {err_msg}", flush=True)
            results[p].append((model_name, "TIMEOUT", 6.0, err_msg))

print("\n" + "=" * 80, flush=True)
print("AUDIT SUMMARY TABLE", flush=True)
print("=" * 80, flush=True)
for p, res in results.items():
    working = [r for r in res if r[1] == "PASS"]
    status_tag = "ACTIVE & WORKING" if working else "FAILED / TIMEOUT"
    print(f"Provider: {p:<16} | Status: {status_tag:<18} | Tested: {len(res)} | Working: {len(working)}", flush=True)
