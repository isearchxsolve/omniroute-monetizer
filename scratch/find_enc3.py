import re, glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
# pick a src_lib_db chunk
cands = glob.glob(root + r'\src_lib_db_*.js')
print("candidates:", len(cands))
for p in cands[:1]:
    s = open(p, encoding='utf-8', errors='ignore').read()
    print("file:", p, "len:", len(s))
    i = s.find('enc:v1')
    if i >= 0:
        print(s[max(0,i-3000):i+1500])
