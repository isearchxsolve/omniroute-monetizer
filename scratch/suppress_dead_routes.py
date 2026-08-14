import os
import requests

BASE_URL = "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "Keross@321")

def main():
    print("Logging into OmniRoute API...")
    s = requests.Session()
    try:
        r = s.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Failed to login: {e}")
        return

    print("Fetching connections...")
    try:
        r = s.get(f"{BASE_URL}/api/providers", timeout=10)
        data = r.json()
        connections = data.get("connections", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"Failed to fetch connections: {e}")
        return

    dead_providers = ["codex", "openai"]
    for c in connections:
        cid = c.get("id")
        provider = c.get("provider")
        if provider in dead_providers or cid in dead_providers:
            if c.get("isActive", False):
                print(f"Suppressing dead route: {provider} ({cid})...")
                try:
                    s.put(f"{BASE_URL}/api/providers/{cid}", json={"isActive": False}, timeout=10)
                    print(f"  -> Successfully suppressed {provider}")
                except Exception as e:
                    print(f"  -> Failed to suppress {provider}: {e}")
            else:
                print(f"Dead route {provider} is already suppressed.")

if __name__ == "__main__":
    main()
