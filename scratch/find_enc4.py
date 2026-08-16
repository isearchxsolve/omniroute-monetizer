import glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
for p in glob.glob(root + r'\src_lib_db_*.js'):
    s = open(p, encoding='utf-8', errors='ignore').read()
    if 'enc:v1' in s:
        print("HAS enc:v1:", p, "len:", len(s))
        i = s.find('enc:v1')
        print(s[max(0,i-3500):i+2000])
        break
