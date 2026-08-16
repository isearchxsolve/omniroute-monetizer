import re

f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

for pat in ['resolveQuotaExhaustionCutoffForTarget', 'getQuotaFetcher', 'getResetAwareProvider', 'getCachedProviderConnections', 'quotaRemainingPercent', 'calculateResetWindowAffinity', 'fetchResetAwareQuotaWithCache']:
    idxs = [m.start() for m in re.finditer(re.escape(pat), s)]
    print(f'{pat}: {len(idxs)}')

print('\n===== resolveQuotaExhaustionCutoffForTarget contexts =====')
for m in list(re.finditer('resolveQuotaExhaustionCutoffForTarget', s))[:3]:
    i = m.start()
    print('--- at', i, '---')
    print(s[max(0,i-100):i+500].replace('\n',' '))
    print()
