import glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
pats = ['enc:v1', 'createCipheriv', 'STORAGE_ENCRYPTION_KEY', 'aes-256-gcm', 'Decryption failed']
found = {p: [] for p in pats}
for p in glob.glob(root + r'\*.js'):
    try:
        s = open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for pat in pats:
        if pat in s:
            found[pat].append(p)
for pat, lst in found.items():
    print(f'== {pat}: {len(lst)} files ==')
    for x in lst[:6]:
        print('  ', x.split('\\')[-1])
