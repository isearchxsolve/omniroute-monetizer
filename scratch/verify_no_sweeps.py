import json, io, os

log = r"C:\Users\Admin\.omniroute\logs\application\app.log"
size = os.path.getsize(log)

with io.open(log, 'r', encoding='utf-8', errors='replace') as f:
    f.seek(max(0, size - 3_000_000))
    tail = f.read()

lines = tail.splitlines()

CUTOFF = "2026-08-15T23:06:36"  # fresh process start

hc = []
enc = []
cred_sweep = []
for ln in lines:
    try:
        o = json.loads(ln)
    except Exception:
        continue
    ts = o.get('timestamp', '')
    if ts < CUTOFF:
        continue
    msg = o.get('message', '')
    comp = o.get('component', '')
    if comp == 'HealthCheck' or '[HealthCheck]' in msg:
        hc.append((ts, msg[:150]))
    if comp == 'Encryption' or '[Encryption]' in msg:
        enc.append((ts, msg[:150]))
    if comp == 'CredentialHealth':
        cred_sweep.append((ts, msg[:150]))

print(f"Since fresh start ({CUTOFF}Z):")
print(f"  [HealthCheck] events: {len(hc)}")
for t, m in hc[:5]:
    print("   ", t[11:23], m)
print(f"  [Encryption] events: {len(enc)}")
for t, m in enc[:5]:
    print("   ", t[11:23], m)
print(f"  [CredentialHealth] events: {len(cred_sweep)}")
for t, m in cred_sweep[:5]:
    print("   ", t[11:23], m)

if not hc and not enc and not cred_sweep:
    print("RESULT: BOTH SWEEPERS CONFIRMED DISABLED - zero sweep activity since restart")
