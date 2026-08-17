"""Measure current per-process CPU via two snapshots (delta), top consumers."""
import subprocess, time, collections

def snap():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Select-Object Id,Name,CPU | ConvertTo-Csv -NoTypeInformation"],
        capture_output=True, text=True, timeout=60)
    d = {}
    for line in out.stdout.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                pid_ = parts[0].strip('"')
                name = parts[1].strip('"')
                cpu = float(parts[2].strip('"')) if parts[2].strip('"') else 0.0
                d[pid_] = (name, cpu)
            except Exception:
                pass
    return d

a = snap()
t0 = time.time()
time.sleep(4)
b = snap()
dt = time.time() - t0
rows = []
for pid_, (name, cpu_b) in b.items():
    if pid_ in a:
        delta = cpu_b - a[pid_][1]
        pct = delta / dt * 100.0  # % of one core
        rows.append((pct, name, pid_))
rows.sort(reverse=True)
with open(r"d:\omniroute-monetizer\scratch\cpu_delta.txt", "w") as f:
    f.write(f"interval={dt:.1f}s (pct is % of ONE core; 400% = all 4 threads)\n")
    for pct, name, pid_ in rows[:15]:
        f.write(f"{pct:7.1f}%  {name:20s} pid={pid_}\n")
print("done")
