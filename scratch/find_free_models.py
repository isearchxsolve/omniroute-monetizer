import requests, json

BASE_URL = 'http://localhost:20128'
headers = {
    "Authorization": "Bearer any",
    "Content-Type": "application/json"
}

try:
    resp = requests.get(f"{BASE_URL}/v1/models", headers=headers, timeout=10)
    models = resp.json().get('data', [])
    
    free_candidates = []
    for m in models:
        mid = m['id'].lower()
        if 'free' in mid:
            free_candidates.append(m['id'])
            
    print(f"Found {len(free_candidates)} potential free models:")
    for f in free_candidates[:20]:
        print(f" - {f}")
        
except Exception as e:
    print(f"Error: {e}")
