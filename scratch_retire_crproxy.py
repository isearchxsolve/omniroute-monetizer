# -*- coding: utf-8 -*-
"""Mark the stale api.cr-proxy.com telemetry seat dead via the pool's own status mechanism.
It was a class-c capture bug (telemetry beacon, not the answer call); replaced by the
api.you.com API-credential seat (worklog #1101)."""
import json, pathlib, time

p = pathlib.Path("state/secrets/session_you_com_chat.json")
raw = json.loads(p.read_text(encoding="utf-8"))
raw["status"] = {
    "alive": False,
    "reason": ("class-c telemetry capture bug (api.cr-proxy.com batch beacon, not the "
               "answer call); replaced by api.you.com API-credential seat, worklog #1101"),
    "marked_at": time.time(),
}
p.write_text(json.dumps(raw, indent=1), encoding="utf-8")
print("marked dead. host=", raw.get("host"), "alive=", raw["status"]["alive"])
