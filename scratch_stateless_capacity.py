import sys, pathlib
sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
SE = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")

print("=== STATELESS VIDEO CAPACITY (free probes, zero spend) ===")
try:
    from rtst_api_client import RtstApiClient
    for n in ["session_rtst_ai", "session_rtst_ai_niloy", "session_rtst_ai_seat2", "session_rtst_ai_seat3"]:
        try:
            c = RtstApiClient(secret=SE / (n + ".json"))
            cap = c.capacity()
            print(f"rtst {n:28} credits={cap.get('credits')} ok={cap.get('ok', cap)}")
        except Exception as e:
            print(f"rtst {n:28} ERROR: {type(e).__name__}: {str(e)[:80]}")
except Exception as e:
    print("rtst import failed:", e)

try:
    from flow_api_client import FlowApiClient
    for n in ["session_labs_google_flow"]:
        try:
            c = FlowApiClient(secret=SE / (n + ".json"))
            cap = c.capacity()
            print(f"flow {n:28} capacity={cap}")
        except Exception as e:
            print(f"flow {n:28} ERROR: {type(e).__name__}: {str(e)[:80]}")
except Exception as e:
    print("flow import failed:", e)

try:
    from digen_session_replay import DigenSessionClient
    for n in ["session_digen_ai"]:
        try:
            c = DigenSessionClient(secret=SE / (n + ".json"))
            cap = c.capacity() if hasattr(c, "capacity") else "(no capacity probe)"
            print(f"digen {n:27} capacity={cap}")
        except Exception as e:
            print(f"digen {n:27} ERROR: {type(e).__name__}: {str(e)[:80]}")
except Exception as e:
    print("digen import failed:", e)
