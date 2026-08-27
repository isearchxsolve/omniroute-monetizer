import sys, json, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
VIDEO = [p for p in SECRETS.glob("session_video_*.json")]

print(f"{'file':42} {'recorded_job':12} {'runtime':10} {'cookie_len':10} {'exchanges':9} status")
for p in sorted(VIDEO):
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"{p.name:42} READ_ERR {e}")
        continue
    rj = d.get("recorded_job")
    rj_kind = "none"
    if isinstance(rj, dict):
        ex = rj.get("exchanges") or []
        rj_kind = f"dict({len(ex)}ex)"
    elif isinstance(rj, list):
        rj_kind = f"list({len(rj)})"
    elif rj:
        rj_kind = type(rj).__name__
    runtime = d.get("runtime") or "-"
    ch = d.get("cookie_header") or ""
    st = (d.get("status") or {})
    alive = st.get("alive") if isinstance(st, dict) else st
    print(f"{p.name:42} {rj_kind:12} {str(runtime):10} {len(ch):<10} {str(alive):9}")
