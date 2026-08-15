import requests
import json
import time

BASE_URL = "http://localhost:20128"
V1_URL = f"{BASE_URL}/v1"
API_KEY = "sk-2daf4dd6d1e45047-d60156-541a3aeb"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

combos_to_test = [
    "auto/pro-reasoning",
    "auto/pro-chat",
    "auto/best-coding",
    "auto/best-reasoning",
    "auto/best-chat",
    "frontier",
    "fusion-coder"
]

print("--- Testing Repaired Combos ---")
for combo in combos_to_test:
    t0 = time.time()
    try:
        r = requests.post(
            f"{V1_URL}/chat/completions",
            headers=headers,
            json={
                "model": combo,
                "messages": [{"role": "user", "content": "Respond with OK"}],
                "max_tokens": 10,
                "temperature": 0
            },
            timeout=25
        )
        elapsed = round(time.time() - t0, 3)
        if r.status_code == 200:
            print(f"[OK 200] {combo} ({elapsed}s)")
        else:
            print(f"[FAIL {r.status_code}] {combo} ({elapsed}s): {r.text[:120]}")
    except Exception as e:
        print(f"[TIMEOUT/ERR] {combo}: {e}")
