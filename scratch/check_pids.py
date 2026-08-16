import psutil, time, sys

now = time.time()
procs = []
for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
    try:
        if p.info['name'] and 'node' in p.info['name'].lower():
            cmd = ' '.join(p.info['cmdline'] or [])
            if 'omniroute' in cmd.lower():
                age = now - p.info['create_time']
                procs.append((p.info['pid'], round(age, 1), cmd[:140]))
    except Exception:
        pass

if not procs:
    print("NO omniroute node processes found")
else:
    for x in sorted(procs, key=lambda t: t[1]):
        print("PID", x[0], "age_s", x[1], "|", x[2])
