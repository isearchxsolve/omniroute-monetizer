"""Open one tab per missing seat on the providers profile (:9222) so the manifest-first
graduation sweep can see them. Skips already-graduated, already-walled, and known video-lane
seats (labs.google / rtst.ai / digen.ai already have open tabs and graduate in the video lane).

Read-only with respect to the operator: this drives ONLY the automation Chrome on
state/automation_profiles/providers via CDP. The sweep refuses any other listener.
"""
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import open_tab  # noqa: E402

PORT = 9222

# name -> URL. Defaults to https://<domain>/ where the domain is the registered host.
SITES = {
    "Groq Chat": "https://groq.com/",
    "ChatHub Web": "https://chathub.gg/",
    "1min.AI": "https://1min.ai/",
    "Baichuan Web": "https://baichuan-ai.com/",
    "Cerebras Inference Chat": "https://cloud.cerebras.ai/",
    "Coze Web": "https://www.coze.com/",
    "Doubao Web (ByteDance)": "https://www.doubao.com/chat/",
    "Grok on X / Grok Web": "https://grok.com/",
    "Meta AI Web": "https://www.meta.ai/",
    "Pollinations AI Web": "https://pollinations.ai/",
    "Together AI Chat": "https://chat.together.ai/",
    "V0 by Vercel (v0.app)": "https://v0.app/",
    "Zhipu GLM Chat": "https://chatglm.cn/",
    "iFlytek SparkDesk": "https://xinghuo.xfyun.cn/desk",
    "Aymo AI": "https://aymo.ai/",
    "Felo AI Web": "https://felo.ai/",
    "Inner AI Web": "https://innerai.com/",
    "Monica AI": "https://monica.im/",
    "Perplexity Free Web": "https://www.perplexity.ai/",
    "Akool Video": "https://app.akool.com/",
    "ChatX": "https://chatx.ai/",
    "Creen AI": "https://creen.ai/",
    "DeepInfra Chat": "https://deepinfra.com/chat",
    "Giz AI Chat": "https://giz.ai/chat/",
    "HeyGen Video": "https://app.heygen.com/",
    "MagicHour Video": "https://magichour.ai/",
    "MiniMax Hailuo AI": "https://hailuoai.video/",
    "NemoVideo": "https://nemovideo.com/",
    "Phind": "https://www.phind.com/",
    "Poe": "https://poe.com/",
    "PromptQL Web": "https://ql.app/",
    "Puter Chat": "https://puter.com/",
    "Google Gemini Web": "https://gemini.google.com/app",
    "Tencent Yuanbao": "https://yuanbao.tencent.com/",
    "VeoAIFree Chat Web": "https://veoaifree.com/",
}

ok, fail = [], []
for name, url in SITES.items():
    t = open_tab(PORT, url)
    if t:
        ok.append((name, t.get("id", "?")))
        print(f"  opened  {name:<32} {url}")
    else:
        fail.append(name)
        print(f"  FAILED  {name:<32} {url}")
    time.sleep(1.5)

print(f"\nopened {len(ok)}  failed {len(fail)}")
if fail:
    print("failures:", ", ".join(fail))
