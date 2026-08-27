"""Check for live signed-in tabs for the 3 expired seats (groq/cerebras/gemini)
so we can harvest fresh credentials. Zero cost: CDP /json only."""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NEEDLES = {
    "api.groq.com": ["groq.com", "console.groq"],
    "chat.cerebras.ai": ["cerebras"],
    "gemini.google.com": ["gemini.google.com"],
}

def tabs_on(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
            return [t for t in json.loads(r.read()) if t.get("type") == "page"]
    except Exception:
        return []

all_tabs = []
for port in (9222, 9223, 9224, 9225):
    for t in tabs_on(port):
        all_tabs.append((port, t.get("url", ""), t.get("title", "")[:40]))

for seat, needles in NEEDLES.items():
    print(f"\n{seat}:")
    hits = [(p, u, t) for (p, u, t) in all_tabs
            if any(n in u for n in needles)]
    if hits:
        for p, u, t in hits:
            print(f"   port {p}  {u[:70]}")
    else:
        print("   NO LIVE TAB")
