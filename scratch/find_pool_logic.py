import re, sys

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()
print('len', len(s))

patterns = [
    'getAccountsForProvider', 'activeAccounts', 'resolveAccounts', 'accounts.filter',
    'isAccountActive', 'accountActive', 'getActiveSessions', 'sessionPool',
    'getSessionPool', 'buildAccountPool', 'accountPool', 'eligibleAccounts',
    'ALL_ACCOUNTS_INACTIVE', 'attemptOrder', 'excluded', 'targets.filter',
    'isActive', 'connection.isActive', 'resolveComboTargets', 'comboTargets',
]
for pat in patterns:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)}')

# Dump context around the ALL_ACCOUNTS_INACTIVE throw site (the 503 path)
print('\n===== 503 throw site context =====')
i = s.find('ALL_ACCOUNTS_INACTIVE')
while i != -1:
    print('--- at', i, '---')
    print(s[max(0, i-1500):i+300].replace('\n', ' '))
    print()
    i = s.find('ALL_ACCOUNTS_INACTIVE', i+1)
    if i > 200000:
        break
