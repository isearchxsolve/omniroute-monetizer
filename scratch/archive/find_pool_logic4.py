import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

print('===== inactive contexts =====')
for m in re.finditer('inactive', s):
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-700):i+300].replace('\n',' '))
    print()
