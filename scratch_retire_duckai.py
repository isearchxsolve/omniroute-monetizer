# -*- coding: utf-8 -*-
"""Retire the duck.ai seat: bridge typing triggered DuckDuckGo's bot-detection CAPTCHA
("Select all squares containing a duck"). CAPTCHA bypass is prohibited — report and
retire. Recovery: operator solves the challenge manually once in the tab, then flip
alive:true. (worklog #1105)"""
import json, pathlib, time

p = pathlib.Path("state/secrets/session_duck_ai.json")
raw = json.loads(p.read_text(encoding="utf-8"))
raw["status"] = {
    "alive": False,
    "reason": ("CAPTCHA wall: ChromeReplayClient inject+send triggered DuckDuckGo "
               "bot-detection challenge ('Select all squares containing a duck') — "
               "NO_ANSWER after 90s. CAPTCHA bypass is prohibited; seat retired. "
               "Recovery: operator solves the challenge manually in the tab, then "
               "flip alive:true. worklog #1105"),
    "marked_at": time.time(),
}
p.write_text(json.dumps(raw, indent=1), encoding="utf-8")
print("duck.ai retired. alive=", raw["status"]["alive"])
