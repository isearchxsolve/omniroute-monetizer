"""Open the same seats from :9222 into :9223, :9224, :9225 using a shared URL list."""
import json, sys, time, urllib.request, urllib.parse

SEATS_PORT = 9222
TARGET_PORTS = [9223, 9224, 9225]
PROFILE_NAMES = {9223: "niloy", 9224: "seat2", 9225: "seat3"}

def get_tabs(port):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  Error getting tabs from port {port}: {e}")
        return []

# Get current seats from providers profile
print(f"Reading seats from :{SEATS_PORT}...")
seats = get_tabs(SEATS_PORT)
seat_urls = []
for t in seats:
    url = t.get("url", "")
    if url.startswith(("http://", "https://")):
        seat_urls.append(url)
seat_urls = sorted(set(seat_urls))
print(f"Source (:{SEATS_PORT}): {len(seat_urls)} unique URLs")

if not seat_urls:
    print("ERROR: No source URLs found!")
    sys.exit(1)

# Save URL list for debugging
with open("_tmp_seat_urls.json", "w") as f:
    json.dump(seat_urls, f, indent=2)

for port in TARGET_PORTS:
    profile = PROFILE_NAMES[port]
    print(f"\n--- {profile} (:{port}) ---")
    existing = get_tabs(port)
    existing_urls = set(t.get("url","") for t in existing)
    
    new_count = 0
    skip_count = 0
    fail_count = 0
    for url in seat_urls:
        if url in existing_urls:
            skip_count += 1
            continue
        try:
            encoded = urllib.parse.quote(url, safe=':/?=&%')
            endpoint = f"http://127.0.0.1:{port}/json/new?{encoded}"
            req = urllib.request.Request(endpoint, method="PUT")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
            new_count += 1
            if new_count % 10 == 0:
                print(f"  Opened {new_count}...")
        except Exception as e:
            fail_count += 1
        time.sleep(0.05)
    
    total_pages = len([t for t in get_tabs(port) if t.get("url","").startswith(("http://","https://"))])
    print(f"  {profile}: {new_count} opened, {skip_count} skipped (already present), {fail_count} failed")
    print(f"  Total HTTP(S) pages now: {total_pages}")

print("\nDone.")
