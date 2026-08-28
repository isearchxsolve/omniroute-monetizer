"""Verify digen stateless graduation (worklog #1131):
1. _client_for('digen.ai', raw) resolves to DigenSessionClient (not ChromeVideoClient).
2. Seat is dispatchable via the pool scan.
3. capacity() reads live credit/remain (read-only, no spend).
4. Spend gate: chat() refuses without OMNI_VIDEO_CONFIRM_SPEND.
Never prints secrets.
"""
import io, json, os, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))

raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8-sig"))

import session_pool as sp

cls = sp._client_for("digen.ai", raw)
print("1. _client_for('digen.ai') ->", cls.__name__ if cls else None)
assert cls is not None and cls.__name__ == "DigenSessionClient", "dispatch did NOT resolve to DigenSessionClient"

# pool-level scan: is the seat visible + dispatchable?
pool = sp.SessionPool()
hit = [s for s in pool.sessions if "digen" in s.key.lower()]
for s in hit:
    print("2. pool seat:", s.key, "| host:", s.host,
          "| dispatchable:", s.dispatchable,
          "| modality:", s.modality,
          "| client_cls:", s.client_cls.__name__ if s.client_cls else None,
          "| has_api:", s.has_api, "| has_recording:", s.has_recording)

# instantiate WITHOUT spend gate -> capacity must still work (read-only), chat must refuse
os.environ.pop("OMNI_VIDEO_CONFIRM_SPEND", None)
client = cls(secret=pathlib.Path("state/secrets/session_digen_ai.json"))
print("3. capacity() =", client.capacity(), "clips (read-only credit check)")

from veo_session_replay import ChatError
try:
    client.chat([{"role": "user", "content": "gate test"}])
    print("4. SPEND GATE FAILED: chat() did NOT raise without OMNI_VIDEO_CONFIRM_SPEND")
except ChatError as e:
    print("4. spend gate OK: ChatError kind =", getattr(e, "kind", "?"), "|", str(e)[:90])
except Exception as e:
    print("4. UNEXPECTED:", type(e).__name__, str(e)[:120])
