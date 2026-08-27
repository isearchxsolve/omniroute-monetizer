# Map: which pool seats (chat providers) have video capability in their chat UI?
# The Chrome Gap Doctrine applied to chat-with-video: if a human can type
# "generate a video of X" into the chat tab and get a video, the pool can too --
# ChromeReplayClient already drives these tabs; only response extraction differs.
import json
import glob
import pathlib

# Known video-capable chat products (2026 knowledge, to be verified against live tabs):
# provider host substring -> (video feature name, how it's triggered in chat)
CHAT_VIDEO_KNOWLEDGE = {
    "gemini.google.com": ("Veo 3", "ask for video in chat; Veo model picker"),
    "grok.com": ("Grok Imagine/Video", "ask for video; Imagine tab"),
    "www.meta.ai": ("Imagine Video", "/imagine video or Imagine button"),
    "chat.qwen.ai": ("Wan video", "video generation tool in chat"),
    "chatglm.cn": ("CogVideoX / QingYan video", "video tool in chat"),
    "www.genspark.ai": ("AI video agent", "video generation agent"),
    "monica.im": ("Monica video", "video tool in chat"),
    "felo.ai": ("Felo video", "video search/generation"),
    "app.1min.ai": ("video studio", "AI studio video tool"),
    "chatgpt.com": ("Sora", "video generation in chat"),
    "huggingface.co": ("spaces video", "spaces only, not chat"),
    "you.com": ("no native video", "search product"),
    "chat.deepseek.com": ("no video", "text only"),
    "chat.mistral.ai": ("no video", "text only"),
    "www.perplexity.ai": ("no video", "search only"),
    "claude.ai": ("no video", "text only"),
    "copilot.microsoft.com": ("Designer images only", "images, no video"),
    "duck.ai": ("no video", "text only"),
    "v0.app": ("no video", "code/UI only"),
    "dashboard.cohere.com": ("no video", "text API"),
    "console.groq.com": ("no video", "text API"),
    "chat.cerebras.ai": ("no video", "text only"),
    "app.chathub.gg": ("aggregator", "depends on backend model"),
    "aymo.ai": ("unknown", "needs live check"),
    "chatx.ai": ("unknown", "needs live check"),
    "yi.baichuan-ai.com": ("no video", "text only"),
    "app.innerai.com": ("unknown", "needs live check"),
    "veoaifree.com": ("Veo via WordPress", "dedicated video site"),
}

seats = []
for f in sorted(glob.glob("state/secrets/session_*.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    host = d.get("host", "")
    mod = d.get("modality", "chat")
    rec = bool(d.get("recorded_exchange") or d.get("recorded_job"))
    api = bool(d.get("api"))
    seats.append((pathlib.Path(f).stem, host, mod, rec, api))

print(f"{'seat':42s} {'host':28s} {'mod':6s} {'rec':4s} {'api':4s} video-capability")
print("-" * 120)
video_capable = []
for stem, host, mod, rec, api in seats:
    cap = None
    for key, (name, how) in CHAT_VIDEO_KNOWLEDGE.items():
        if key in host or host in key:
            cap = (name, how)
            break
    capstr = f"{cap[0]} ({cap[1][:40]})" if cap else "?"
    flag = ""
    if cap and cap[0] not in ("no video", "no native video", "unknown"):
        flag = "  <-- VIDEO"
        video_capable.append((stem, host, mod, cap[0]))
    print(f"{stem:42s} {host:28s} {mod:6s} {'Y' if rec else '-':4s} {'Y' if api else '-':4s} {capstr}{flag}")

print(f"\n=== CHAT SEATS WITH VIDEO CAPABILITY: {len(video_capable)} ===")
for stem, host, mod, name in video_capable:
    print(f"  {stem:42s} {name}")
