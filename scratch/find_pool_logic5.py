import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

# How does the combo loop get a connection/account for a target provider?
terms = ['getConnection', 'acquireConnection', 'connectionFor', 'forProvider',
         'pickConnection', 'nextConnection', 'connectionId', 'activeConnection',
         'availableConnection', 'resolveConnection', 'selectConnection',
         'providerConnections', 'getProviderConnections', 'listConnections',
         'isProviderInCooldown', 'providerCooldown', 'no available', 'no_available']
for t in terms:
    idxs = [m.start() for m in re.finditer(re.escape(t), s)]
    print(f'{t}: {len(idxs)}')

# The execution loop around W++ (attempted counter)
print('\n===== W++ contexts (attempt counter) =====')
for m in list(re.finditer(re.escape('W++'), s))[:6]:
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-700):i+200].replace('\n',' '))
    print()
