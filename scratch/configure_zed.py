"""Rewrite Zed settings.json to use OmniRoute COMBO aliases as model IDs.
Backup-first. Only touches agent.default_model + OmniRoute.available_models.
Preserves TokenRouter, agent permissions, theme, fonts, everything else.
"""
import json, os, shutil, sys
from datetime import datetime

ZED = os.path.join(os.environ["APPDATA"], "Zed", "settings.json")

# ---- backup ----
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = rf"d:\omniroute-monetizer\state\zed_settings_backup_{ts}.json"
shutil.copy2(ZED, bak)
print(f"BACKUP -> {bak}")

with open(ZED, encoding="utf-8") as f:
    zed = json.load(f)

# ---- combo model IDs (the real, cascading, verified-live model names) ----
CAP = {
    "tools": True, "images": True, "parallel_tool_calls": False,
    "prompt_cache_key": False, "chat_completions": True,
    "interleaved_reasoning": False, "max_tokens_parameter": False,
}

def M(name, display, max_tok=200000, max_out=32000):
    return {"name": name, "display_name": display,
            "max_tokens": max_tok, "max_output_tokens": max_out,
            "max_completion_tokens": max_tok, "capabilities": dict(CAP)}

models = [
    M("auto/best-coding",     "[FAST] Best Coding (tool-safe workhorse)"),
    M("auto/best-reasoning",  "[FAST] Best Reasoning"),
    M("auto/best-chat",       "[FAST] Best Chat"),
    M("frontier",             "[FRONTIER] Fast frontier cascade"),
    M("kimi-coding",          "[CODING] Kimi Coding"),
    M("fusion-coder",         "[CODING] Fusion Coder"),
    M("auto/pro-coding",      "[POWER] Pro Coding cascade (GPT-5.6 > Sonnet > Kimi)"),
    M("auto/pro-reasoning",   "[POWER] Pro Reasoning"),
    M("auto/pro-chat",        "[POWER] Pro Chat"),
    M("Frontier Max",         "[MAX] Frontier Max (Opus > GPT-5.6 > Sonnet cascade)"),
    M("auto/asian-flagships", "[MAX] Asian Flagships (DeepSeek-R1 > Qwen > Kimi)"),
    M("auto/free-chat",       "[FREE] Auto Free Router"),
    M("moonshotai/kimi-k3-free", "[FREE] Kimi K3 Free", 128000, 8192),
]

# ---- write into config ----
oc = zed.setdefault("language_models", {}).setdefault("openai_compatible", {})
omni = oc.setdefault("OmniRoute", {})
omni["api_url"] = "http://localhost:20128/v1"
omni["available_models"] = models

# default agent model: fast + tool-safe (single-model combo = nvidia workhorse)
agent = zed.setdefault("agent", {})
agent["default_model"] = {"provider": "OmniRoute", "model": "auto/best-coding"}

with open(ZED, "w", encoding="utf-8") as f:
    json.dump(zed, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"WROTE {ZED}")
print(f"  OmniRoute api_url = {omni['api_url']}")
print(f"  default_model     = {agent['default_model']}")
print(f"  available_models  = {len(models)} combo IDs:")
for m in models:
    print(f"     {m['name']:26s} {m['display_name']}")
