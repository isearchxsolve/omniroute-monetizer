"""Read a process's ACTUAL environment block from its PEB (not the user profile env).

CreateEnvironmentBlock(bInherit=FALSE) returns the user's profile environment, which is
NOT what a running process has. The real env lives at PEB -> ProcessParameters -> Environment.
"""
import ctypes, ctypes.wintypes as w, subprocess, sys

def get_process_env(pid):
    k32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010

    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Reserved1", ctypes.c_void_p),
            ("PebBaseAddress", ctypes.c_void_p),
            ("Reserved2", ctypes.c_void_p * 2),
            ("UniqueProcessId", ctypes.POINTER(ctypes.c_ulong)),
            ("Reserved3", ctypes.c_void_p),
        ]

    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return None, "OpenProcess failed"
    pbi = PROCESS_BASIC_INFORMATION()
    retlen = ctypes.c_ulong(0)
    status = ntdll.NtQueryInformationProcess(h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), ctypes.byref(retlen))
    if status != 0 or not pbi.PebBaseAddress:
        k32.CloseHandle(h); return None, "NtQueryInformationProcess failed"

    # PEB is 64-bit here (python is 64-bit, target is 64-bit python).
    # PEB->ProcessParameters is at offset 0x20 on x64.
    pp_addr = ctypes.c_void_p()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(pbi.PebBaseAddress + 0x20), ctypes.byref(pp_addr), ctypes.sizeof(pp_addr), None):
        k32.CloseHandle(h); return None, "read ProcessParameters ptr failed"
    # RTL_USER_PROCESS_PARAMETERS->Environment is at offset 0x80 on x64.
    env_addr = ctypes.c_void_p()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(pp_addr.value + 0x80), ctypes.byref(env_addr), ctypes.sizeof(env_addr), None):
        k32.CloseHandle(h); return None, "read Environment ptr failed"

    # Read the env block: sequence of NUL-terminated UTF-16 strings, double NUL at end.
    buf = ctypes.create_string_buffer(65536)
    if not k32.ReadProcessMemory(h, env_addr, buf, len(buf), None):
        k32.CloseHandle(h); return None, "read env block failed"
    k32.CloseHandle(h)

    raw = buf.raw
    entries = []
    i = 0
    while i < len(raw):
        # find double NUL (end of a UTF-16 string = 2 zero bytes)
        j = i
        while j + 1 < len(raw) and not (raw[j] == 0 and raw[j+1] == 0):
            j += 2
        s = raw[i:j].decode("utf-16-le", errors="replace")
        if not s:
            break
        entries.append(s)
        i = j + 2
    return entries, None

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "(Get-NetTCPConnection -LocalPort 8190 -State Listen).OwningProcess"],
    capture_output=True, text=True).stdout.strip()
pid = int(out.splitlines()[0]) if out else None
print("listener pid:", pid)

env, err = get_process_env(pid)
if err:
    print("env read:", err); sys.exit(1)
gate = [e for e in env if e.upper().startswith("OMNI_VIDEO_CONFIRM_SPEND")]
print("ACTUAL process env spend gate:", gate or "NOT SET")
# also show a couple of other OMNI_ vars for context
omni = [e for e in env if e.upper().startswith("OMNI_")]
print("all OMNI_ vars:", omni or "(none)")
