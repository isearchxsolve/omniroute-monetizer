import requests
import json
import time

URL = 'http://localhost:20128/v1/chat/completions'
HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer <REDACTED>'
}

def test_prompt(model, prompt):
    print("=" * 60)
    print(f"[*] Prompting Target: {model}")
    print(f"[*] Prompt: {prompt}")
    print("=" * 60)
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 350,
        'temperature': 0.2
    }
    t0 = time.time()
    resp = requests.post(URL, headers=HEADERS, json=payload, timeout=30)
    elapsed = time.time() - t0
    print(f"[+] HTTP Status: {resp.status_code} ({elapsed:.2f}s)")
    
    text = resp.text
    full_content = ""
    model_used = "Unknown"
    
    if text.startswith('data:'):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('data:') and not line.endswith('[DONE]'):
                raw_json = line[5:].strip()
                try:
                    chunk = json.loads(raw_json)
                    model_used = chunk.get('model', model_used)
                    choices = chunk.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        full_content += delta.get('content', '')
                except Exception:
                    pass
    else:
        try:
            data = resp.json()
            model_used = data.get('model', model_used)
            choices = data.get('choices', [])
            if choices:
                full_content = choices[0].get('message', {}).get('content', '')
        except Exception:
            full_content = text[:400]
            
    print(f"[+] Actual Engine Resolved: {model_used}")
    print(f"[+] Model Output:\n{full_content.strip()}")
    print("\n")

if __name__ == '__main__':
    test_prompt('auto/best-coding', 'Write a clean Python class for an LRU Cache with get and put methods.')
    test_prompt('frontier', 'Explain the Byzantine Generals Problem in 3 concise bullet points.')
    test_prompt('fusion-coder', 'Write a Python generator function to stream Fibonacci numbers.')
