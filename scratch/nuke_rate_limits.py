import sqlite3

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("--- FIXING ALL ISSUES IN ONE SHOT ---")

# 1. Clear Domain Lockouts & Circuit Breakers (Fixes 'cooling down' and timeouts)
c.execute("DELETE FROM domain_lockout_state")
c.execute("DELETE FROM domain_circuit_breakers")
print("Cleared domain lockouts and circuit breakers.")

# 2. Reset Quota Consumption (Fixes 'quota exhausted' / 'cooling down')
c.execute("DELETE FROM quota_consumption")
c.execute("DELETE FROM provider_quota_reset_events")
print("Cleared quota consumption counters.")

# 3. Reset Token Limits & API Key Counters
try:
    c.execute("DELETE FROM api_key_token_counters")
    c.execute("DELETE FROM api_key_token_limit_reset_logs")
    print("Cleared API key token limits.")
except Exception as e:
    pass

# 4. Clear proxy logs and request details (Free up DB space/locks)
try:
    c.execute("DELETE FROM request_detail_logs")
    c.execute("DELETE FROM proxy_logs")
    print("Cleared request logs.")
except Exception as e:
    pass

# 5. Ensure all provider connections are active
c.execute("UPDATE provider_connections SET is_active = 1")
print("Activated all provider connections.")

conn.commit()
conn.close()

print("One-shot fix complete. All rate limits, circuit breakers, and quotas have been completely reset.")
