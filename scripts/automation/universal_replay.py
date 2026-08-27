import json
import time
import requests
from typing import Dict, Any, Optional

# --- Browser-impersonation transport ---------------------------------------
# Servers fingerprint the client at the TLS Client Hello (JA3/JA4) and the
# HTTP/2 handshake (Akamai) BEFORE any HTTP header is read. Python `requests`
# negotiates with OpenSSL over HTTP/1.1, which is instantly recognisable as a
# script and is why replays get AUTH/WALL/UNPARSEABLE verdicts even with a
# valid session cookie. curl_cffi reproduces Chrome's exact TLS Client Hello
# and HTTP/2 frame signature while still sending OUR recorded HTTP headers
# byte-for-byte (Law 4). Fall back to requests when it is not installed.
try:
    import curl_cffi
    from curl_cffi.requests import exceptions as _cc_exc
    _HAVE_CURL_CFFI = True
    _TRANSPORT_EXC = (_cc_exc.RequestException, requests.exceptions.RequestException)
except ImportError:
    curl_cffi = None
    _HAVE_CURL_CFFI = False
    _TRANSPORT_EXC = (requests.exceptions.RequestException,)

# Which browser to impersonate. "chrome" always tracks the latest Chrome
# fingerprint in the installed curl_cffi. The network-level handshake is what
# matters; the HTTP headers are the recorded ones, so this is not per-site.
_IMPERSONATE = "chrome"

# CANONICAL exception classes. session_pool.py's full-pool fall-through catches the exact class
# objects defined in veoaifree_chat_client / veo_session_replay. This file used to define its own
# lookalike classes here -- so a 429 raised below escaped the pool's `except ChatError` and the
# load balancer stopped after the FIRST session instead of rotating across the whole pool
# (2026-08-27, worklog #1109). Import the canonical ones; never redefine them.
from veoaifree_chat_client import ChatError          # noqa: E402
from veo_session_replay import SessionExpired        # noqa: E402  (subclass of ChatError)

# A prompt shorter than this is never used to detect an echo by containment: aymo.ai's real answer
# "Hi!" contains the prompt "hi", and dropping it as an echo emptied the extraction entirely.
_ECHO_MIN_PROMPT = 24

