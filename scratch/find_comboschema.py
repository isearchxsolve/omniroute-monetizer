import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

# How are combo model entries normalized? Look for providerId usage and name/model parsing
for pat in ['providerId', '.providerId', 'resolveComboTargets', 'normalizeComboModel', 'parseComboModel']:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)} at {idxs[:8]}')

# dump context around first providerId
m = re.search(r'\.providerId', s)
if m:
    i = m.start()
    print('\n===== .providerId context =====')
    print(s[max(0,i-800):i+400])
