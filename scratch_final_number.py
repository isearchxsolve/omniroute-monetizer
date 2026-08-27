"""scratch_final_number.py — compute the ground-truth final number: dispatchable seats by modality."""
import json, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")

SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
files = sorted(SECRETS.glob("session_*.json"))

chat, video, other = [], [], []
dispatchable_chat, dispatchable_video = [], []

for f in files:
    try:
        raw = json.loads(f.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"  UNREADABLE {f.name}: {e}")
        continue
    name = f.stem
    modality = raw.get("modality") or ("video" if "video" in name else "chat")
    has_exchange = bool(raw.get("recorded_exchange"))
    has_ws = bool(raw.get("recorded_ws"))
    has_job = bool(raw.get("recorded_job"))
    chrome = raw.get("chrome")
    host = raw.get("host", "")
    # dispatchability per session_pool: chrome decl OR known chrome host OR recorded bytes
    chrome_decl = bool(chrome) and chrome not in (False, "")
    disp = bool(has_exchange or has_ws or has_job or chrome_decl)
    row = (name, host, has_exchange, has_ws, has_job, chrome_decl, disp)
    if modality == "video":
        video.append(row)
        if disp: dispatchable_video.append(name)
    else:
        chat.append(row)
        if disp: dispatchable_chat.append(name)

print(f"=== CHAT SEATS: {len(chat)} total, {len(dispatchable_chat)} dispatchable ===")
for name, host, ex, ws, job, ch, disp in chat:
    kind = []
    if ex: kind.append("http")
    if ws: kind.append("ws")
    if ch: kind.append("chrome")
    print(f"  {'OK ' if disp else '-- '}{name:38s} host={host:28s} [{'+'.join(kind) or 'none'}]")

print(f"\n=== VIDEO SEATS: {len(video)} total, {len(dispatchable_video)} dispatchable ===")
for name, host, ex, ws, job, ch, disp in video:
    kind = []
    if job: kind.append("job")
    if ex: kind.append("http")
    if ch: kind.append("chrome")
    print(f"  {'OK ' if disp else '-- '}{name:38s} host={host:28s} [{'+'.join(kind) or 'none'}]")

print(f"\nFINAL NUMBER: {len(files)} seat files | chat {len(dispatchable_chat)}/{len(chat)} dispatchable | video {len(dispatchable_video)}/{len(video)} dispatchable")
print(f"TOTAL DISPATCHABLE: {len(dispatchable_chat) + len(dispatchable_video)}")
