import sqlite3
import requests
import json
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

providers = ["qoder", "lmarena", "codex", "grok-cli", "amazon-q"]

print("--- DEEP DIVE RCA ---")

for p in providers:
    print(f"\n[{p.upper()}] Database Connections:")
    c.execute("SELECT id, name, is_active, auth_type FROM provider_connections WHERE provider = ?", (p,))
    rows = c.fetchall()
    
    active_conns = []
    for r in rows:
        cid, name, active, auth = r
        print(f"  - ID: {cid[:8]} | Name: {name} | Active: {active} | Auth: {auth}")
        if active:
            active_conns.append(cid)
            
    print(f"\n[{p.upper()}] Pinging Inference for each active connection:")
    
    # Target model for each provider
    models = {
        "qoder": "qoder/qwen3.7-max",
        "lmarena": "lmarena/claude-sonnet-5",
        "codex": "codex/gpt-5.6-sol",
        "grok-cli": "grok-cli/grok-4.5",
        "amazon-q": "amazon-q/amazon-q"
    }
    
    model = models.get(p)
    
    for cid in active_conns:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Ping!"}],
            "stream": False
        }
        headers = {
            "x-omniroute-connection": cid
        }
        
        start = time.time()
        try:
            resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, headers=headers, timeout=30)
            elapsed = time.time() - start
            if resp.status_code == 200:
                print(f"  -> Connection {cid[:8]} [SUCCESS] in {elapsed:.2f}s")
            else:
                print(f"  -> Connection {cid[:8]} [FAIL {resp.status_code}] in {elapsed:.2f}s | Error: {resp.text}")
        except Exception as e:
             print(f"  -> Connection {cid[:8]} [ERROR] {e}")

conn.close()
