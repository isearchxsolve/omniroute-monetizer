# -*- coding: utf-8 -*-
"""Mark the chatgpt.com free-web seat dead via the pool's own status mechanism.

Two independent blockers (worklog #1103):
  1. class-(c) capture bug: recording captured POST /backend-api/f/conversation/prepare
     with ephemeral Bearer + x-conduit-token, NOT the streaming conversation call.
     Requests-replay of a prepare endpoint can never produce an answer.
  2. login wall: the correct shape is the Chrome bridge, but the automation
     `providers` profile is NOT signed in to chatgpt.com (verified 2026-08-27).

Recovery path (documented, requires operator): sign in to chatgpt.com ONCE in the
automation providers profile (SignInToProviders.cmd, guard-applied), then add
"chatgpt.com" -> CHROME_CLIENTS and flip this seat alive:true.
"""
import json, pathlib, time

p = pathlib.Path("state/secrets/session_chatgpt_free_web.json")
raw = json.loads(p.read_text(encoding="utf-8"))
raw["status"] = {
    "alive": False,
    "reason": ("class-c capture bug (recorded /conversation/prepare with ephemeral "
               "Bearer+x-conduit-token, not the streaming conversation call) AND login "
               "wall in automation providers profile (not signed in). Recovery: operator "
               "signs in once via SignInToProviders.cmd, then wire chatgpt.com into "
               "CHROME_CLIENTS. worklog #1103"),
    "marked_at": time.time(),
}
p.write_text(json.dumps(raw, indent=1), encoding="utf-8")
print("marked dead. host=", raw.get("host"), "alive=", raw["status"]["alive"])
