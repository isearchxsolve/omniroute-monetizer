import os, glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server'
hits = {}
for p in glob.glob(root + r'\**\*.js', recursive=True):
    try:
        s = open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for pat in ['enc:v1', 'createCipheriv', 'STORAGE_ENCRYPTION_KEY', 'aes-256-gcm']:
        if pat in s:
            hits.setdefault(pat, []).append((p, s.count(pat)))

for pat, lst in hits.items():
    print(f'== {pat} ==')
    for p, c in lst:
        print(f'  {c}x  {p}')
