# -*- coding: utf-8 -*-
"""Print host + modality + status for the 12 REPLAY_OK secrets to build the Chrome
client registration map. Read-only."""
import json, pathlib

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
WANT = [
    "session_1min_ai.json", "session_google_gemini_web.json",
    "session_perplexity_free_web.json", "session_mistral_le_chat.json",
    "session_cohere_coral_web.json", "session_qwen_chat_(alibaba).json",
    "session_groq_chat.json", "session_felo_ai_web.json", "session_chatx.json",
    "session_deepseek_chat.json", "session_zhipu_glm_chat.json",
    "session_cerebras_inference_chat.json",
]
for name in WANT:
    p = SECRETS / name
    if not p.exists():
        print("MISSING", name); continue
    d = json.loads(p.read_text(encoding="utf-8"))
    st = d.get("status") or {}
    print("%-38s host=%-28s modality=%-6s alive=%s site=%s" % (
        name, d.get("host"), d.get("modality"), st.get("alive"), (d.get("site") or "")[:40]))
