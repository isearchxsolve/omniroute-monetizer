"""READ-ONLY digen token-liveness check: credit/remain + queue/list. No job submission.
Also checks which seat files exist for digen and their dispatch state.
"""
import io, json, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))

import requests
from digen_session_replay import DigenSessionClient

sec = pathlib.Path("state/secrets")
for name in ("session_digen_ai", "session_video_digen"):
    f = sec / (name + ".json")
    print("=" * 60)
    print("SEAT FILE:", name, "exists:", f.exists())
    if not f.exists():
        continue
    raw = json.loads(f.read_text(encoding="utf-8-sig"))
    print("  host:", raw.get("host"), "| modality:", raw.get("modality"),
          "| runtime:", raw.get("runtime"), "| chrome decl:", bool(raw.get("chrome")))
    st = raw.get("status") or {}
    print("  status:", {k: v for k, v in st.items() if k != "cookie_header"} if isinstance(st, dict) else st)
    job = raw.get("recorded_job") or {}
    exs = job.get("exchanges") or []
    print("  recorded_job exchanges:", len(exs))
    has_token = any("Digen-Token" in (e.get("request_headers") or {}) for e in exs)
    print("  has Digen-Token in recording:", has_token)
    if not has_token:
        continue
    try:
        client = DigenSessionClient(secret=f)
        # read-only: credit remain
        r = requests.get("https://api.digen.ai/v1/credit/remain", headers=client._headers, timeout=15)
        print("  credit/remain:", r.status_code, r.text[:200])
        # read-only: queue list (status=3 = completed)
        r2 = requests.get("https://api.digen.ai/v1/queue/list?page=0&pageSize=3&status=3",
                          headers=client._headers, timeout=15)
        print("  queue/list:", r2.status_code)
        if r2.status_code == 200:
            jobs = (r2.json().get("data") or {}).get("list") or []
            print("    completed jobs visible:", len(jobs))
            if jobs:
                j0 = jobs[0]
                vu = j0.get("videoUrl") or j0.get("videoURLV1") or ""
                print("    newest job id:", j0.get("id"), "| has videoUrl:", bool(vu))
    except Exception as e:
        print("  CLIENT ERROR:", type(e).__name__, str(e)[:200])
