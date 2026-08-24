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
            
        self.exchange = self.raw.get("recorded_exchange")
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

    def _inject_prompt(self, new_prompt: str) -> str:
        if not self.base_body:
            return ""
        body = self.base_body
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
        return body

    def _extract_response(self, response_text: str) -> str:
        # A simple heuristic to extract the most likely text from varying JSON/SSE streams without using an LLM.
        import re
        # Look for content fields in standard OpenAI-like or generic JSON responses
        # Match "content":"..." or "text":"..."
        matches = re.findall(r'"(?:content|text|answer)"\s*:\s*"([^"]+)"', response_text)
        if matches:
            # Reconstruct the string if it was chunked
            text = "".join(matches).replace('\\n', '\n').replace('\\"', '"')
            if text:
                return text.strip()
        
        # Fallback for plain text or unstructured
        return response_text[:1000].strip()

    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
            
        new_prompt = messages[-1]["content"]
        
        # 1. Inject prompt using LLM
        new_body_str = self._inject_prompt(new_prompt)
        
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
        final_text = self._extract_response(r.text)
        
        return {
            "text": final_text,
            "label": "universal-adapter"
        }
