import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get all active connections
c.execute("SELECT id, provider, name FROM provider_connections WHERE is_active = 1")
connections = c.fetchall()

print("--- ANALYZING DATABASE FOR MODELS ---")

# Look at schema of tables that might map models to connections
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f"Tables: {[t[0] for t in tables]}")

# If there's a models table, describe it
if ('models',) in tables:
    c.execute("PRAGMA table_info(models)")
    print(f"Models schema: {c.fetchall()}")
    
    # Try to find a relationship between models and connections/providers
    c.execute("SELECT id, name, provider FROM models LIMIT 10")
    print(f"Sample models: {c.fetchall()}")

if ('provider_models',) in tables:
    c.execute("PRAGMA table_info(provider_models)")
    print(f"Provider Models schema: {c.fetchall()}")

conn.close()
