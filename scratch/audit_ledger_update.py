"""Audit which ledger entries got the E2E VERIFIED evidence (check for over-matching)."""
import json

d = json.load(open("state/all_296_providers_execution_ledger.json", encoding="utf-8"))
MARK = "E2E VERIFIED 2026-08-18"

def walk(c, path=""):
    if isinstance(c, dict):
        for k, v in c.items():
            if isinstance(v, dict):
                if MARK in str(v.get("evidence", "")):
                    ident = v.get("provider") or v.get("id") or v.get("name") or k
                    print("MATCH:", path + "/" + str(k), "| ident:", ident, "| status:", v.get("status"))
                else:
                    walk(v, path + "/" + str(k))
            elif isinstance(v, list):
                walk(v, path + "/" + str(k))
    elif isinstance(c, list):
        for i, e in enumerate(c):
            if isinstance(e, dict):
                if MARK in str(e.get("evidence", "")):
                    ident = e.get("provider") or e.get("id") or e.get("name") or i
                    print("MATCH:", path + f"[{i}]", "| ident:", ident, "| status:", e.get("status"))
                else:
                    walk(e, path + f"[{i}]")
            elif isinstance(e, list):
                walk(e, path + f"[{i}]")

walk(d)
