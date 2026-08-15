import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT * FROM audit_log WHERE action = 'provider.credentials.revoked' ORDER BY timestamp DESC LIMIT 20")
rows = c.fetchall()

c.execute("PRAGMA table_info(provider_connections)")
cols = [col[1] for col in c.fetchall()]

count = 0
for r in rows:
    try:
        old_value = json.loads(r[5])
        conn_data = old_value.get('connection')
        if not conn_data:
            continue
            
        c.execute("SELECT id FROM provider_connections WHERE id=?", (conn_data['id'],))
        if c.fetchone():
            continue
            
        insert_cols = []
        insert_vals = []
        mapping = {
            'id': 'id', 'provider': 'provider', 'authType': 'auth_type', 'name': 'name', 
            'email': 'email', 'priority': 'priority', 'isActive': 'is_active', 
            'testStatus': 'test_status', 'errorCode': 'error_code', 'lastError': 'last_error', 
            'lastErrorAt': 'last_error_at', 'lastErrorType': 'last_error_type', 
            'lastErrorSource': 'last_error_source', 'backoffLevel': 'backoff_level', 
            'lastTested': 'last_tested', 'expiresAt': 'expires_at', 'tokenExpiresAt': 'token_expires_at', 
            'lastHealthCheckAt': 'last_health_check_at', 'expiresIn': 'expires_in', 
            'consecutiveUseCount': 'consecutive_use_count', 'rateLimitProtection': 'rate_limit_protection', 
            'createdAt': 'created_at', 'updatedAt': 'updated_at', 'proxyEnabled': 'proxy_enabled', 
            'perKeyProxyEnabled': 'per_key_proxy_enabled', 'quotaVisible': 'quota_visible', 
            'maxConcurrent': 'max_concurrent'
        }
        
        for jk, dk in mapping.items():
            if jk in conn_data and dk in cols:
                insert_cols.append(dk)
                val = conn_data[jk]
                if val is True: val = 1
                elif val is False: val = 0
                insert_vals.append(val)
                
        if 'providerSpecificData' in conn_data and 'provider_specific_data' in cols:
            insert_cols.append('provider_specific_data')
            insert_vals.append(json.dumps(conn_data['providerSpecificData']))
            
        query = f"INSERT INTO provider_connections ({','.join(insert_cols)}) VALUES ({','.join(['?']*len(insert_vals))})"
        c.execute(query, insert_vals)
        print(f"Restored {conn_data['provider']}")
        count += 1
    except Exception as e:
        print(e)
        
conn.commit()
print(f"Restored {count} connections.")