class UniversalSessionClient:
    """
    Universal HTTP Replay Adapter.
    Takes a session metadata JSON (which must contain a 'recorded_exchange' blueprint).
    Uses a fast LLM to inject the new prompt into the request payload,
    fires the HTTP request natively via requests, and uses an LLM to extract the response.
    """
    def __init__(self, secret):
        import pathlib
        # Kept so a rotated cookie can be written back to the file it came from. Without a path the
        # client still works; it just cannot persist rotation past its own process.
        self._src = None
        if isinstance(secret, pathlib.Path) or isinstance(secret, str):
            self._src = pathlib.Path(secret)
            with open(secret, "r", encoding="utf-8") as f:
                self.raw = json.load(f)
        else:
            self.raw = secret

        self.exchange = self._normalise_exchange(self.raw)
        if not self.exchange:
            raise ValueError(f"No recorded_exchange found for universal replay on {self.raw.get('host')}")
        self.url = self.exchange.get("url")
        self.method = self.exchange.get("method", "POST")

        # Filter out HTTP/2 pseudo-headers (like :authority, :path) which crash requests
        raw_headers = self.exchange.get("request_headers", {})
        self.headers = {k: v for k, v in raw_headers.items() if not k.startswith(":")}

        # The recorded content-length describes the RECORDED body. Substituting a prompt changes the
        # length, so keeping it means announcing the wrong size -- a truncated read or a 400 at the
        # provider. requests computes the right one from the body it is given.
        self.headers = {k: v for k, v in self.headers.items()
                        if k.lower() not in ("content-length", "content-md5")}

        self.base_body = self.exchange.get("request_body", "")

        # Override cookies from the live session if available
        if "cookie_header" in self.raw:
            self.headers["cookie"] = self.raw["cookie_header"]
            self.headers["Cookie"] = self.raw["cookie_header"]

        # Add Origin header if missing (fixes HuggingFace CSRF protection)
        if not any(k.lower() == "origin" for k in self.headers.keys()):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.url)
            self.headers["origin"] = f"{parsed.scheme}://{parsed.netloc}"

    # Three capture generations wrote three different shapes into state/secrets/. Reading only
    # the newest one meant an older file yielded base_body == "" -> a BODYLESS POST that often
    # still returns HTTP 200, i.e. a silent false green. Normalise on read instead.
    _URL_KEYS = ("url", "request_url")
    _METHOD_KEYS = ("method", "request_method")
    _BODY_KEYS = ("request_body", "post_data", "postData", "body", "payload")
    _HEADER_KEYS = ("request_headers", "headers", "request_header")

    @classmethod
    def _normalise_exchange(cls, raw: dict) -> Optional[Dict[str, Any]]:
        """Accept every capture schema and return the canonical one, or None."""
        cand = raw.get("recorded_exchange")

        # digen-style: {"recorded_job": {"exchanges": [...]}} -- pick the submit call, which is
        # the first exchange carrying a body (later ones are status polls).
        if not isinstance(cand, dict):
            job = raw.get("recorded_job")
            if isinstance(job, dict):
                exchanges = job.get("exchanges")
                if isinstance(exchanges, list):
                    bodied = [e for e in exchanges
                              if isinstance(e, dict) and cls._first(e, cls._BODY_KEYS)]
                    cand = bodied[0] if bodied else (exchanges[0] if exchanges else None)

        # some captures stored a bare list of exchanges at the top level
        if not isinstance(cand, dict):
            for key in ("exchanges", "recorded_exchanges", "captured_requests"):
                seq = raw.get(key)
                if isinstance(seq, list) and seq and isinstance(seq[0], dict):
                    bodied = [e for e in seq if cls._first(e, cls._BODY_KEYS)]
                    cand = bodied[0] if bodied else seq[0]
                    break

        if not isinstance(cand, dict):
            return None

        url = cls._first(cand, cls._URL_KEYS)
        if not url:
            return None
        headers = cls._first(cand, cls._HEADER_KEYS) or {}
        if not isinstance(headers, dict):
            headers = {}
        return {
            "url": url,
            "method": cls._first(cand, cls._METHOD_KEYS) or "POST",
            "request_headers": headers,
            "request_body": cls._first(cand, cls._BODY_KEYS) or "",
        }

    @staticmethod
    def _first(d: dict, keys) -> Any:
        for k in keys:
            v = d.get(k)
            if v:
                return v
        return None

    def _inject_prompt(self, new_prompt: str) -> str:
        if not self.base_body:
            return ""
        body = self.base_body
        import urllib.parse

        # The prompt is substituted into a recorded body as raw text, so every character that is
        # special in that body's ENCODING has to be escaped or the body stops parsing. This is not a
        # corner case: real prompts contain newlines and quotes constantly, and an unescaped newline
        # made chat.qwen.ai answer
        #     {"code":"RequestValidationError","details":["Field '542': JSON decode error"]}
        # which reads exactly like a dead session but is our own bug. The recorded sentinel contains
        # no special characters, so it is still searched for literally -- only the replacement is
        # escaped.
        # Escape whenever the body carries JSON ANYWHERE, not just when the whole body is JSON.
        # huggingface.co posts multipart/form-data whose parts contain JSON, so a whole-body check
        # said "not JSON", the raw newlines went in unescaped and the inner JSON stopped parsing --
        # HTTP 500. Defaulting to escaped is the safe direction: on a genuinely plain body the only
        # cost is a newline arriving as the two characters \n, where the other error corrupts the
        # payload outright.
        stripped = body.lstrip()
        is_json = stripped[:1] in ("{", "[") or '{"' in body
        esc = json.dumps(new_prompt)[1:-1]
        repl = esc if is_json else new_prompt

        for ph in [
            "Reply exactly one word: Omni.",
            "Reply exactly one word: Omni",
            "Reply exactly one word : Omni.",
            "Reply exactly one word : Omni",
            "Hi",
            "Hello"
        ]:
            if ph in body:
                return body.replace(ph, repl)
            # A url-encoded body is almost always a form field CARRYING JSON (Google's `f.req`,
            # Next.js server actions), so the replacement is json-escaped before it is percent
            # encoded. On a genuinely plain form field this only means a newline arrives as the two
            # characters \n instead of a real newline -- wrong but harmless, where the other order
            # corrupts the payload outright.
            ph_url = urllib.parse.quote_plus(ph)
            if ph_url in body:
                return body.replace(ph_url, urllib.parse.quote_plus(esc))
            ph_url2 = urllib.parse.quote(ph)
            if ph_url2 in body:
                return body.replace(ph_url2, urllib.parse.quote(esc))
        return body

    @staticmethod
    def _piece_from_obj(o) -> str:
        """Pull a text fragment from one parsed chunk across OpenAI/Anthropic/generic shapes."""
        if not isinstance(o, dict):
            return ""
        ch = o.get("choices")
        if isinstance(ch, list) and ch and isinstance(ch[0], dict):
            c0 = ch[0]
            d = c0.get("delta") or c0.get("message")
            if isinstance(d, dict):
                v = d.get("content") or d.get("text")
                if isinstance(v, str):
                    return v
            if isinstance(c0.get("text"), str):
                return c0["text"]
        d = o.get("delta")
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            v = d.get("text") or d.get("content")
            if isinstance(v, str):
                return v
        cb = o.get("content_block")
        if isinstance(cb, dict) and isinstance(cb.get("text"), str):
            return cb["text"]
        cont = o.get("content")
        if isinstance(cont, list):
            parts = [b.get("text", "") for b in cont if isinstance(b, dict)]
            if any(parts):
                return "".join(parts)
        for k in ("content", "text", "answer", "token", "value", "output", "response"):
            v = o.get(k)
            if isinstance(v, str) and v:
                return v
        return ""

    @staticmethod
    def _error_from_obj(o) -> Optional[str]:
        if not isinstance(o, dict):
            return None
        if o.get("type") == "error":
            e = o.get("error") or o.get("message")
            return e if isinstance(e, str) else (json.dumps(e)[:200] if e else "stream error")
        e = o.get("error")
        if isinstance(e, str) and e:
            return e
        if isinstance(e, dict):
            return e.get("message") or json.dumps(e)[:200]
        return None

    def _is_echo(self, frag: str) -> bool:
        """True when a swept fragment is the prompt coming back, not generated text.

        Deliberately narrow, and the bounds were both learned the hard way:

          * NOT "anything that is a substring of the prompt" -- that destroys the answer, because a
            streamed reply arrives as tokens like "Ver" + "ified" and "Ver" is a substring of
            "Reply exactly one word: Verified".
          * `p in f` only counts for a LONG prompt. With prompt "hi", aymo.ai's real answer "Hi!"
            contains the prompt and was dropped as an echo, which emptied the extraction and made the
            whole SSE stream fall through to the raw fallback. A short prompt cannot be told apart
            from a short answer this way, so it is not tried.
        """
        p = (getattr(self, "_last_prompt", "") or "").strip().lower()
        f = (frag or "").strip().lower()
        if not p or not f:
            return False
        return f == p or (len(p) >= _ECHO_MIN_PROMPT and p in f)

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        head = text[:400].lstrip().lower()
        return (head.startswith(("<!doctype", "<html", "<?xml"))
                or "<meta " in head or "<head>" in head)

    @staticmethod
    def _strip_xssi(text: str) -> str:
        """Drop the anti-JSON-hijack prefix Google (and a few others) put in front of a JSON body."""
        t = (text or "").lstrip()
        for pref in (")]}'", "while(1);", "for(;;);"):
            if t.startswith(pref):
                return t[len(pref):].lstrip()
        return text

    @classmethod
    def _deep_strings(cls, node, depth: int = 0) -> list:
        """Every string in a nested list/dict, in order. Google's reply arrays are positional with
        no field names, so there is no key to look the answer up by."""
        if depth > 12:
            return []
        if isinstance(node, str):
            return [node]
        if isinstance(node, (list, tuple)):
            out = []
            for v in node:
                out.extend(cls._deep_strings(v, depth + 1))
            return out
        if isinstance(node, dict):
            out = []
            for v in node.values():
                out.extend(cls._deep_strings(v, depth + 1))
            return out
        return []

    @staticmethod
    def _google_error(text: str) -> Optional[str]:
        """Google signals a refusal in the SAME envelope it uses for answers, but with a null
        payload and a `BardErrorInfo` code instead:

            [["wrb.fr",null,null,null,null,[13,null,[["...BardErrorInfo",[1076]]]]]]

        Without this, the envelope parser finds no documents, falls through to the raw fallback and
        the refusal reads as an answer. Observed on gemini.google.com after two successful replays:
        the session is state-sensitive, so a refusal here means STOP, not retry.
        """
        if "BardErrorInfo" not in (text or ""):
            return None
        import re
        m = re.search(r"BardErrorInfo\"\s*,\s*\[\s*(\d+)", text)
        code = m.group(1) if m else "unknown"
        return (f"GOOGLE_REFUSED: BardErrorInfo {code} -- the session replied to earlier replays and "
                f"is now refusing. State-sensitive or rate-limited; do not retry.")

    @classmethod
    def _google_envelope(cls, text: str) -> str:
        """Unwrap Google's batchexecute body: `)]}'`, then alternating length lines and JSON
        payloads, each `[["wrb.fr",null,"<escaped json>"]]` whose third element is JSON *inside* a
        JSON string. Neither json.loads on the body nor a regex sweep for `"text":"..."` reaches it.

        Parsed with a streaming json decoder rather than a regex -- a regex over this escaping is
        unwritable in practice, and the framing is newline-aligned so raw_decode walks it cleanly.

        This is a RESPONSE envelope, not a per-provider request adapter: the same shape is served by
        every Google property (Gemini, Flow, AI Studio), so one generic handler is worth it.

        Answer path measured on gemini.google.com 2026-08-26 (see inspect_reply_shape.py): the reply
        lives under `[4][0]` of the inner document, and the streaming increments repeat it, so the
        LAST document holds the most complete text.
        """
        t = cls._strip_xssi(text)
        if "wrb.fr" not in t:
            return ""
        dec = json.JSONDecoder()
        docs = []
        i = 0
        while i < len(t):
            while i < len(t) and t[i] not in "[{":
                i += 1
            if i >= len(t):
                break
            try:
                obj, end = dec.raw_decode(t, i)
            except ValueError:
                i += 1
                continue
            docs.extend(cls._unwrap_wrb(obj))
            i = end
        if not docs:
            return ""
        # Later documents are fuller versions of the same reply, so search from the end.
        for doc in reversed(docs):
            body = doc[4] if isinstance(doc, list) and len(doc) > 4 else None
            best = ""
            for s in cls._deep_strings(body if body is not None else doc):
                if len(s) <= len(best):
                    continue
                if s.startswith(("http://", "https://", "data:")) or "_" in s[:4]:
                    continue                                   # c_/r_/rc_ ids and urls
                best = s
            if best:
                return best[:4000].strip()
        return ""

    @classmethod
    def _unwrap_wrb(cls, obj) -> list:
        out = []
        if isinstance(obj, list):
            for row in obj:
                if (isinstance(row, list) and len(row) >= 3
                        and row[0] == "wrb.fr" and isinstance(row[2], str)):
                    try:
                        out.append(json.loads(row[2]))
                    except ValueError:
                        pass
                else:
                    out.extend(cls._unwrap_wrb(row))
        return out

    @staticmethod
    def _accumulate(pieces) -> str:
        """Join stream pieces, handling both delta and CUMULATIVE streams.

        Providers split roughly in half on this. A delta stream sends "Ver" then "ified" and the
        pieces must be concatenated. A cumulative stream (www.perplexity.ai) sends the whole answer
        so far in every event, so plain concatenation returns "5858" for an answer of "58".

        A piece that extends everything seen so far SUPERSEDES it; a repeat of the accumulation is
        dropped; anything else is appended. The `len(acc) >= 2` guard on the repeat case keeps a
        genuine delta of one repeated character ("a" then "a" -> "aa") from being swallowed.
        """
        acc = ""
        for p in pieces:
            if not p:
                continue
            if acc and p.startswith(acc) and len(p) > len(acc):
                acc = p
            elif acc and p == acc and len(acc) >= 2:
                continue
            else:
                acc += p
        return acc

    def _extract_response(self, response_text: str):
        """Return (assembled_text, error_message). Universal across SSE and whole-body JSON."""
        import re
        text = self._strip_xssi((response_text or "").strip())

        # Checked before the generic paths: a Google body is JSON nested in a JSON string, so the
        # SSE and whole-body branches both miss it and the raw fallback used to hand back `)]}'`.
        gerr = self._google_error(response_text or "")
        if gerr:
            return "", gerr
        g = self._google_envelope(response_text or "")
        if g:
            return g, None

        # tRPC / React-Query numbered-line patch stream (Mistral Le Chat answers the POST itself in
        # this shape). The answer is assembled from JSON patches -- "5" then append "8" -> "58" --
        # so neither the SSE branch nor a regex sweep for a single "text" field reaches it. This is
        # a RESPONSE envelope handler, not a per-provider request adapter.
        try:
            from multistep_replay import looks_like_trpc_stream, mistral_patch_stream_parse
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import looks_like_trpc_stream, mistral_patch_stream_parse
        if looks_like_trpc_stream(text):
            assembled = mistral_patch_stream_parse(text)
            if assembled:
                return assembled, None

        def scan(objs):
            pieces, err = [], None
            for o in objs:
                p = self._piece_from_obj(o)
                if p and not self._is_echo(p):     # a replayed body often carries the user turn back
                    pieces.append(p)
                e = self._error_from_obj(o)
                if e:
                    err = e
            return self._accumulate(pieces).strip(), err

        # 1) SSE stream: one JSON per `data:` line
        if text.startswith("data:") or "\ndata:" in text:
            objs = []
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                frag = line[5:].strip()
                if frag in ("", "[DONE]"):
                    continue
                try:
                    objs.append(json.loads(frag))
                except Exception:
                    continue
            assembled, err = scan(objs)
            if assembled:
                return assembled, None
            if err:
                return "", err

        # 2) whole-body JSON
        try:
            assembled, err = scan([json.loads(text)])
            if assembled:
                return assembled, None
            if err:
                return "", err
        except Exception:
            pass

        # 3) regex sweep for chunked "content"/"text"/"delta" fields.
        # The sweep covers the WHOLE body, and many providers echo the user turn back inside a
        # `content` field -- often twice, once as the message and once in the conversation record.
        # Unfiltered, that echo is concatenated in FRONT of the real answer: chat.mistral.ai scored
        # as answering "reply exactly one word: verifiedreply exactly one word: verifiedver", which
        # is the prompt twice plus three generated characters. Echo fragments are dropped so what
        # survives is what the model actually produced.
        frags = re.findall(r'"(?:content|text|answer|delta)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        frags = [f for f in frags if not self._is_echo(f)]
        if frags:
            joined = self._accumulate(frags).replace('\\n', '\n').replace('\\"', '"').strip()
            if joined:
                return joined, None

        # 4) Nothing structured matched. Handing the raw body back as the reply is how a dead route
        # reads as a live one: an HTML login wall, error page or marketing landing arrives as "the
        # model's answer", and anything scoring that text for a keyword can find it in the page's own
        # markup -- veoaifree.com scored an answer of `<!doctype html>`, and you.com's reply carried
        # `width=device-width, initial-scale=1` from a <meta> tag. A body we cannot parse is a
        # failure, not an answer. Short plain-text bodies are still allowed through, because some
        # providers genuinely answer in text/plain.
        if self._looks_like_html(text):
            return "", (f"UNPARSEABLE_HTML: provider returned an HTML page, not an API response "
                        f"({len(text)} bytes) -- this session does not answer over this endpoint")
        # A stream we failed to parse is the same false-supply hazard as an HTML page, just
        # structured: handing the raw SSE back means the caller receives `event: chunk\ndata: {...}`
        # as the assistant's words. Observed on aymo.ai once the echo filter had wrongly emptied the
        # parse -- the reply was 804 characters of protocol.
        if "data: {" in text or text.lstrip().startswith("event:"):
            return "", (f"UNPARSEABLE_STREAM: {len(text)} bytes of event-stream that no parser "
                        f"branch could assemble -- refusing to return the protocol as a reply")
        if len(text) > 4000:
            return "", (f"UNPARSEABLE: {len(text)} bytes in no recognised response shape -- refusing "
                        f"to pass a raw body off as a model reply")
        return text[:2000].strip(), None

    # Providers rotate session cookies as they are used: the reply carries Set-Cookie and a real
    # browser stores it. A replay that keeps re-sending the jar recorded at capture time therefore
    # decays on the provider's own schedule no matter what any keepalive service does, because the
    # jar on disk is a SNAPSHOT and nothing was writing back to it. That is the actual expiry path
    # for these sessions -- OmniRoute's OAuth refresh endpoint cannot touch them, they are not
    # OmniRoute connections. Absorb the rotation and persist it instead.
    def _absorb_cookies(self, resp) -> int:
        rotated: Dict[str, str] = {}
        for r in list(getattr(resp, "history", []) or []) + [resp]:
            for name, value in self._iter_set_cookies(r):
                if name:
                    rotated[name] = value if value is not None else ""
        if not rotated:
            return 0

        current = self.headers.get("cookie") or self.headers.get("Cookie") or ""
        jar: Dict[str, str] = {}
        order: list = []
        for part in current.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            if k and k not in jar:
                order.append(k)
            jar[k] = v.strip()

        changed = 0
        for k, v in rotated.items():
            if not v:                       # cleared by the provider -- honour the deletion
                if jar.pop(k, None) is not None:
                    order = [o for o in order if o != k]
                    changed += 1
                continue
            if jar.get(k) != v:
                if k not in jar:
                    order.append(k)
                jar[k] = v
                changed += 1
        if not changed:
            return 0

        merged = "; ".join(f"{k}={jar[k]}" for k in order if k in jar)
        self.headers["cookie"] = merged
        self.headers["Cookie"] = merged
        self._persist_cookies(merged)
        return changed

    def _persist_cookies(self, merged: str) -> None:
        """Write the rotated jar back so the NEXT process starts from the fresh one, not the capture.

        Atomic (tmp + replace): a half-written secrets file would take a live provider off the pool.
        Writes to cookie_header because __init__ gives that key precedence over request_headers.
        Never logs or returns the value.
        """
        if self._src is None:
            return
        try:
            disk = json.loads(self._src.read_text(encoding="utf-8"))
            disk["cookie_header"] = merged
            # Keep the embedded copy consistent so a different reader cannot see a stale jar.
            hdrs = (disk.get("recorded_exchange") or {}).get("request_headers")
            if isinstance(hdrs, dict):
                for k in list(hdrs):
                    if k.lower() == "cookie":
                        hdrs[k] = merged
            disk["cookieRotatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            tmp = self._src.with_name(self._src.name + ".tmp")
            tmp.write_text(json.dumps(disk, indent=2), encoding="utf-8")
            tmp.replace(self._src)
        except Exception:
            pass   # a stale jar on disk is survivable; losing the answer we just got is not

    # --- Transport ---------------------------------------------------------
    @staticmethod
    def _iter_set_cookies(resp):
        """Yield (name, value) for every Set-Cookie on a response, across both
        transports. `requests` iterates Cookie objects; curl_cffi iterates bare
        names with the objects on `.jar`."""
        cookies = getattr(resp, "cookies", None)
        if not cookies:
            return
        # curl_cffi: names on the wrapper, Cookie objects on .jar
        jar = getattr(cookies, "jar", None)
        if jar is not None:
            for c in jar:
                yield (getattr(c, "name", None), getattr(c, "value", None))
            return
        # requests: Cookie objects directly
        for c in cookies:
            if hasattr(c, "name"):
                yield (c.name, getattr(c, "value", None))

    def _fire(self, method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float):
        """Send one request through the best available transport.

        Prefers curl_cffi browser impersonation (real Chrome TLS + HTTP/2
        fingerprint) so the server cannot tell this is a script. Falls back to
        plain requests when curl_cffi is unavailable. Returns a response object
        exposing .status_code/.ok/.text/.cookies/.history/.raise_for_status().
        """
        if _HAVE_CURL_CFFI:
            kwargs = {
                "headers": headers,
                "timeout": timeout,
                "impersonate": _IMPERSONATE,
                # We replay the RECORDED headers byte-for-byte; do not let
                # curl_cffi inject its own default browser headers on top.
                "default_headers": False,
                "allow_redirects": True,
            }
            if body:
                kwargs["content"] = body
            return curl_cffi.request(method, url, **kwargs)

        kwargs = {"headers": headers, "timeout": timeout}
        if body:
            kwargs["data"] = body
        return requests.request(method, url, **kwargs)

    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
            
        new_prompt = messages[-1]["content"]
        # Recorded so _extract_response can tell a generated reply from the prompt echoed back.
        self._last_prompt = str(new_prompt)

        # 1. Inject prompt using LLM
        new_body_str = self._inject_prompt(new_prompt)

        # 1a. Pre-flight mutations: refresh client-generated identifiers that the server
        # rejects if reused (e.g. Mistral's messageId UUID -> 409 on reuse). Not an adapter:
        # the recorded request is still replayed as-is except for these fresh fields.
        try:
            from multistep_replay import apply_preflight
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import apply_preflight
        import urllib.parse as _up
        new_body_str = apply_preflight(_up.urlsplit(self.url).netloc, new_body_str)

        # A recorded POST with no body is a broken capture, not a live session. Firing it
        # anyway often returns HTTP 200 from an error/landing page and reads as success.
        if str(self.method).upper() in ("POST", "PUT", "PATCH") and not new_body_str:
            raise ChatError(
                "EMPTY_BODY",
                f"capture for {self.raw.get('host')} has no replayable request "
                f"body (schema keys present: {sorted(self.raw.keys())}). Re-capture it; "
                f"do not treat a 200 from a bodyless POST as a working session."
            )

        # 1b. The sentinel must actually have been replaced, or we would send the recorded
        # probe prompt and log the model's answer to *that* as if it answered the caller.
        if new_body_str == self.base_body and new_prompt not in new_body_str:
            raise ChatError(
                "SENTINEL_NOT_FOUND",
                f"could not inject the prompt into the recorded body for "
                f"{self.raw.get('host')} -- no known sentinel matched, so the replay would "
                f"re-send the captured probe prompt instead of the caller's."
            )
        
        # 2. Fire request through the browser-impersonation transport.
        try:
            body_bytes = new_body_str.encode("utf-8") if self.base_body else None
            r = self._fire(self.method, self.url, self.headers, body_bytes, timeout=60)

            # Only from a non-error reply: a 401/403 body can carry a logged-OUT jar, and storing
            # that would convert a recoverable session into a dead one.
            if r.ok:
                self._absorb_cookies(r)

            if r.status_code in (401, 403):
                raise SessionExpired("AUTH", "Auth rejected: " + r.text[:100])

            r.raise_for_status()

        except _TRANSPORT_EXC as e:
            raise ChatError("HTTP_ERROR", str(e))
            
        # 2b. Multi-step providers: some return a small bootstrap JSON (stream_key /
        # conversation_id) and deliver the real answer on a second request. Detect and
        # follow up before ordinary extraction, which would score the bootstrap as the
        # answer (or as SINGLE_USE because it contains an id field).
        try:
            from multistep_replay import detect_bootstrap, run_followup
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import detect_bootstrap, run_followup
        provider_key = detect_bootstrap(r.text)
        if provider_key:
            follow_text, follow_err = run_followup(
                provider_key, r.text, self.headers,
                self.raw.get("cookie_header", ""), timeout=60.0)
            if follow_text:
                return {
                    "text": follow_text,
                    "label": f"universal-adapter+multistep:{provider_key}",
                    "status": r.status_code,
                    "raw": r.text,
                }
            # follow-up failed: fall through to normal extraction so the bootstrap
            # is at least reported honestly rather than swallowed.

        # 3. Extract final answer
        final_text, err = self._extract_response(r.text)
        if not final_text and err:
            e = ChatError("UPSTREAM_ERROR: " + err)
            # The keyword-search unlock needs the body even when no parser assembled it: a
            # computed answer sitting in an unrecognised envelope is still a live replay.
            e.raw = r.text
            e.status = r.status_code
            raise e

        return {
            "text": final_text,
            "label": "universal-adapter",
            "status": r.status_code,
            "raw": r.text,
        }
