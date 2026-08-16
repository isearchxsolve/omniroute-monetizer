import psutil, json, io, os

# 1. Check the two fresh node processes' network listeners
for pid in (9104, 9360):
    try:
        p = psutil.Process(pid)
        conns = p.net_connections()
        listen = [c for c in conns if c.status == 'LISTEN']
        print(f"PID {pid}: user={p.username()} listen={[(c.laddr.ip, c.laddr.port) for c in listen]}")
    except Exception as e:
        print(f"PID {pid}: {type(e).__name__}: {e}")

# 2. Check app.log for the latest startup banner and HealthCheck banner
log = r"C:\Users\Admin\.omniroute\logs\application\app.log"
size = os.path.getsize(log)
print("app.log size:", size)

# read last 2MB
with io.open(log, 'r', encoding='utf-8', errors='replace') as f:
    f.seek(max(0, size - 2_000_000))
    tail = f.read()

lines = tail.splitlines()
print("tail lines:", len(lines))

# find the last startup marker and any HealthCheck/CredentialHealth banners after it
startup_idx = None
for i, ln in enumerate(lines):
    if 'OmniRoute' in ln and ('starting' in ln.lower() or 'Starting' in ln or 'listening' in ln.lower() or 'ready' in ln.lower()):
        startup_idx = i

banners = []
for ln in lines:
    if 'proactive token health-check' in ln or 'credential health' in ln.lower() or 'CredentialHealth' in ln:
        banners.append(ln[:200])

print("--- last 25 raw lines ---")
for ln in lines[-25:]:
    print(ln[:220])
print("--- HealthCheck/CredentialHealth banners in tail ---")
for b in banners[-10:]:
    print(b)
