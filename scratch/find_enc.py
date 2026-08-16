import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

for pat in ['enc:v1', 'createCipheriv', 'aes-256-gcm', 'getAuthTag', 'STORAGE_ENCRYPTION_KEY']:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)} at {idxs[:5]}')

# dump context around first enc:v1 usage (the decrypt function)
m = re.search('enc:v1', s)
if m:
    i = m.start()
    print('\n===== enc:v1 context =====')
    print(s[max(0,i-1500):i+800])
