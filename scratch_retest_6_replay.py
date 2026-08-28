"""Law-3 replay re-test of the 6 recorded chat seats currently routed to Chrome.

Instantiates UniversalSessionClient DIRECTLY (bypasses Chrome dispatch) and sends the
computed arithmetic probe. A clean '58' = replay works -> candidate for runtime:replay.
Classifies: PASS / AUTH(SessionExpired) / ChatError(code) / FALSE-GREEN (audited text).

Chat replay is free/low-risk. Does NOT touch video seats. Does NOT flip anything.
"""
import io, json, pathlib, sys, time, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))

from universal_replay import UniversalSessionClient
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

SEATS = [
    "session_cerebras_inference_chat",
    "session_deepseek_chat",
    "session_google_gemini_web",
    "session_meta_ai_web",
    "session_v0_app",
    "session_zhipu_glm_chat",
]

# Law-3 computed probe: answer must be 58, which cannot be echoed from the prompt text.
PROBE = "What is 41+17? Reply with only the number."
EXPECT = "58"

sec = pathlib.Path("state/secrets")
results = {}
for name in SEATS:
    f = sec / (name + ".json")
    print("=" * 72)
    print("SEAT:", name)
    t0 = time.time()
    try:
        client = UniversalSessionClient(secret=str(f))
        out = client.chat([{"role": "user", "content": PROBE}])
        dt = time.time() - t0
        text = (out.get("text") or "").strip()
        low = text.lower()
        has58 = EXPECT in text.replace(",", "")
        # false-green audit: placeholder / echo / empty
        placeholder = any(p in low for p in ("cooking", "loading", "thinking", "generating", "please wait", "..."))
        echo = PROBE.lower()[:20] in low
        verdict = "PASS" if (has58 and not placeholder and not echo) else "FALSE-GREEN/NO-58"
        results[name] = verdict
        print(f"  [{verdict}] status={out.get('status')} label={out.get('label')} {dt:.1f}s")
        print(f"  text[:300]: {text[:300]!r}")
        if placeholder:
            print("  !! placeholder marker present in reply")
        if echo:
            print("  !! prompt echoed back")
    except SessionExpired as e:
        dt = time.time() - t0
        results[name] = "AUTH-EXPIRED"
        print(f"  [AUTH-EXPIRED] {dt:.1f}s kind={getattr(e, 'kind', None)} msg={str(e)[:160]}")
    except ChatError as e:
        dt = time.time() - t0
        kind = getattr(e, "kind", None) or str(e).split(":")[0][:40]
        raw = getattr(e, "raw", "") or ""
        results[name] = f"CHAT-ERROR:{kind}"
        print(f"  [CHAT-ERROR] {dt:.1f}s kind={kind} status={getattr(e,'status',None)} msg={str(e)[:200]}")
        if raw:
            print(f"  raw[:200]: {raw[:200]!r}")
    except Exception as e:
        dt = time.time() - t0
        results[name] = f"EXC:{type(e).__name__}"
        print(f"  [EXC:{type(e).__name__}] {dt:.1f}s {str(e)[:200]}")
        traceback.print_exc(limit=2)

print("=" * 72)
print("SUMMARY")
for k, v in results.items():
    print(f"  {k:40s} -> {v}")
