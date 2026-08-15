import os
import sqlite3

src = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies")
dst = "scratch/temp_chrome_cookies.db"

# Read bytes with file sharing enabled
with open(src, "rb", buffering=0) as f_src:
    # On Windows, python open might lock, let's use powershell if python fails
    pass
