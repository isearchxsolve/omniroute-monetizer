import base64, subprocess, json

ps = "Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc],
                   capture_output=True, text=True, timeout=30)
print("RC=", r.returncode)
print("STDOUT len=", len(r.stdout))
print("STDERR=", r.stderr[:300])
print("FIRST200=", r.stdout[:200])
try:
    data = json.loads(r.stdout.strip(), strict=False)
    if isinstance(data, dict):
        data = [data]
    print("PARSED", len(data), "processes")
    for d in data:
        print("  pid=", d.get("ProcessId"))
except Exception as e:
    print("PARSE FAIL:", e)
