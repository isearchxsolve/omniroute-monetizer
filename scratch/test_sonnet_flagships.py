import sqlite3
import requests
import json
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Re-enable the user's primary OAuth accounts: windsurf, trae, cline, antigravity (kunal.colab)
providers_to_enable = ["windsurf", "trae", "cline", "clinepass", "antigravity", "codex", "ainative"]
for p in providers_to_enable:
    c.execute("UPDATE provider_connections SET is_active = 1 WHERE provider = ?", (p,))
    print(f"Re-enabled provider: {p}")

conn.commit()
conn.close()

# Now test specific Sonnet and flagship models with streaming
test_flagships = [
    # Windsurf models
    ("windsurf", "claude-sonnet-4.6"),
    ("windsurf", "claude-sonnet-4.5"),
    ("windsurf", "claude-opus-4.7-max"),
    ("windsurf", "swe-1.6"),
    
    # AINative models
    ("ainative", "claude-sonnet-4-5"),
    ("ainative", "claude-opus-4"),
    ("ainative", "deepseek-r1"),
    
    # Trae / Clinepass / Codex models
    ("clinepass", "claude-3-5-sonnet-20241022"),
    ("codex", "gpt-4o"),
    
    # Direct alias tests
    ("", "claude-sonnet-4.6"),
    ("", "claude-sonnet-4.5"),
]

print("\n=== TESTING FLAGSHIPS & SONNET MODELS LIVE ===")
for prov, m in test_flagships:
    model_str = f"{prov}/{m}" if prov else m
    payload = {
        "model": model_str,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": True
    }
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=8)
        chunks = []
        ttft = None
        for line in resp.iter_lines():
            if line:
                if ttft is None:
                    ttft = round(time.time() - start, 2)
                chunk_str = line.decode('utf-8', errors='replace')
                if chunk_str.startswith('data: ') and not chunk_str.startswith('data: [DONE]'):
                    chunks.append(chunk_str)
                    if len(chunks) >= 2:
                        break
        elapsed = round(time.time() - start, 2)
        if resp.status_code == 200 and chunks:
            print(f"[SUCCESS] {model_str:<35} | TTFT: {ttft}s | Total: {elapsed}s | Status: 200")
        else:
            print(f"[{resp.status_code}] {model_str:<35} | {elapsed}s | {resp.text[:80] if not chunks else chunks[0][:80]}")
    except Exception as e:
        print(f"[TIMEOUT/ERR] {model_str:<35} | {round(time.time()-start, 2)}s | {str(e)[:60]}")
