import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

# Look for terms about account/session selection and inactive filtering
terms = ['inactive', 'no_active', 'noActive', 'selectAccount', 'pickAccount',
         'nextAccount', 'getAccount', 'accountFor', 'sessionFor', 'resolveSession',
         'acquireSession', 'getSession', 'availableAccounts', 'activeSessions',
         'connection', 'cooldown', 'rateLimitedUntil', 'skip', 'excluded.push',
         'attemptOrder.push', 'W++', 'W+=1', 'attempted']
for t in terms:
    idxs = [m.start() for m in re.finditer(re.escape(t), s)]
    print(f'{t}: {len(idxs)}')

# The execution loop: find where attemptOrder is pushed and where a target is skipped
print('\n===== attemptOrder.push contexts =====')
for m in list(re.finditer('attemptOrder', s))[:6]:
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-400):i+250].replace('\n',' '))
    print()
