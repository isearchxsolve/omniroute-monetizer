"""ChatX stateless 2-leg replay client (chrome-free, no Selenium/Chrome).

ChatX (chatx.ai) is a Laravel app. A single recorded POST /sendchat is NOT enough
to replay it statelessly: the `_token` is a per-session CSRF that rotates, and the
answer is delivered on a SECOND endpoint (GET /chats_stream, SSE) keyed by the
conversions_id that /sendchat returns. So this client performs the full genuine
flow on every call, using curl_cffi (Chrome TLS Client-Hello + HTTP/2 impersonation,
Law 4) and the seat's recorded cookie_header as the starting jar:

  Leg 0  GET  https://chatx.ai/gpt        -> fresh cookies + CSRF from
                                              <meta name="csrf-token" content="...">
  Leg 1  POST https://chatx.ai/sendchat    -> form: fresh _token + prompt
                                              -> {"response":true, conversions_id, ass_conversions_id}
  Leg 2  GET  https://chatx.ai/chats_stream?...  (SSE)
                                              -> accumulate type=="response.output_text.delta"

Verified LIVE 2026-08-28 (worklog #1115): answered "Omni" in 2.7s, quota left=10.
Parallel-safe: each call builds its own curl_cffi Session, no shared browser, no
global lock. This is the graduation path for the chatx seat (runtime="replay").
"""
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from curl_cffi.requests import Session as CCSession

try:
    from veoaifree_chat_client import ChatError          # canonical
    from veo_session_replay import SessionExpired        # canonical (subclass of ChatError)
except ImportError:
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    from veoaifree_chat_client import ChatError
    from veo_session_replay import SessionExpired

BASE = "https://chatx.ai"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# Error signatures that must never be counted as a successful answer.
_ERR_SIG = re.compile(
    r"(unauthenticated|unauthorized|csrf|token mismatch|invalid token|"
    r"sign in|log ?in|rate.?limit|quota|expired|forbidden|captcha|"
    r"cloudflare|attention required|403|429)", re.I)


class ChatXReplayClient:
    """Stateless ChatX client. Constructor matches the pool contract: (secret=path|dict)."""

    def __init__(self, secret):
        if isinstance(secret, (str, Path)):
            self._src = Path(secret)
            with open(secret, "r", encoding="utf-8-sig") as f:
                self.raw = json.load(f)
        else:
            self._src = None
            self.raw = secret

        self.cookie_header = self.raw.get("cookie_header", "")
        rx = self.raw.get("recorded_exchange") or {}
        body = rx.get("request_body", "")
        self._rec_fields = dict(urllib.parse.parse_qsl(body))
        self._page = self.raw.get("page_url") or (BASE + "/gpt")

    # ------------------------------------------------------------------ helpers
    def _new_session(self) -> CCSession:
        s = CCSession(impersonate="chrome")
        for part in self.cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                s.cookies.set(k.strip(), v.strip(), domain="chatx.ai")
        return s

    def _common_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self._page,
        }

    # ------------------------------------------------------------------ main
    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = messages[-1].get("content", "")
        if not prompt:
            raise ChatError("EMPTY_PROMPT", "empty prompt")

        s = self._new_session()
        hdr = self._common_headers()

        # ---- Leg 0: page for fresh CSRF + cookie refresh ----
        try:
            r0 = s.get(self._page, headers=hdr, timeout=40)
        except Exception as e:
            raise ChatError("HTTP_ERROR", f"leg0 GET failed: {e}")
        if r0.status_code in (401, 403):
            raise SessionExpired("AUTH", f"leg0 HTTP {r0.status_code}")
        m = (re.search(r'name="csrf-token"\s+content="([^"]+)"', r0.text)
             or re.search(r'content="([^"]+)"\s+name="csrf-token"', r0.text))
        if not m:
            raise ChatError("NO_CSRF", "csrf-token meta not found (login wall or layout change)")
        csrf = m.group(1)

        # ---- Leg 1: POST /sendchat ----
        fields = {
            "_token": csrf,
            "user_id": self._rec_fields.get("user_id", ""),
            "chats_id": self._rec_fields.get("chats_id", ""),
            "prompt": prompt,
            "current_model": model or self._rec_fields.get("current_model", "gpt3"),
            "is_web": self._rec_fields.get("is_web", "0"),
            "is_youtube": self._rec_fields.get("is_youtube", "0"),
        }
        h1 = dict(hdr)
        h1.update({
            "X-CSRF-TOKEN": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": BASE,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })
        try:
            r1 = s.post(BASE + "/sendchat", data=fields, headers=h1, timeout=60)
        except Exception as e:
            raise ChatError("HTTP_ERROR", f"leg1 POST failed: {e}")
        if r1.status_code in (401, 403):
            raise SessionExpired("AUTH", f"leg1 HTTP {r1.status_code}")
        if r1.status_code != 200:
            raise ChatError("HTTP_ERROR", f"leg1 HTTP {r1.status_code}: {r1.text[:120]}")
        try:
            j1 = r1.json()
        except Exception:
            raise ChatError("BAD_JSON", f"leg1 not JSON: {r1.text[:120]}")
        if not j1.get("response"):
            raise ChatError("LEG1_REJECTED",
                            str(j1.get("message") or j1.get("error") or j1)[:160])
        conversions_id = j1.get("conversions_id")
        ass = j1.get("ass_conversions_id")
        if not conversions_id:
            raise ChatError("NO_CONVERSION_ID", f"leg1 missing conversions_id: {j1}")

        # ---- Leg 2: GET /chats_stream (SSE) ----
        q = urllib.parse.urlencode({
            "user_id": fields["user_id"], "chats_id": fields["chats_id"],
            "current_model": fields["current_model"],
            "conversions_id": conversions_id, "ass_conversions_id": ass,
            "g_recaptcha_response": "", "is_web": fields["is_web"],
            "is_youtube": fields["is_youtube"], "reasoning_effort": "", "verbosity": "",
        })
        h2 = dict(hdr)
        h2["Accept"] = "text/event-stream"
        answer = ""
        t0 = time.time()
        try:
            r2 = s.get(BASE + "/chats_stream?" + q, headers=h2,
                       stream=True, timeout=90)
            if r2.status_code in (401, 403):
                raise SessionExpired("AUTH", f"leg2 HTTP {r2.status_code}")
            for line in r2.iter_lines():
                if not line:
                    continue
                line = line if isinstance(line, str) else line.decode("utf-8", "replace")
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    try:
                        obj = json.loads(payload)
                    except Exception:
                        continue
                    if obj.get("type") == "response.output_text.delta":
                        answer += obj.get("delta", "")
                if time.time() - t0 > 90:
                    break
        except SessionExpired:
            raise
        except ChatError:
            raise
        except Exception as e:
            raise ChatError("HTTP_ERROR", f"leg2 stream failed: {e}")
        finally:
            try:
                r2.close()
            except Exception:
                pass

        answer = answer.strip()
        if not answer:
            raise ChatError("EMPTY_ANSWER", "no answer extracted from SSE stream")
        if _ERR_SIG.search(answer) and len(answer) < 120:
            raise ChatError("UPSTREAM_ERROR", answer[:200])

        return {
            "text": answer,
            "label": "chatx-2leg-replay",
            "status": 200,
            "raw": answer,
        }


if __name__ == "__main__":
    # standalone smoke test
    seat = Path(__file__).resolve().parent.parent.parent / "state" / "secrets" / "session_chatx.json"
    c = ChatXReplayClient(seat)
    out = c.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
    print("TEXT:", out["text"][:200])
    print("LABEL:", out["label"])
