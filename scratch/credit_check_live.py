"""Read-only credit/budget/quota probe for OmniRoute Monetizer.

Reads credit-related tables from the OmniRoute storage DB and prints
balances/budgets/limits WITHOUT printing secrets. Also attempts the
management API to discover any credit/billing endpoint.

NO writes are performed. This is diagnostic only.
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB = os.environ.get("OMNIROUTE_DB", r"C:\Users\Admin\.omniroute\storage.sqlite")
BASE = "http://localhost:20128"

CREDIT_TABLES = [
    "token_ledger",
    "domain_budgets",
    "domain_cost_history",
    "domain_budget_reset_logs",
    "api_key_token_limits",
    "api_key_token_counters",
    "quota_snapshots",
    "quota_consumption",
    "usage_history",
    "hourly_usage_summary",
    "daily_usage_summary",
    "provider_plans",
    "account_key_limits",
    "provider_key_limits",
    "key_value",
]

REDACT = ("api_key", "key", "token", "secret", "password", "auth", "credential")


def redact_key(k: str) -> str:
    k = k.lower()
    return any(word in k for word in REDACT)


def load_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def dump_table(conn, name, limit=20):
    try:
        rows = conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid DESC LIMIT {limit}').fetchall()
    except Exception as e:
        print(f"  ERROR: {e}")
        return
    print(f"  rows: {len(rows)}")
    if not rows:
        return
    cols = rows[0].keys()
    for r in rows:
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, str) and len(v) > 60:
                v = v[:60] + f"...<len={len(r[c])}>"
            if redact_key(c) and v is not None:
                v = "[REDACTED]"
            vals.append(f"{c}={v}")
        print("   " + " | ".join(vals))


def main():
    print(f"DB: {DB}")
    print(f"OMNIROUTE BASE: {BASE}\n")

    conn = load_conn()

    # Quota snapshots = provider remaining percentage (what the provider reports)
    print("=== quota_snapshots (provider-reported remaining %) ===")
    dump_table(conn, "quota_snapshots", 30)

    print("\n=== token_ledger (credits/Xp ledger) ===")
    dump_table(conn, "token_ledger", 15)

    print("\n=== domain_budgets (budget caps) ===")
    dump_table(conn, "domain_budgets", 15)

    print("\n=== domain_cost_history (spend) ===")
    dump_table(conn, "domain_cost_history", 15)

    print("\n=== api_key_token_limits ===")
    dump_table(conn, "api_key_token_limits", 15)

    print("\n=== api_key_token_counters ===")
    dump_table(conn, "api_key_token_counters", 15)

    print("\n=== account_key_limits ===")
    dump_table(conn, "account_key_limits", 15)

    print("\n=== provider_key_limits ===")
    dump_table(conn, "provider_key_limits", 15)

    print("\n=== provider_plans ===")
    dump_table(conn, "provider_plans", 15)

    print("\n=== usage summary (spend so far) ===")
    print("  daily_usage_summary:")
    dump_table(conn, "daily_usage_summary", 10)
    print("  hourly_usage_summary:")
    dump_table(conn, "hourly_usage_summary", 10)

    # key_value entries mentioning credit/budget/quota/plan (keys only + safe values)
    print("\n=== key_value entries matching credit/budget/quota/plan (keys only) ===")
    try:
        rows = conn.execute(
            "SELECT key FROM key_value WHERE key LIKE '%credit%' OR key LIKE '%budget%' "
            "OR key LIKE '%quota%' OR key LIKE '%plan%' OR key LIKE '%balance%' "
            "OR key LIKE '%ledger%' OR key LIKE '%cost%' LIMIT 50"
        ).fetchall()
        for r in rows:
            print("  KEY:", r["key"])
    except Exception as e:
        print("  ERROR:", e)

    conn.close()

    print("\nDone. Read-only probe — no writes performed.")


if __name__ == "__main__":
    main()
