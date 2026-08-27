# -*- coding: utf-8 -*-
"""Retire genspark.ai + yi.baichuan-ai.com seats: DOM diagnosis predicts bridge misfire.
(worklog #1105)

genspark.ai: the only visible textarea is the agent's "Additional details (optional)"
  field, not a chat composer — ChromeReplayClient would inject into the wrong input.
yi.baichuan-ai.com: ZERO message containers match the bridge's generic selectors even
  with existing content — the poll would NO_ANSWER every time.

Both need provider-specific adapters (custom composer + response selectors), not the
generic bridge. Retired alive:false with the recovery requirement documented.
"""
import json, pathlib, time

RETIRES = {
    "session_genspark_ai.json": (
        "bridge misfire: only visible textarea is the agent 'Additional details "
        "(optional)' field, not a chat composer; generic bridge would inject into the "
        "wrong input. Needs a provider-specific adapter. worklog #1105"),
    "session_yi_baichuan.json": (
        "bridge misfire: zero message containers match the generic POLL_JS selectors "
        "even with existing content; poll would NO_ANSWER every time. Needs custom "
        "response selectors. worklog #1105"),
}

for fname, reason in RETIRES.items():
    p = pathlib.Path("state/secrets") / fname
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["status"] = {"alive": False, "reason": reason, "marked_at": time.time()}
    p.write_text(json.dumps(raw, indent=1), encoding="utf-8")
    print("retired:", fname, "->", raw["host"])
