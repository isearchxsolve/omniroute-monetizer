import json
import time
import requests
from typing import Dict, Any, Optional

class SessionExpired(Exception):
    pass

class ChatError(Exception):
    pass

class UniversalSessionClient:
    """
    Universal HTTP Replay Adapter.
    Takes a session metadata JSON (which must contain a 'recorded_exchange' blueprint).
    Uses a fast LLM to inject the new prompt into the request payload,
    fires the HTTP request natively via requests, and uses an LLM to extract the response.
    """
    def __init__(self, secret):
        import pathlib
        if isinstance(secret, pathlib.Path) or isinstance(secret, str):
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
        for ph in [
            "Reply exactly one word: Omni.",
            "Reply exactly one word: Omni",
            "Reply exactly one word : Omni.",
            "Reply exactly one word : Omni",
            "Hi",
            "Hello"
        ]:
            if ph in body:
                return body.replace(ph, new_prompt)
            ph_url = urllib.parse.quote_plus(ph)
            if ph_url in body:
                return body.replace(ph_url, urllib.parse.quote_plus(new_prompt))
            ph_url2 = urllib.parse.quote(ph)
            if ph_url2 in body:
                return body.replace(ph_url2, urllib.parse.quote(new_prompt))
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

    def _extract_response(self, response_text: str):
        """Return (assembled_text, error_message). Universal across SSE and whole-body JSON."""
        import re
        text = (response_text or "").strip()

        def scan(objs):
            pieces, err = [], None
            for o in objs:
                p = self._piece_from_obj(o)
                if p:
                    pieces.append(p)
                e = self._error_from_obj(o)
                if e:
                    err = e
            return "".join(pieces).strip(), err

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

        # 3) regex sweep for chunked "content"/"text"/"delta" fields
        matches = re.findall(r'"(?:content|text|answer|delta)"\s*:\s*"([^"]*)"', text)
        if matches:
            joined = "".join(matches).replace('\\n', '\n').replace('\\"', '"').strip()
            if joined:
                return joined, None

        return text[:2000].strip(), None

    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
            
        new_prompt = messages[-1]["content"]

        # 1. Inject prompt using LLM
        new_body_str = self._inject_prompt(new_prompt)

        # A recorded POST with no body is a broken capture, not a live session. Firing it
        # anyway often returns HTTP 200 from an error/landing page and reads as success.
        if str(self.method).upper() in ("POST", "PUT", "PATCH") and not new_body_str:
            raise ChatError(
                f"EMPTY_BODY: capture for {self.raw.get('host')} has no replayable request "
                f"body (schema keys present: {sorted(self.raw.keys())}). Re-capture it; "
                f"do not treat a 200 from a bodyless POST as a working session."
            )

        # 1b. The sentinel must actually have been replaced, or we would send the recorded
        # probe prompt and log the model's answer to *that* as if it answered the caller.
        if new_body_str == self.base_body and new_prompt not in new_body_str:
            raise ChatError(
                f"SENTINEL_NOT_FOUND: could not inject the prompt into the recorded body for "
                f"{self.raw.get('host')} -- no known sentinel matched, so the replay would "
                f"re-send the captured probe prompt instead of the caller's."
            )
        
        # 2. Fire request
        try:
            req_kwargs = {
                "headers": self.headers,
                "timeout": 60
            }
            if self.base_body:
                req_kwargs["data"] = new_body_str.encode("utf-8")
                
            r = requests.request(self.method, self.url, **req_kwargs)
            
            if r.status_code in (401, 403):
                raise SessionExpired("Auth rejected: " + r.text[:100])
                
            r.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            raise ChatError("HTTP_ERROR", str(e))
            
        # 3. Extract final answer
        final_text, err = self._extract_response(r.text)
        if not final_text and err:
            raise ChatError("UPSTREAM_ERROR: " + err)

        return {
            "text": final_text,
            "label": "universal-adapter",
            "status": r.status_code,
        }
