"""scratch_seat_shapes.py — compare the two grok seat files' structure (no secret values printed)."""
import sys, json, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sec = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
for name in sorted(p.name for p in sec.glob("session_grok*.json")):
    d = json.loads((sec / name).read_text(encoding="utf-8-sig"))
    print(f"\n=== {name} ===")
    for k, v in d.items():
        if k == "cookie_header":
            print(f"  {k}: <{len(v)} chars>")
        elif k == "recorded_ws":
            print(f"  {k}: url={v.get('url','')[:60]} sent={len(v.get('frames_sent',[]))} recv={len(v.get('frames_received',[]))} status={v.get('response_status')}")
        elif isinstance(v, (dict, list)):
            print(f"  {k}: {json.dumps(v)[:150]}")
        else:
            print(f"  {k}: {v!r}")
print("\n=== all grok-related seats ===")
for p in sorted(sec.glob("session_*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(p.name, "PARSE ERR", e); continue
    if "grok" in (d.get("host") or p.name).lower():
        print(f"  {p.name}: host={d.get('host')} modality={d.get('modality')} runtime={d.get('runtime')} "
              f"rec_ex={bool(d.get('recorded_exchange'))} rec_job={bool(d.get('recorded_job'))} "
              f"rec_ws={bool(d.get('recorded_ws'))} chrome={bool(d.get('chrome'))} cookie={len(d.get('cookie_header') or '')}")
