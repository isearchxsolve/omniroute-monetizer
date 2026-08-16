import glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
for p in glob.glob(root + r'\*.js'):
    try:
        s = open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    if 'getComboStepTarget' in s and '998905' in s:
        i = s.find('998905,e=>')
        if i < 0:
            i = s.find('getComboStepTarget')
        print("FILE:", p.split('\\')[-1])
        print(s[i:i+3500])
        break
