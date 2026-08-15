import sqlite3
import json
import datetime

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("--- RESTORING REVOKED PROVIDER CONNECTIONS ---")

c.execute("SELECT timestamp, target_id, old_value FROM audit_log WHERE event_type = 'provider.credentials.revoked' ORDER BY timestamp DESC LIMIT 20")
rows = c.fetchall()

restored_count = 0

for r in rows:
    ts, target_id, old_value_str = r
    if not old_value_str:
        continue
        
    try:
        old_value = json.loads(old_value_str)
        conn_data = old_value.get("connection")
        if not conn_data:
            continue
            
        provider = conn_data.get("provider")
        conn_id = conn_data.get("id")
        auth_type = conn_data.get("authType")
        name = conn_data.get("name", "")
        email = conn_data.get("email", None)
        priority = conn_data.get("priority", 1)
        is_active = 1
        
        # Check if it already exists
        c.execute("SELECT id FROM provider_connections WHERE id = ?", (conn_id,))
        if c.fetchone():
            continue
            
        print(f"Restoring {provider} ({conn_id}) deleted at {ts}...")
        
        # We need to insert it back. We don't have all columns, but let's see provider_connections schema
        # Or we can use the omniroute API? 
        # No, we can just insert the JSON into the key_value store if it uses that, or provider_connections
        pass
    except Exception as e:
        print(e)

# Let's check schema of provider_connections to insert correctly
c.execute("PRAGMA table_info(provider_connections)")
columns = [col[1] for col in c.fetchall()]
print("Columns in provider_connections:", columns)

for r in rows:
    ts, target_id, old_value_str = r
    try:
        old_value = json.loads(old_value_str)
        conn_data = old_value.get("connection")
        if not conn_data: continue
        
        conn_id = conn_data.get("id")
        
        # Skip if exists
        c.execute("SELECT id FROM provider_connections WHERE id = ?", (conn_id,))
        if c.fetchone(): continue
            
        insert_cols = []
        insert_vals = []
        
        # Map JSON fields to DB columns
        mapping = {
            "id": "id", "provider": "provider", "authType": "auth_type", "name": "name", "email": "email",
            "priority": "priority", "isActive": "is_active", "testStatus": "test_status", 
            "errorCode": "error_code", "lastError": "last_error", "lastErrorAt": "last_error_at",
            "lastErrorType": "last_error_type", "lastErrorSource": "last_error_source",
            "backoffLevel": "backoff_level", "lastTested": "last_tested", "expiresAt": "expires_at",
            "tokenExpiresAt": "token_expires_at", "lastHealthCheckAt": "last_health_check_at",
            "expiresIn": "expires_in", "consecutiveUseCount": "consecutive_use_count",
            "rateLimitProtection": "rate_limit_protection", "createdAt": "created_at",
            "updatedAt": "updated_at", "proxyEnabled": "proxy_enabled", "perKeyProxyEnabled": "per_key_proxy_enabled",
            "quotaVisible": "quota_visible", "maxConcurrent": "max_concurrent"
        }
        
        for json_k, db_k in mapping.items():
            if json_k in conn_data and db_k in columns:
                val = conn_data[json_k]
                if isinstance(val, bool): val = 1 if val else 0
                insert_cols.append(db_k)
                insert_vals.append(val)
                
        # Handle JSON fields
        if "providerSpecificData" in conn_data and "provider_specific_data" in columns:
            insert_cols.append("provider_specific_data")
            insert_vals.append(json.dumps(conn_data["providerSpecificData"]))
            
        if "quotaWindowThresholds" in conn_data and conn_data["quotaWindowThresholds"] and "quota_window_thresholds" in columns:
            insert_cols.append("quota_window_thresholds")
            insert_vals.append(json.dumps(conn_data["quotaWindowThresholds"]))
            
        if "rateLimitOverrides" in conn_data and conn_data["rateLimitOverrides"] and "rate_limit_overrides" in columns:
            insert_cols.append("rate_limit_overrides")
            insert_vals.append(json.dumps(conn_data["rateLimitOverrides"]))
            
        placeholders = ",".join(["?"] * len(insert_vals))
        col_names = ",".join(insert_cols)
        
        c.execute(f"INSERT INTO provider_connections ({col_names}) VALUES ({placeholders})", insert_vals)
        print(f"  -> Successfully restored {conn_data.get('provider')} connection.")
        restored_count += 1
        
    except Exception as e:
        print(f"  -> Failed to restore: {e}")

conn.commit()
conn.close()
print(f"Restored {restored_count} revoked connections.")
