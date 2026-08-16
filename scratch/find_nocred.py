import re, glob

root = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks'
# find "No credentials for" in the main routing chunk and others
targets = [
    r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js',
]
for p in targets:
    s = open(p, encoding='utf-8', errors='ignore').read()
    for m in re.finditer('No credentials for', s):
        i = m.start()
        print(f'--- _0c7dpks at {i} ---')
        print(s[max(0,i-1200):i+400])
        print()
