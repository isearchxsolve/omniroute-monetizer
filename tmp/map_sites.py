"""Map unharvested target hosts to capture_sessions_cdp.py site names."""
import json

d = json.load(open(r"D:\omniroute-monetizer\state\free_llm_chat_sites.json", encoding="utf-8-sig"))
sites = d if isinstance(d, list) else d.get("sites", [])
targets = ["chatglm.cn", "hailuoai.com", "pollinations.ai", "coze.com", "doubao.com",
           "stepfun.com", "baichuan-ai.com", "creen.ai", "phind.com",
           "dashboard.cohere.com", "together.ai", "cerebras.ai", "meta.ai",
           "nemovideo.com", "akool.com", "xinghuo.xfyun.cn", "prompt.ql.app", "puter.com"]
for s in sites:
    url = str(s.get("url", ""))
    if any(t in url for t in targets):
        print(repr(s.get("name")), "->", url[:70], "| session_only:", s.get("session_only"))
