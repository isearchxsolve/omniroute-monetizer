"""Try stateless replay across several ready seats, ONE call each, stop at first
live success. Proves the runtime path serves a real answer with NO Chrome.
Each failure is classified (auth-expired vs wall vs parse)."""
import sys, json, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRETS = pathlib.Path("state/secrets")
from universal_replay import UniversalSessionClient
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

# ready chat seats from the static audit, in likely-fresh order
hosts = ["chat.cerebras.ai", "chat.deepseek.com", "chat.mistral.ai",
         "chat.qwen.ai", "api.cohere.com", "chatglm.cn", "chatx.ai",
         "felo.ai", "api.1min.ai", "www.perplexity.ai", "gemini.google.com"]

def find_seat(host):
    # seat files are session_<host-with-dots>.json or session_<host>_chat.json
    for p in SECRETS.glob("session_*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if raw.get("host") == host and raw.get("recorded_exchange"):
            return p
    return None

success = None
for host in hosts:
    seat = find_seat(host)
    if not seat:
        print(f"[skip] {host:22} no seat file w/ exchange")
        continue
    t0 = time.time()
    try:
        client = UniversalSessionClient(str(seat))
        result = client.chat([{"role": "user", "content": "Reply with the single word: ready"}],
                             model="probe")
        dt = time.time() - t0
        text = result.get("text", "") if isinstance(result, dict) else str(result)
        if text.strip():
            print(f"[LIVE] {host:22} {dt:.1f}s -> {text[:120]!r}")
            success = host
            break
        else:
            print(f"[empty] {host:22} {dt:.1f}s -> empty reply")
    except SessionExpired as e:
        print(f"[AUTH-EXPIRED] {host:22} {time.time()-t0:.1f}s -> {str(e)[:90]}")
    except ChatError as e:
        print(f"[CHATERR] {host:22} {time.time()-t0:.1f}s -> {str(e)[:90]}")
    except Exception as e:
        print(f"[ERR] {host:22} {time.time()-t0:.1f}s -> {type(e).__name__}: {str(e)[:90]}")

print()
print("FIRST LIVE STATELESS SUCCESS:", success or "NONE (all need re-auth or wall)")
