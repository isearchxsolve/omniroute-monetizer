import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

for pat in ['getProviderConnections', 'getConnection']:
    print(f'===== {pat} =====')
    for m in re.finditer(re.escape(pat), s):
        i = m.start()
        print('--- at', i, '---')
        print(s[max(0,i-300):i+400].replace('\n',' '))
        print()

# Also: how does combo build eR (ordered targets) and is there a guard checking accounts before loop?
# Find 'isProviderInCooldown' contexts
print('===== isProviderInCooldown =====')
for m in list(re.finditer('isProviderInCooldown', s))[:8]:
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-250):i+250].replace('\n',' '))
    print()
