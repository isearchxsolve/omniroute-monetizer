import ctypes
import os
import sqlite3

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80

kernel32 = ctypes.windll.kernel32

src_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies")
dst_path = os.path.abspath("scratch/temp_chrome_cookies.db")

handle = kernel32.CreateFileW(
    src_path,
    GENERIC_READ,
    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
    None,
    OPEN_EXISTING,
    FILE_ATTRIBUTE_NORMAL,
    None
)

if handle == -1 or handle == 0xFFFFFFFFFFFFFFFF:
    err = kernel32.GetLastError()
    print(f"Failed to open source file. Error: {err}")
else:
    file_size = kernel32.GetFileSize(handle, None)
    print(f"Source file size: {file_size} bytes")
    
    buffer = ctypes.create_string_buffer(file_size)
    bytes_read = ctypes.c_ulong(0)
    
    success = kernel32.ReadFile(handle, buffer, file_size, ctypes.byref(bytes_read), None)
    kernel32.CloseHandle(handle)
    
    if success:
        with open(dst_path, "wb") as f:
            f.write(buffer.raw[:bytes_read.value])
        print(f"Copied {bytes_read.value} bytes to {dst_path}")
        
        conn = sqlite3.connect(dst_path)
        cur = conn.cursor()
        cur.execute("SELECT host_key, name, path, expires_utc FROM cookies WHERE host_key LIKE '%tokenrouter%'")
        rows = cur.fetchall()
        print(f"Found {len(rows)} TokenRouter cookies in user's active Chrome:")
        for r in rows:
            print(" ", r)
        conn.close()
    else:
        print("ReadFile failed")
