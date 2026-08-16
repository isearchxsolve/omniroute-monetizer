"""Analyze token healthcheck module: what is w() (flag check), h(), and does tick D() re-check the flag?"""
import re

p = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\src_lib_1mef7mu._.js"
s = open(p, encoding="utf-8", errors="replace").read()
print(f"module len={len(s)}")

# Find imports section (start of module)
print("\n=== module head (imports) ===")
print(s[:1500])

# Find function D definition - the sweep tick
print("\n=== search for sweep function and sweeping flag ===")
for m in re.finditer(r"sweeping", s):
    print(f"@{m.start()}: ...{s[max(0,m.start()-250):m.start()+250]}...")
    print("---")
