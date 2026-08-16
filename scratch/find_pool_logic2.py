import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

# resolveComboTargets contexts
print('===== resolveComboTargets =====')
for m in re.finditer('resolveComboTargets', s):
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-200):i+500].replace('\n',' '))
    print()

# isActive contexts
print('===== isActive =====')
for m in re.finditer(r'\.isActive', s):
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-350):i+250].replace('\n',' '))
    print()
