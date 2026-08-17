"""Find where http://0.0.0.14/ is configured in the slim Chrome profile."""
import os, json

ROOT = r"d:\omniroute-chrome-profile"
NEEDLE = "0.0.0.14"
OUT = r"d:\omniroute-monetizer\scratch\ip_search.txt"

hits = []
# Only scan small JSON-ish config files, skip huge caches
candidate_names = {
    "Preferences", "Secure Preferences", "Local State",
    "Current Session", "Current Tabs", "Last Session", "Last Tabs",
    "Pinned Tabs", "Bookmarks", "History",
}
for dirpath, dirnames, filenames in os.walk(ROOT):
    # skip heavy dirs
    dirnames[:] = [d for d in dirnames if d not in
                   ("Cache", "Code Cache", "GPUCache", "Service Worker",
                    "IndexedDB", "File System", "blob_storage", "DawnCache",
                    "ShaderCache", "GraphiteDawnCache", "Storage", "Cache_Data")]
    for fn in filenames:
        if fn in candidate_names:
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 20_000_000:
                    continue
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = f.read()
                if NEEDLE in data:
                    # find context
                    idx = data.find(NEEDLE)
                    ctx = data[max(0, idx-80):idx+80].replace("\n", " ")
                    hits.append(f"{p}\n    ...{ctx}...")
            except Exception as e:
                hits.append(f"{p} ERROR {e}")

with open(OUT, "w", encoding="utf-8") as f:
    if hits:
        f.write(f"FOUND {len(hits)} file(s) containing {NEEDLE}:\n")
        f.write("\n".join(hits))
    else:
        f.write(f"no file contains {NEEDLE}\n")
print("done", len(hits))
