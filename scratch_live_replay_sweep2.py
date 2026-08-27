"""Continue the stateless-replay sweep past deepseek, with hardened success
detection: a reply whose body is an error-JSON (PoW gate, auth, wall) is NOT a
success. Classify each outcome honestly."""
import sys, json, pathlib, time, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRETS = pathlib.Path("state/secrets")
from universal_replay import UniversalSessionClient
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

hosts = ["chat.mistral.ai", "chat.qwen.ai", "api.cohere.com", "chatglm.cn",
         "chatx.ai", "felo.ai", "api.1min.ai", "www.perplexity.ai",
         "gemini.google.com"]

# error signatures that mean the body is a rejection, not an answer
ERR_SIG = re.compile(
    r"INVALID_POW|POW_RESPONSE|unauthorized|Unauthorized|invalid.{0,20}(jwt|token|api[_ ]?key)|"
    r"expired|forbidden|403|401|rate.?limit|captcha|challenge|error\"?\s*:", re.I)

def find_seat(host):
    for p in SECRETS.glob("session_*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if raw.get("host") == host and raw.get("recorded_exchange"):
            return p
    return None

def looks_like_error(text):
    t = text.strip()
    # short JSON blob containing an error/code field
    if t.startswith("{") and ERR_SIG.search(t):
        return True
    return bool(ERR_SIG.search(t[:200]))

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
        if not text.strip():
            print(f"[empty] {host:22} {dt:.1f}s -> empty reply")
        elif looks_like_error(text):
            print(f"[GATE/ERR] {host:22} {dt:.1f}s -> {text[:110]!r}")
        else:
            print(f"[LIVE] {host:22} {dt:.1f}s -> {text[:120]!r}")
            success = host
            break
    except SessionExpired as e:
        print(f"[AUTH-EXPIRED] {host:22} {time.time()-t0:.1f}s -> {str(e)[:90]}")
    except ChatError as e:
        print(f"[CHATERR] {host:22} {time.time()-t0:.1f}s -> {str(e)[:90]}")
    except Exception as e:
        print(f"[ERR] {host:22} {time.time()-t0:.1f}s -> {type(e).__name__}: {str(e)[:90]}")

print()
print("FIRST CLEAN LIVE STATELESS SUCCESS:", success or "NONE yet")
