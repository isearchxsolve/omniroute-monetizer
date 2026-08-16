import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

for off in [90105, 107787, 186957]:
    print(f'===== resolveComboTargets at {off} =====')
    print(s[max(0,off-200):off+2500])
    print()
