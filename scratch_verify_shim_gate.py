"""Verify the task-owned shim on :8190 is healthy AND has the spend gate set.

Read-only: hits /v1/models (no spend) and reads the serving process env for
OMNI_VIDEO_CONFIRM_SPEND via the process token.
"""
import ctypes, ctypes.wintypes as w, json, sys, urllib.request

# --- 1. Find the listener on :8190 ---
import subprocess
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "(Get-NetTCPConnection -LocalPort 8190 -State Listen).OwningProcess"],
    capture_output=True, text=True).stdout.strip()
pid = int(out.splitlines()[0]) if out else None
print("listener pid:", pid)

# --- 2. Read that process's environment for the spend gate ---
def proc_env(pid):
    k32 = ctypes.windll.kernel32
    adv = ctypes.windll.advapi32
    userenv = ctypes.windll.userenv
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    TOKEN_QUERY = 0x0008
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return None, "OpenProcess failed (need admin?)"
    tok = w.HANDLE()
    if not adv.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
        k32.CloseHandle(h); return None, "OpenProcessToken failed"
    env = ctypes.c_void_p()
    if not userenv.CreateEnvironmentBlock(ctypes.byref(env), tok, False):
        k32.CloseHandle(tok); k32.CloseHandle(h); return None, "CreateEnvironmentBlock failed"
    # env block is a sequence of NUL-terminated UTF-16 strings, double NUL at end
    addr = env.value
    entries = []
    while True:
        s = ctypes.wstring_at(addr)
        if not s:
            break
        entries.append(s)
        addr += (len(s) + 1) * 2
    userenv.DestroyEnvironmentBlock(env)
    k32.CloseHandle(tok); k32.CloseHandle(h)
    return entries, None

env, err = proc_env(pid)
if err:
    print("env read:", err)
else:
    gate = [e for e in env if e.upper().startswith("OMNI_VIDEO_CONFIRM_SPEND")]
    print("spend gate in serving process env:", gate or "NOT SET")

# --- 3. Health: /v1/models ---
try:
    with urllib.request.urlopen("http://127.0.0.1:8190/v1/models", timeout=5) as r:
        data = json.load(r)
    models = data.get("data", [])
    video = [m for m in models if "video" in (m.get("id","")).lower() or m.get("id","").startswith("video/")]
    flow = [m for m in models if "labs.google" in m.get("id","")]
    print("models total:", len(models), "| video-ish:", len(video), "| labs.google entries:", len(flow))
    for m in flow:
        print("  ", m.get("id"))
except Exception as e:
    print("models error:", type(e).__name__, e)
