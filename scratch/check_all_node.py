import psutil, time

now = time.time()
print("=== ALL node processes ===")
found = 0
for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
    try:
        if p.info['name'] and 'node' in p.info['name'].lower():
            age = now - p.info['create_time']
            cmd = ' '.join(p.info['cmdline'] or [])
            print("PID", p.info['pid'], "age_s", round(age,1), "|", cmd[:160])
            found += 1
    except Exception:
        pass
if found == 0:
    print("(none)")
