import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""
    SELECT provider, name, auth_type, is_active, test_status, last_error, last_error_at
    FROM provider_connections
    ORDER BY provider, name
""")

rows = c.fetchall()

report = "# 📊 Master Provider State Document\n\n"
report += "As requested, I am documenting the exact state of ALL configured providers in the database.\n\n"

current_provider = None
for r in rows:
    provider, name, auth_type, is_active, test_status, last_error, last_error_at = r
    
    if provider != current_provider:
        report += f"## {provider}\n"
        current_provider = provider
        
    status_icon = "✅" if test_status == "active" else ("❌" if test_status == "error" else "⚠️")
    active_str = "Enabled" if is_active else "Disabled"
    
    report += f"- **Account:** {name or 'Default'} ({auth_type})\n"
    report += f"  - **Status:** {status_icon} {test_status.upper()} | **Toggle:** {active_str}\n"
    
    if test_status == "error" and last_error:
        report += f"  - **Error:** `{last_error}`\n"
        report += f"  - **Time:** {last_error_at}\n"
        
    report += "\n"

with open(r"D:\omniroute-monetizer\scratch\master_provider_state.md", "w", encoding="utf-8") as f:
    f.write(report)

print("Report generated at D:\\omniroute-monetizer\\scratch\\master_provider_state.md")
