import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

for pat in ['no credentials available', 'isModelLocked', 'isModelAvailable', 'model excluded', 'recordModelLockoutFailure', 'getModelLockout', 'clearModelLockout', 'modelLockout']:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)}')

print('\n===== "no credentials available" context =====')
for m in re.finditer('no credentials available', s):
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-500):i+200].replace('\n',' '))
    print()

print('\n===== isModelLocked definition context =====')
for m in list(re.finditer('isModelLocked', s))[:3]:
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-200):i+400].replace('\n',' '))
    print()
