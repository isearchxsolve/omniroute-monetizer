"""scratch_final_number2.py — final number via the pool's REAL dispatch (_client_for)."""
import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")

import session_pool as sp

SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
files = sorted(SECRETS.glob("session_*.json"))

chat_ok, video_ok, dead = [], [], []
for f in files:
    name = f.stem
    try:
        ps = sp.PooledSession(f)
    except Exception as e:
        dead.append((name, f"load-error: {e}"))
        continue
    disp = ps.dispatchable
    if not disp and ps.client_cls is None:
        dead.append((name, "no client_cls"))
        continue
    modality = ps.modality or ("video" if "video" in name else "chat")
    if disp:
        (video_ok if modality == "video" else chat_ok).append(name)
    else:
        dead.append((name, "not dispatchable"))

print(f"CHAT dispatchable via pool: {len(chat_ok)}")
for n in chat_ok: print("  OK", n)
print(f"\nVIDEO dispatchable via pool: {len(video_ok)}")
for n in video_ok: print("  OK", n)
print(f"\nNOT dispatchable: {len(dead)}")
for n, why in dead: print("  --", n, "|", why)
print(f"\nFINAL NUMBER: {len(files)} seats | {len(chat_ok)} chat + {len(video_ok)} video = {len(chat_ok)+len(video_ok)} dispatchable")
