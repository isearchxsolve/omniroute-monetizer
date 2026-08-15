import sqlite3
import requests
import json
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, name, provider, is_active FROM provider_connections WHERE is_active = 1")
rows = c.fetchall()

providers_map = {}
for r in rows:
    cid, name, provider, active = r
    if provider not in providers_map:
        providers_map[provider] = []
    providers_map[provider].append(cid)

print("--- FETCHING REAL MODELS FOR EACH PROVIDER ---")

all_healthy_models = []

for provider, cids in providers_map.items():
    print(f"\n[{provider.upper()}]")
    
    # Try to fetch models using the first active connection
    cid = cids[0]
    headers = {"x-omniroute-connection": cid}
    
    try:
        resp = requests.get("http://localhost:20128/v1/models", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            model_ids = [m.get("id") for m in models]
            
            # Filter out junk model names (like 'quotas', 'plan', 'fetchedAt')
            real_models = [m for m in model_ids if m not in ['quotas', 'plan', 'message', 'fetchedAt', 'source', 'bankedResetCredits']]
            
            print(f"  Found {len(real_models)} real models. (e.g. {real_models[:3]})")
            
            # Let's test the first real model
            if real_models:
                test_model = real_models[0]
                # Fallback to a better model if the first one is weird
                for rm in real_models:
                    if any(x in rm.lower() for x in ['sonnet', 'gpt', 'qwen', 'claude', 'gemini', 'llama', 'mistral']):
                        test_model = rm
                        break
                        
                print(f"  Testing model: {test_model}...")
                
                payload = {
                    "model": test_model,
                    "messages": [{"role": "user", "content": "Ping!"}],
                    "stream": False,
                    "max_tokens": 5
                }
                
                start = time.time()
                chat_resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, headers=headers, timeout=20)
                elapsed = time.time() - start
                
                if chat_resp.status_code == 200:
                    print(f"  [PASS] {test_model} in {elapsed:.2f}s")
                    all_healthy_models.append({
                        "provider": provider,
                        "model_id": test_model,
                        "full_id": f"{provider}/{test_model}" if not test_model.startswith(f"{provider}/") else test_model
                    })
                else:
                    print(f"  [FAIL] {test_model} (HTTP {chat_resp.status_code}): {chat_resp.text[:100]}")
                    
        else:
            print(f"  [FAIL] Could not fetch models (HTTP {resp.status_code})")
    except Exception as e:
        print(f"  [ERROR] {e}")

print("\n--- FINAL HEALTHY MODELS ---")
for m in all_healthy_models:
    print(f"{m['provider']}: {m['full_id']}")

with open("D:/omniroute-monetizer/scratch/true_healthy_models.json", "w") as f:
    json.dump(all_healthy_models, f, indent=4)

conn.close()
