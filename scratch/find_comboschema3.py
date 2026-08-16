import re, glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
f = root + r'\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

# find normalizeModelEntry definition
for pat in ['normalizeModelEntry', 'getComboModelString', 'normalizeComboStep']:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)} at {idxs[:6]}')

# module 230376 likely holds normalizeModelEntry
i = s.find('230376,e=>')
print('\n===== module 230376 =====')
if i >= 0:
    print(s[i:i+3000])
