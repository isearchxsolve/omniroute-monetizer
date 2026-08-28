"""P2 recon: inspect the meta.ai seat file + recording shape (read-only, no secrets printed)."""
import io, json, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

secrets = pathlib.Path("state/secrets")
for f in sorted(secrets.glob("session_*meta*.json")):
    raw = json.loads(f.read_text(encoding="utf-8-sig"))
    print("=" * 70)
    print("FILE:", f.name)
    print("  host:", raw.get("host"), "| modality:", raw.get("modality"),
          "| runtime:", raw.get("runtime"), "| api:", raw.get("api"),
          "| chrome:", bool(raw.get("chrome")))
    print("  top-level keys:", sorted(raw.keys()))
    print("  has cookie_header:", bool(raw.get("cookie_header")),
          "| cookie len:", len(raw.get("cookie_header") or ""))
    st = raw.get("status") or {}
    print("  status:", {k: v for k, v in st.items() if k != "detail"} | ({"detail_len": len(str(st.get("detail") or ""))} if st.get("detail") else {}))
    rec = raw.get("recorded_exchange")
    if rec:
        exs = rec.get("exchanges") if isinstance(rec, dict) else rec
        if isinstance(exs, list):
            print("  recorded_exchange: %d exchanges" % len(exs))
            for i, ex in enumerate(exs[:4]):
                req = ex.get("request") or {}
                print("    [%d] %s %s" % (i, req.get("method"), (req.get("url") or "")[:110]))
                hdrs = req.get("headers") or {}
                print("        req headers:", sorted(k for k in hdrs)[:14])
        else:
            print("  recorded_exchange shape:", type(rec).__name__, str(rec)[:200])
    else:
        print("  recorded_exchange: NONE")
    if raw.get("recorded_ws"):
        print("  recorded_ws: present")
    print("  sentinel:", str(raw.get("sentinel"))[:120])
