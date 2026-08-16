"""Stall observer: watch the OmniRoute server child during stalls.

Samples CPU% and ESTABLISHED network connections of the server process
every second while probing /v1/models. When a stall is detected, dumps
the remote endpoints the process is talking to.
"""
import time
import datetime
import requests
import psutil

BASE = "http://localhost:20128"
SERVER_PID = 22792  # server child (owns port 20128)
DURATION = 240

proc = psutil.Process(SERVER_PID)
print(f"watching PID {SERVER_PID} ({proc.name()}) for {DURATION}s", flush=True)

def snapshot():
    try:
        conns = proc.net_connections(kind="inet")
        est = [c for c in conns if c.status == "ESTABLISHED" and c.raddr]
        remotes = {}
        for c in est:
            key = f"{c.raddr.ip}:{c.raddr.port}"
            remotes[key] = remotes.get(key, 0) + 1
        return remotes
    except Exception as e:
        return {"error": str(e)}

start = time.time()
last_probe = 0.0
cpu = proc.cpu_percent(None)  # prime
while time.time() - start < DURATION:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    cpu = proc.cpu_percent(0.5)
    # probe every ~2s
    if time.time() - last_probe >= 2.0:
        last_probe = time.time()
        t0 = time.time()
        try:
            r = requests.get(f"{BASE}/v1/models", timeout=45)
            dt = time.time() - t0
            if dt > 3.0:
                remotes = snapshot()
                print(f"[{ts}] STALL {dt:.2f}s cpu={cpu:.0f}% remotes={remotes}", flush=True)
            else:
                print(f"[{ts}] ok {dt:.2f}s cpu={cpu:.0f}%", flush=True)
        except Exception as e:
            dt = time.time() - t0
            remotes = snapshot()
            print(f"[{ts}] ERR {dt:.2f}s {type(e).__name__} cpu={cpu:.0f}% remotes={remotes}", flush=True)

print("DONE", flush=True)
