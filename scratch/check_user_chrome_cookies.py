import os
import sqlite3
import shutil

chrome_cookie_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies")
print(f"Chrome cookie path exists: {os.path.exists(chrome_cookie_path)}")

if os.path.exists(chrome_cookie_path):
    # Copy to temp file to avoid file lock
    temp_cookie_path = "scratch/temp_chrome_cookies.db"
    try:
        shutil.copy2(chrome_cookie_path, temp_cookie_path)
        conn = sqlite3.connect(temp_cookie_path)
        cur = conn.cursor()
        cur.execute("SELECT host_key, name, path, expires_utc FROM cookies WHERE host_key LIKE '%tokenrouter%'")
        rows = cur.fetchall()
        print(f"Found {len(rows)} TokenRouter cookies in user's Chrome:")
        for r in rows:
            print(" ", r)
        conn.close()
    except Exception as e:
        print("Error reading Chrome cookies:", e)
