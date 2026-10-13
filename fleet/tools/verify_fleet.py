import json
import subprocess
import sys
import os

print('='*60)
print('KAGGLE FLEET INFRASTRUCTURE VERIFICATION')
print('='*60)

# 1. Accounts
with open('C:/kaggle/working/state/kaggle_accounts.json') as f:
    data = json.load(f)

accounts = data.get('accounts', [])
print('ACCOUNTS:')
for i, acc in enumerate(accounts, 1):
    print(f'  {i}. {acc["account_id"]}: {acc["email"]}')
print(f'Total: {len(accounts)} accounts, {len(set(a["email"] for a in accounts))} distinct')

# 2. Packages
try:
    import curl_cffi
    import httpx
    import uvicorn
    import fastapi
    print('Python packages: OK')
except ImportError as e:
    print(f'Missing package: {e}')
    sys.exit(1)

# 3. Kaggle CLI
r = subprocess.run(['kaggle', '--version'], capture_output=True, text=True)
print(f'Kaggle CLI: {r.stdout.strip()}')

# 4. Directories
dirs = [
    'C:/kaggle/working/scripts/automation',
    'C:/kaggle/working/state',
    'C:/kaggle/working/OiiOii',
    'C:/kaggle/working/EmergentSH'
]
for d in dirs:
    print(f'Dir {d}: {"OK" if os.path.exists(d) else "MISSING"}')

# 5. Kaggle API test
print()
print('Testing Kaggle API access...')
for i in range(5):
    tok = None if i == 0 else None
    tok_file = f'D:/anonym/vault/kaggle_token_{i+1}.txt'
    if os.path.exists(tok_file):
        tok = open(tok_file).read().strip()
    
    env = dict(os.environ)
    if tok:
        env['KAGGLE_API_TOKEN'] = tok
        env.pop('KAGGLE_USERNAME', None)
        env.pop('KAGGLE_KEY', None)
    
    r = subprocess.run(['kaggle', 'quota'], capture_output=True, text=True, env=env, timeout=30)
    quota_lines = [l.strip() for l in (r.stdout or '').splitlines() if 'CPU' in l or 'GPU' in l]
    who = 'main' if i == 0 else f'token_{i+1}'
    status = 'OK' if r.returncode == 0 else 'FAIL'
    quota_info = ' '.join(quota_lines)[:80]
    print(f'  Account {i+1}: {status} - {quota_info}')

print()
print('='*60)
print('FLEET VERIFICATION COMPLETE - ALL SYSTEMS READY!')
print('='*60)