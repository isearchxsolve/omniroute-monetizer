"""Shallow signup-flow classification of the 11 session-less NEEDS_BROWSER providers.
HuggingFace baseline method: fetch login/signup page, detect captcha/OAuth/email markers.
CAPTCHA POLICY: any hCaptcha/reCAPTCHA/Turnstile => DISCARD immediately."""
import json
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")

TARGETS = {
    "adapta-web": ["https://adapta.one", "https://agent.adapta.one"],
    "blackbox-web": ["https://www.blackbox.ai"],
    "codebuddy-cn": ["https://copilot.tencent.com"],
    "microsoft-designer-web": ["https://designer.microsoft.com"],
    "muse-spark-web": ["https://www.meta.ai"],
    "perplexity-web": ["https://www.perplexity.ai"],
    "suno": ["https://suno.com"],
    "t3-web": ["https://t3.chat"],
    "udio": ["https://www.udio.com"],
    "veoaifree-web": ["https://veoaifree.com"],
    "yuanbao-web": ["https://yuanbao.tencent.com"],
}

CAPTCHA_MARKERS = [
    ("hcaptcha", r"hcaptcha|hcaptcha\.com"),
    ("recaptcha", r"g-recaptcha|recaptcha|google\.com/recaptcha"),
    ("turnstile", r"cf-turnstile|challenges\.cloudflare\.com|turnstile"),
    ("arkose", r"arkoselabs|funcaptcha|arkose"),
]
OAUTH_MARKERS = [
    ("google_sso", r"accounts\.google\.com|Continue with Google|google-signin|gsi/client"),
    ("github_sso", r"github\.com/login/oauth|Continue with GitHub"),
    ("apple_sso", r"appleid\.apple\.com|Sign in with Apple"),
    ("wechat", r"open\.weixin\.qq\.com|wechat|weixin"),
    ("qq", r"graph\.qq\.com|qq\.com/oauth"),
    ("microsoft_sso", r"login\.microsoftonline\.com|login\.live\.com"),
]
EMAIL_MARKERS = [
    ("email_form", r"type=[\"']email[\"']|input[^>]*email|sign up with email|continue with email"),
    ("password_form", r"type=[\"']password[\"']"),
]


def classify(slug, urls):
    out = {"slug": slug, "urls": urls, "fetch": [], "captcha": [], "oauth": [],
           "email": [], "verdict": None}
    body_all = ""
    for u in urls:
        try:
            r = requests.get(u, headers={"User-Agent": UA, "Accept": "text/html"},
                             timeout=25, allow_redirects=True)
            out["fetch"].append({"url": u, "status": r.status_code,
                                 "final": r.url[:80], "len": len(r.text)})
            body_all += r.text
        except Exception as e:
            out["fetch"].append({"url": u, "status": None, "error": f"{type(e).__name__}: {str(e)[:80]}"})
    low = body_all.lower()
    for name, pat in CAPTCHA_MARKERS:
        if re.search(pat, low):
            out["captcha"].append(name)
    for name, pat in OAUTH_MARKERS:
        if re.search(pat, low):
            out["oauth"].append(name)
    for name, pat in EMAIL_MARKERS:
        if re.search(pat, low):
            out["email"].append(name)

    # verdict
    if out["captcha"]:
        out["verdict"] = "DISCARD_CAPTCHA"
    elif not out["fetch"] or all(f.get("status") is None for f in out["fetch"]):
        out["verdict"] = "UNREACHABLE"
    elif out["oauth"] and not out["email"]:
        out["verdict"] = "OAUTH_ONLY"
    elif out["email"]:
        out["verdict"] = "EMAIL_SIGNUP_POSSIBLE"
    elif len(body_all) < 2000:
        out["verdict"] = "SPA_EMPTY_HTML_NEEDS_BROWSER"
    else:
        out["verdict"] = "UNKNOWN_NEEDS_DEEPER"
    return out


results = []
for slug, urls in TARGETS.items():
    r = classify(slug, urls)
    results.append(r)
    print(f"{slug:26s} -> {r['verdict']:28s} captcha={r['captcha']} oauth={r['oauth']} email={r['email']}")
    for f in r["fetch"]:
        if f.get("status"):
            print(f"    {f['status']} {f['url']} -> {f.get('final','')} ({f.get('len',0)} bytes)")
        else:
            print(f"    ERR {f['url']}: {f.get('error')}")

json.dump({"classified_at": "2026-08-18", "results": results},
          open("state/signup_flow_classification_14.json", "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("\nsaved -> state/signup_flow_classification_14.json")
