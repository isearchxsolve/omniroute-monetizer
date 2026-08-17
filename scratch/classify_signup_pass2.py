"""Second pass: JS-heavy SPAs. Probe known auth endpoints + scan JS bundles for auth providers."""
import json
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "*/*"}

# known auth-ish endpoints per provider
PROBES = {
    "blackbox-web": [
        "https://www.blackbox.ai/api/auth/session",
        "https://www.blackbox.ai/api/auth/providers",
        "https://www.blackbox.ai/login",
    ],
    "perplexity-web": [
        "https://www.perplexity.ai/rest/auth/session",
        "https://www.perplexity.ai/settings/account",
    ],
    "suno": [
        "https://suno.com/api/auth/session",
        "https://studio-api.suno.ai/api/auth/session",
    ],
    "t3-web": [
        "https://t3.chat/api/auth/session",
    ],
    "yuanbao-web": [
        "https://yuanbao.tencent.com/api/auth/session",
    ],
    "codebuddy-cn": [
        "https://www.codebuddy.cn/api/auth/session",
        "https://copilot.tencent.com/api/auth/session",
    ],
    "muse-spark-web": [
        "https://www.meta.ai/api/graphql",
    ],
}

AUTH_PATTERNS = [
    ("google", r"accounts\.google\.com|google[-_ ]?(sso|oauth|signin)|gsi/client"),
    ("github", r"github\.com/login/oauth|github[-_ ]?(sso|oauth)"),
    ("apple", r"appleid\.apple\.com|apple[-_ ]?(sso|signin)"),
    ("facebook", r"facebook\.com/v\d+/dialog/oauth|fb[-_ ]?login"),
    ("microsoft", r"login\.microsoftonline\.com|login\.live\.com"),
    ("wechat", r"open\.weixin\.qq\.com|wechat"),
    ("qq", r"graph\.qq\.com|qq[-_ ]?login"),
    ("clerk", r"clerk\.[a-z0-9.-]+|clerk\.com"),
    ("auth0", r"auth0|\.auth0\.com"),
    ("supabase", r"supabase\.co|supabase"),
    ("hcaptcha", r"hcaptcha"),
    ("recaptcha", r"recaptcha"),
    ("turnstile", r"turnstile|challenges\.cloudflare\.com"),
    ("email_magic_link", r"magic[-_ ]?link|send[-_ ]?(verification|login)[-_ ]?(code|email|link)"),
    ("email_password", r"sign[-_ ]?(up|in)[-_ ]?with[-_ ]?(email|password)|email[-_ ]?password"),
]

out = {}
for slug, urls in PROBES.items():
    found = set()
    notes = []
    for u in urls:
        try:
            r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
            body = r.text
            notes.append(f"{r.status_code} {u} ({len(body)}b)")
            low = body.lower()
            for name, pat in AUTH_PATTERNS:
                if re.search(pat, low):
                    found.add(name)
            # if HTML page, also scan referenced JS bundles (first 5)
            if "text/html" in r.headers.get("content-type", "") and r.status_code == 200:
                scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', body)[:5]
                for s in scripts:
                    su = s if s.startswith("http") else requests.compat.urljoin(u, s)
                    try:
                        jr = requests.get(su, headers=H, timeout=20)
                        jlow = jr.text.lower()
                        for name, pat in AUTH_PATTERNS:
                            if re.search(pat, jlow):
                                found.add(name)
                    except Exception:
                        pass
        except Exception as e:
            notes.append(f"ERR {u}: {type(e).__name__} {str(e)[:60]}")
    out[slug] = {"auth_markers": sorted(found), "notes": notes}
    print(f"{slug:22s} markers={sorted(found)}")
    for n in notes:
        print(f"    {n}")

json.dump(out, open("state/signup_flow_classification_14_pass2.json", "w", encoding="utf-8"), indent=2)
print("\nsaved -> state/signup_flow_classification_14_pass2.json")
