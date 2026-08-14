import requests
import json
import concurrent.futures
import time
import os

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3].rstrip("/")
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "Keross@321")

def main():
    print("=== OmniRoute Optimizer: Dead Route Suppression ===")
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    r.raise_for_status()
    
    token = r.cookies.get("auth_token") or r.json().get("token")
    if token: s.cookies.set("auth_token", token)
    
    print("Fetching connections...")
    r = s.get(f"{BASE_URL}/api/providers", timeout=15)
    connections = r.json().get("connections", [])
    print(f"Total connections: {len(connections)}")
    
    def check_and_suppress(conn):
        cid = conn.get("id")
        name = conn.get("name") or conn.get("provider")
        try:
            res = s.post(f"{BASE_URL}/api/providers/{cid}/test", timeout=30)
            valid = res.json().get("valid", False)
            
            # Suppress dead route or re-enable live route
            is_active = conn.get("isActive", True)
            if is_active != valid:
                conn_copy = dict(conn)
                conn_copy["isActive"] = valid
                s.put(f"{BASE_URL}/api/providers/{cid}", json={"connection": conn_copy}, timeout=15)
                print(f"[{'OK' if valid else 'DEAD'}] {name}: isActive -> {valid}")
                return (name, valid, True)
            else:
                return (name, valid, False)
        except Exception as e:
            print(f"[ERR] {name}: {e}")
            return (name, False, False)
            
    print("Testing connections concurrently...")
    changed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for name, valid, changed in executor.map(check_and_suppress, connections):
            if changed: changed_count += 1
            
    print(f"Finished. Updated {changed_count} connections.")

if __name__ == "__main__":
    main()
