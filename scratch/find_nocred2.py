import glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
for p in glob.glob(root + r'\*.js'):
    try:
        s = open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    if 'No credentials for' in s:
        i = s.find('No credentials for')
        print("FILE:", p.split('\\')[-1], "len:", len(s))
        print(s[max(0,i-1500):i+500])
        print("="*80)
