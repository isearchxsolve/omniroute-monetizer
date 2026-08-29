import json, os
SE = r"D:\omniroute-monetizer\state\secrets"
print("=== STATELESS VIDEO SEATS - health check ===")
for n in ["session_rtst_ai","session_rtst_ai_niloy","session_rtst_ai_seat2",
          "session_rtst_ai_seat3","session_labs_google_flow","session_digen_ai",
          "session_labs_google"]:
    p = os.path.join(SE, n + ".json")
    if not os.path.exists(p):
        print(f"{n:32} MISSING"); continue
    d = json.load(open(p, encoding="utf-8-sig"))
    st = d.get("status") or {}
    api = d.get("api") or {}
    print(f"{n:32} alive={st.get('alive')} reason={st.get('reason')} "
          f"kind={api.get('kind')} runway={st.get('runway_days')} "
          f"credits={api.get('credits') or d.get('credits')}")
print()
print("=== CHROME-BOUND VIDEO SEATS the failover burned through ===")
for n in ["session_video_akool","session_video_digen","session_video_gemini",
          "session_video_qwen"]:
    p = os.path.join(SE, n + ".json")
    d = json.load(open(p, encoding="utf-8-sig"))
    st = d.get("status") or {}
    print(f"{n:32} alive={st.get('alive')} reason={st.get('reason')} "
          f"chrome={bool(d.get('chrome'))}")
