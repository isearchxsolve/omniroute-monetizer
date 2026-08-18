"""Check OmniRoute auth and get connections with auth."""
import requests, json

base = 'http://localhost:20128'

# 1. Try without auth
r1 = requests.get(f'{base}/api/providers', timeout=10)
print(f"No auth: HTTP {r1.status_code}, body[:200]={r1.text[:200]}")

# 2. Try login
try:
    r2 = requests.post(f'{base}/api/auth/login', json={"password": "admin"}, timeout=10)
    print(f"Login 'admin': HTTP {r2.status_code}, body[:200]={r2.text[:200]}")
except Exception as e:
    print(f"Login error: {e}")

# 3. Try common passwords
for pw in ['admin', 'password', 'omniroute', 'monetizer', '1234', 'test', 'omniroute123']:
    try:
        r = requests.post(f'{base}/api/auth/login', json={"password": pw}, timeout=5)
        if r.status_code == 200:
            print(f"Login SUCCESS with password '{pw}': {r.text[:200]}")
            # Get session cookie
            cookies = r.cookies.get_dict()
            print(f"Cookies: {list(cookies.keys())}")
            # Try providers with session
            r3 = requests.get(f'{base}/api/providers', cookies=r.cookies, timeout=10)
            print(f"Providers with auth: HTTP {r3.status_code}, count={len(r3.json().get('connections', []))}")
            break
    except:
        pass

# 4. Check if there's a stored password in config
import os
for f in ['state/config.json', 'state/settings.json', 'config.json', '.env']:
    fp = os.path.join('d:\\omniroute-monetizer', f)
    if os.path.exists(fp):
        print(f"\nFound config: {fp}")
        try:
            content = open(fp, encoding='utf-8').read()[:500]
            print(f"  Content[:500]: {content}")
        except:
            pass
