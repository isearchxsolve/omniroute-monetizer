"""Create Chrome-doctrine video seat files for all 14 video hosts.

Each seat file declares modality=video so session_pool._client_for dispatches to
ChromeVideoClient. The live signed-in tab IS the credential — no recorded bytes.
Multi-account hosts get one seat per port (several accounts = several allowances).
"""
import json
import pathlib
import time

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")

# (filename, host, chrome_port, notes)
SEATS = [
    # ---- dedicated video hosts ----
    ("session_video_labs_google.json", "labs.google", 9222,
     "Google Flow / Veo 3.1 via proven FlowSession adapter. ~20 credits/clip."),
    ("session_video_labs_google_seat2.json", "labs.google", 9224,
     "Google Flow seat 2 (seat2 profile :9224). Separate account/allowance."),
    ("session_video_veoaifree.json", "veoaifree.com", 9222,
     "VEO 3.1 free via proven VeoFreeSession adapter. 2 videos/account allowance."),
    ("session_video_veoaifree_seat2.json", "veoaifree.com", 9223,
     "veoaifree seat 2 (niloy profile :9223). Separate account/allowance."),
    ("session_video_veoaifree_seat3.json", "veoaifree.com", 9225,
     "veoaifree seat 3 (seat3 profile :9225). Separate account/allowance."),
    ("session_video_akool.json", "akool.com", 9223,
     "Akool image-to-video 4K. Generic UI driver."),
    ("session_video_magichour.json", "magichour.ai", 9223,
     "Magic Hour video. Generic UI driver. gen=45 credits observed."),
    ("session_video_giz.json", "www.giz.ai", 9223,
     "GizAI video. Generic UI driver. avatars=23 observed."),
    ("session_video_creen.json", "www.creen.ai", 9223,
     "Creen AI video. Generic UI driver."),
    ("session_video_heygen.json", "app.heygen.com", 9223,
     "HeyGen avatar video. Generic UI driver. Auth UNCLEAR — may hit wall."),
    ("session_video_digen.json", "digen.ai", 9223,
     "Digen video. Generic UI driver."),
    ("session_video_nemovideo.json", "www.nemovideo.com", 9222,
     "Nemo Video. Generic UI driver. Heavy SPA — may EVAL_ERR on probe."),
    # ---- dual-modal chat hosts (video through same signed-in session) ----
    ("session_video_grok.json", "grok.com", 9222,
     "Grok Imagine video via chat UI. Same session as chat seat."),
    ("session_video_gemini.json", "gemini.google.com", 9222,
     "Veo via Gemini UI. Same session as chat seat."),
    ("session_video_qwen.json", "chat.qwen.ai", 9222,
     "Wan video via Qwen Studio UI. Same session as chat seat."),
    ("session_video_meta.json", "www.meta.ai", 9222,
     "Imagine video via Meta AI UI. Same session as chat seat."),
    ("session_video_chatglm.json", "chatglm.cn", 9222,
     "CogVideoX via ChatGLM UI. Same session as chat seat."),
]

created = 0
skipped = 0
for fname, host, port, notes in SEATS:
    path = SECRETS / fname
    if path.exists():
        print(f"  SKIP (exists): {fname}")
        skipped += 1
        continue
    seat = {
        "host": host,
        "modality": "video",
        "chrome_port": port,
        "context": {"loggedIn": True},
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "notes": f"Chrome-doctrine video seat — live tab on :{port} is the credential. {notes}",
    }
    path.write_text(json.dumps(seat, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  CREATED: {fname}  host={host}  port={port}")
    created += 1

print(f"\nDone: {created} created, {skipped} skipped (already existed)")
