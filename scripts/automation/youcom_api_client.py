"""youcom_api_client.py — the you.com API-CREDENTIAL seat: X-API-Key + documented contract, no replay.

WHY THIS EXISTS. you.com's "API Playground" is a developer tool gated by an `X-API-Key`. The original
capture (class-c bug, worklog #1101) grabbed `api.cr-proxy.com/.../batch` — a TELEMETRY beacon, not the
answer call — so replay rotted. The real answer endpoint is `POST https://api.you.com/v1/answer`, and it
NEVER fires from the playground UI unless an API key is wired (the curl example shows the unfilled
`YDC_API_KEY` placeholder). So browser automation of the playground is the wrong shape entirely.

The operator account holds FREE promotional credits (zero money invested — operator-confirmed 2026-08-27).
A key was created via the dashboard's Create-New-Key flow (AGENTS.md Resolution 1), the one-time `ydc-sk-`
reveal captured, and verified with a real authenticated 200 OK before this client was written (AGENTS.md
rule 7: never report a credential as harvested without a verified upstream 200).

Because auth is a plain `X-API-Key` header (no signed cookie, no DBSC, no device binding), the key travels
and the documented REST contract is called directly from Python with no browser in the request path. There
is no recorded exchange to replay and there never will be — same seat class as rtst.ai.

`session_pool._client_for` dispatches on the seat's declared `api.kind == "youcom"`, and
`PooledSession.dispatchable` accepts `has_api`.

SEAT FILE (`state/secrets/session_you_com_api.json`), written by the harvester, never by hand:

    {"host": "api.you.com", "modality": "chat",
     "api": {"kind": "youcom", "token": "<ydc-sk-...>", "base": "https://api.you.com"}}

CONTRACT. `POST {base}/v1/answer` with `{"query": "<prompt>"}` and header `X-API-Key: <token>`.
Response is `{"answer", "citations", "results"}`. This is a single-turn answer/search API, not a
multi-turn chat, so `chat()` flattens the message list into one query (last user message, system prompt
prepended as instructions) exactly like ChromeReplayClient._flatten_prompt.

SECRETS. The key is read from the seat file, held in a header, and never printed, logged, or returned.

    python youcom_api_client.py --selftest        # pure logic, no network, no seat
    python youcom_api_client.py --chat "prompt"   # one real call against the seat
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from veoaifree_chat_client import ChatError            # noqa: E402
from veo_session_replay import SessionExpired          # noqa: E402  (the class the pool/face catch)

DEFAULT_BASE = "https://api.you.com"

# Language that means "you cannot have this without paying / quota burned". Never worked around (Law 5).
WALL_WORDS = ("insufficient", "not enough credit", "out of credit", "no credit", "upgrade",
              "payment required", "subscribe", "purchase", "quota exceeded", "billing",
              "rate limit", "too many requests")

SYSTEM_CAP = 400  # chars of system prompt kept as instructions prefix


def _flatten_prompt(messages: List[Dict[str, Any]]) -> str:
    """you.com /v1/answer is single-turn: collapse the message list to one query string.
    Mirrors ChromeReplayClient._flatten_prompt so both seats treat a prompt identically."""
    if not messages:
        return ""
    system = ""
    last_user = ""
    for m in messages:
        role = (m.get("role") or "").lower()
        content = m.get("content") or ""
        if isinstance(content, list):            # multimodal parts -> keep text only
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if role == "system":
            system = content
        elif role == "user":
            last_user = content
    if not last_user:                            # no user turn: use whatever text we have
        last_user = messages[-1].get("content") or ""
        if isinstance(last_user, list):
            last_user = " ".join(p.get("text", "") for p in last_user if isinstance(p, dict))
    if system:
        return f"[Instructions: {system[:SYSTEM_CAP]}] {last_user}".strip()
    return last_user


class YouComApiClient:
    """One you.com seat. Constructed by the pool as `YouComApiClient(secret=<path>)`."""

    def __init__(self, secret, timeout: int = 90):
        self.timeout = int(timeout)
        self.path = pathlib.Path(secret) if not isinstance(secret, pathlib.Path) else secret
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        api = raw.get("api") or {}
        token = (api.get("token") or raw.get("api_key") or "").strip()
        if not token:
            raise SessionExpired("you.com seat carries no api.token -- re-harvest this seat")
        self.host: str = raw.get("host") or "api.you.com"
        self.base: str = (api.get("base") or DEFAULT_BASE).rstrip("/")
        # The one place the key is handled, so there is exactly one thing to audit. Never printed.
        self._headers = {"Content-Type": "application/json",
                         "Accept": "application/json",
                         "X-API-Key": token}
        self.label = f"youcom/{self.host}"

    # ---- transport -------------------------------------------------------------------------------
    def _answer(self, query: str) -> dict:
        try:
            r = requests.post(f"{self.base}/v1/answer", headers=self._headers,
                              json={"query": query}, timeout=self.timeout)
        except requests.RequestException as e:
            raise ChatError("TRANSPORT", f"you.com /v1/answer: {type(e).__name__}")
        text = r.text or ""
        if r.status_code in (401, 403):
            raise SessionExpired(f"you.com rejected the X-API-Key ({r.status_code})")
        if r.status_code == 402:
            raise ChatError("wall", "you.com requires payment (HTTP 402)")
        if r.status_code == 429:
            raise ChatError("RATE", "you.com rate-limited (HTTP 429)")
        low = text.lower()
        if any(w in low for w in WALL_WORDS):
            raise ChatError("wall", f"you.com quota/credit wall: {text[:120]}")
        try:
            return r.json()
        except ValueError:
            raise ChatError("UNPARSEABLE", f"/v1/answer returned {r.status_code} non-JSON")

    # ---- pool client contract --------------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw: Any) -> Dict[str, Any]:
        query = _flatten_prompt(messages)
        if not query.strip():
            raise ChatError("EMPTY_PROMPT", "you.com chat got an empty prompt")
        data = self._answer(query)
        answer = (data.get("answer") or "").strip()
        if not answer:
            raise ChatError("EMPTY_ANSWER", "you.com returned no answer field")
        # you.com inlines citation markers like [[1]] / [[2]] into the answer text. They are
        # index pointers into `citations`, not content — strip them so chat consumers get clean text.
        answer = re.sub(r"\[\[\d+\]\]", "", answer).strip()
        return {"text": answer, "label": self.label,
                "citations": data.get("citations") or []}


def _cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--secret", default=str(pathlib.Path(
        r"D:\omniroute-monetizer\state\secrets\session_you_com_api.json")))
    ap.add_argument("--selftest", action="store_true", help="pure logic, no network")
    ap.add_argument("--chat", default=None, help="one real call with this prompt")
    a = ap.parse_args()

    if a.selftest:
        # flatten logic only — no network, no seat, no credit
        cases = [
            ([{"role": "user", "content": "hi"}], "hi"),
            ([{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
             "[Instructions: be brief] hi"),
            ([], ""),
        ]
        ok = True
        for msgs, want in cases:
            got = _flatten_prompt(msgs)
            status = "PASS" if got == want else "FAIL"
            if got != want:
                ok = False
            print(f"[{status}] {msgs!r} -> {got!r}")
        print("SELFTEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    if a.chat:
        r = YouComApiClient(secret=a.secret).chat([{"role": "user", "content": a.chat}])
        print(f"[{r.get('label')}]\n{r['text']}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
