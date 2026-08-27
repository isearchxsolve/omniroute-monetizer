import json, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = Path(r"d:\omniroute-monetizer\state\secrets\session_chatx.json")
d = json.loads(p.read_text(encoding="utf-8-sig"))
d["runtime"] = "replay"
st = d.setdefault("status", {})
st["alive"] = True
st["reason"] = "ok"
st["graduated_at"] = int(time.time())
st["note"] = "graduated chrome-free via chatx_replay 2-leg stateless client (worklog #1115); LIVE verified answered Omni in 2.7s"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("graduated chatx: runtime=replay, alive=True")
print("keys:", list(d.keys()))
