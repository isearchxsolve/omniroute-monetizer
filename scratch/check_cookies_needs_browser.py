"""Cross-check Chrome-profile storage_state cookies against the 14 NEEDS_BROWSER domains."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ss = json.loads((ROOT / "state" / "browser_profile" / "storage_state.json").read_text(encoding="utf-8"))
cookies = ss.get("cookies", [])
print(f"storage_state cookies: {len(cookies)}")

# domain -> provider slug map (match on registrable-ish domain suffix)
targets = {
    "adapta.one": "adapta-web",
    "blackbox.ai": "blackbox-web",
    "chatgpt.com": "chatgpt-web",
    "openai.com": "chatgpt-web",
    "copilot.tencent.com": "codebuddy-cn",
    "grok.com": "grok-web",
    "x.com": "grok-web",
    "officeapps.live.com": "microsoft-designer-web",
    "live.com": "microsoft-designer-web",
    "microsoft.com": "microsoft-designer-web",
    "meta.ai": "muse-spark-web",
    "perplexity.ai": "perplexity-web",
    "suno.ai": "suno",
    "t3.chat": "t3-web",
    "udio.com": "udio",
    "veoaifree.com": "veoaifree-web",
    "yuanbao.tencent.com": "yuanbao-web",
    "tencent.com": "yuanbao-web",
    "zed.dev": "zed-hosted",
}

hits = {}
all_domains = sorted({c.get("domain", "") for c in cookies})
print("\n=== all cookie domains in storage_state ===")
for d in all_domains:
    print("  ", d)

print("\n=== matches vs NEEDS_BROWSER targets ===")
for c in cookies:
    dom = c.get("domain", "").lstrip(".")
    for suffix, slug in targets.items():
        if dom == suffix or dom.endswith("." + suffix):
            hits.setdefault(slug, []).append((c.get("domain"), c.get("name")))

if hits:
    for slug, lst in sorted(hits.items()):
        print(f"  {slug}: {len(lst)} cookies")
        for dom, name in lst[:12]:
            print(f"      {dom}  {name}")
else:
    print("  NONE — no session cookies for any of the 14 targets")
