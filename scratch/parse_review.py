import json, pathlib

J = pathlib.Path(r"C:\Users\Admin\.claude\projects\D--omniroute-monetizer"
                 r"\c06b804c-fc23-4b51-bde4-27c1aa1d0ef5\subagents\workflows"
                 r"\wf_1e132b33-633\journal.jsonl")

rows = [json.loads(l) for l in J.read_text("utf-8", "replace").splitlines() if l.strip()]
print("journal rows:", len(rows), "kinds:", sorted({r.get("type") or r.get("kind") for r in rows}))

for r in rows:
    if (r.get("type") or r.get("kind")) != "result":
        continue
    label = r.get("label") or r.get("agentLabel") or r.get("id") or "?"
    val = r.get("value") if "value" in r else r.get("result")
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except Exception:
            pass
    print("\n" + "=" * 74)
    print("AGENT:", label)
    if isinstance(val, dict) and "findings" in val:
        fs = val["findings"] or []
        print("  findings:", len(fs))
        for f in fs:
            print("   [%s] line %s: %s" % (f.get("severity"), f.get("line"),
                                           (f.get("title") or "")[:110]))
            print("       FIX:", (f.get("fix") or "")[:220].replace("\n", " "))
    elif isinstance(val, dict) and "verdicts" in val:
        for v in val["verdicts"] or []:
            print("   real=%-5s %-12s %s" % (v.get("real"), v.get("corrected_severity"),
                                             (v.get("title") or "")[:95]))
    else:
        print("  ", str(val)[:600])
