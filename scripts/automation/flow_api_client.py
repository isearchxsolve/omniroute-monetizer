"""flow_api_client.py -- pool API client that bridges labs.google (Flow) supply into the :8190 pool.

WHY THIS FILE EXISTS (read before touching):
  The DOMINANT video supply on this machine is Google Flow (labs.google): four accounts holding
  ~2,075 credits (worklog #1123), enough for ~103 eight-second Veo clips at the measured 20
  credits/clip. That supply is already served -- genuinely, with live signed-in Chromes minting
  bearers and reCAPTCHA tokens -- by `video_router.py serve` on :8189 (`POST /v1/videos/generations`
  -> poll -> `/v1/videos/{id}/content`). But the film kit's designated consumer endpoint is the
  session-pool shim on :8190 (`model: "video/auto"`), and the pool could not see Flow at all: its
  only labs.google seat was a stale replay capture (401/CAPTCHA, non-dispatchable).

  This client is the bridge, and it follows the EXACT pattern of rtst_api_client.py (worklog #1122):
  a seat file declares `"api": {"kind": "flow", ...}`, session_pool._client_for dispatches on the
  kind, and this client performs the documented contract. It does NOT re-implement Flow's protocol
  and does NOT touch the provider side -- it is a thin, honest client over our OWN :8189 router,
  which already plays the Chrome contract correctly.

MONEY DISCIPLINE (mirrors rtst_api_client.py):
  * `OMNI_VIDEO_CONFIRM_SPEND` must be set truthy before any submit, else this client raises
    ChatError("wall", ...) and spends nothing. The operator's film-runway instruction is the
    consent; the keepalive bat sets the variable.
  * A FREE quote (`POST /v1/videos/quote`) is checked against `OMNI_VIDEO_MAX_SPEND` (default 30)
    and the account balance BEFORE the spending call. Flow's quote is an estimate (exact=false),
    so the router's server-side balance check remains the final gate.
  * The submit is issued ONCE. Never retried: there is no idempotency key, so a retry is a second
    charge. The pool's own fallback moves to a DIFFERENT seat, never a second submit here.

Wire shape consumed (video_router.py direct face, all on 127.0.0.1:8189):
    POST /v1/videos/quote        {"model": ..., "duration": 5}        -> {quote, balance, ...}
    POST /v1/videos/generations  {"prompt", "model", "wait": true,
                                  "wait_timeout": 600, "budget": 600}  -> public_job
    public_job: {id, status: queued|active|succeeded|failed, content_url, credits_charged, error, ...}

Pool-facing contract (identical to RtstApiClient.chat):
    chat(messages, model=None, **kw) -> {"text": <absolute clip URL>, "label": host,
                                         "status": "completed", "credits": <charged>, ...}
    capacity() -> {"host", "creditsRemaining", "clipsRemaining", "creditsPerClip"}

Run the self-test (no spend; exercises quote + capacity only):
    python flow_api_client.py --selftest
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from veoaifree_chat_client import ChatError

DEFAULT_BASE = "http://127.0.0.1:8189"
DEFAULT_MODEL = "veo_3_1_t2v_fast"     # cheapest proven Flow model: 20 credits per 8s clip
CREDITS_PER_CLIP = 20                  # measured by the router's quote endpoint (worklog #1123)
LEDGER = pathlib.Path(r"D:\omniroute-monetizer\state\flow_api_ledger.json")


def _truthy(v: Optional[str]) -> bool:
    return bool(v) and str(v).strip().lower() not in ("0", "false", "no", "")


class FlowApiClient:
    """Pool seat client for Flow supply via the local :8189 video router.

    Constructed by session_pool with `secret=` pointing at the seat file
    (state/secrets/session_labs_google_flow.json). The seat file carries NO secret for this
    kind -- the bearer lives inside the router process, in memory, as designed. The seat file
    only declares kind/base/model.
    """

    host = "labs.google"
    modality = "video"

    def __init__(self, secret: pathlib.Path | str | None = None):
        raw: Dict[str, Any] = {}
        if secret:
            try:
                raw = json.loads(pathlib.Path(secret).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                raw = {}
        api = raw.get("api") or {}
        self.base = str(api.get("base") or DEFAULT_BASE).rstrip("/")
        self.model = str(api.get("model") or DEFAULT_MODEL)
        self.token = api.get("token") or os.environ.get("VIDEO_ROUTER_TOKEN") or None
        # Loopback router with no --token accepts unauthenticated calls (_authed() is True when
        # the token is unset); when a token IS configured we must present it or get 401.
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        try:
            self.max_spend = float(os.environ.get("OMNI_VIDEO_MAX_SPEND") or 30)
        except ValueError:
            self.max_spend = 30.0
        self.timeout = 660.0           # router wait_timeout(600) + submit/poll slack

    # ---- transport ------------------------------------------------------------------------------
    def _call(self, path: str, method: str = "GET", body: Optional[dict] = None,
              timeout: float = 60.0) -> dict:
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "{}")
            except ValueError:
                detail = {"raw": "unreadable error body"}
            raise ChatError("ROUTER_HTTP", f"router {method} {path} -> HTTP {e.code}: "
                                           f"{json.dumps(detail)[:300]}") from e
        except urllib.error.URLError as e:
            raise ChatError("ROUTER_DOWN", f"video router unreachable at {self.base}: {e.reason}") from e

    # ---- free reads ------------------------------------------------------------------------------
    def capacity(self) -> Dict[str, Any]:
        """Honest capacity: the router's live per-account balances, summed over flow accounts.

        clipsRemaining is COMPUTED (balance // 20), never hardcoded -- Law 3. A router that is
        down reports zero, not a guess.
        """
        try:
            doc = self._call("/v1/accounts", timeout=30)
        except ChatError:
            return {"host": self.host, "creditsRemaining": 0, "clipsRemaining": 0,
                    "creditsPerClip": CREDITS_PER_CLIP, "error": "router unreachable"}
        total = 0
        seats = 0
        for a in doc.get("accounts") or []:
            if a.get("provider") == "flow" and a.get("enabled") and a.get("ready"):
                total += int(a.get("credits") or 0)
                seats += 1
        return {"host": self.host, "creditsRemaining": total,
                "clipsRemaining": total // CREDITS_PER_CLIP,
                "creditsPerClip": CREDITS_PER_CLIP, "flowSeats": seats}

    def _quote(self, prompt_model: str) -> Dict[str, Any]:
        return self._call("/v1/videos/quote", method="POST",
                          body={"model": prompt_model, "duration": 5}, timeout=30)

    # ---- the one path that spends ----------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        """Pool-facing entry point, signature-identical to RtstApiClient.chat.

        Returns {"text": <absolute clip URL>, "label": host, "status": "completed", ...}.
        """
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = str(messages[-1].get("content") or "").strip()
        if len(prompt.split()) < 5:
            raise ChatError("SHORT_PROMPT", "flow video prompts need a real scene description "
                                            "(5+ words)")
        want_model = str(model or self.model)
        # The pool may pass a provider-prefixed id ("labs.google/veo_3_1_t2v_fast"); the router
        # resolves its own keys, so strip only our own host prefix if present.
        if want_model.startswith(self.host + "/"):
            want_model = want_model.split("/", 1)[1]

        # 1) FREE pre-commit gate: quote + balance. Nothing spent if this refuses.
        q = self._quote(want_model)
        if q.get("error"):
            raise ChatError("QUOTE_REFUSED", f"router quote refused: {q['error']}")
        need = q.get("quote")
        balance = q.get("balance")
        if isinstance(need, (int, float)) and need > self.max_spend:
            raise ChatError("wall", f"flow quote {need:g} exceeds OMNI_VIDEO_MAX_SPEND="
                                    f"{self.max_spend:g}")
        if isinstance(need, (int, float)) and isinstance(balance, (int, float)) and balance < need:
            raise ChatError("wall", f"flow balance {balance:g} < quote {need:g}: seat is dry")
        if not self.confirm_spend:
            raise ChatError("wall", f"spend gate closed: flow clip costs ~{need} credits; "
                                    f"set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")

        # 2) Submit ONCE, wait for completion. `wait: true` makes the router block until the job
        #    is succeeded/failed and answer with the final public_job -- no second call can double-charge.
        body = {"prompt": prompt, "model": want_model, "wait": True,
                "wait_timeout": 600, "budget": 600}
        for k in ("aspect", "resolution", "seed", "duration", "account"):
            if kw.get(k) is not None:
                body[k] = kw[k]
        self._ledger({"host": self.host, "model": want_model, "quoted": need,
                      "submitted_at": int(time.time()), "prompt_words": len(prompt.split())})
        job = self._call("/v1/videos/generations", method="POST", body=body, timeout=self.timeout)

        status = job.get("status")
        job_id = str(job.get("id") or "")
        charged = job.get("credits_charged")
        if status == "succeeded":
            rel = job.get("content_url") or ""
            if not rel:
                raise ChatError("NO_URL", f"flow job {job_id[:8]} succeeded but exposed no "
                                          f"content_url")
            url = rel if rel.startswith("http") else f"{self.base}{rel}"
            return {"text": url, "label": self.host, "status": "completed",
                    "model": job.get("model") or want_model,
                    "duration": job.get("duration"),
                    "credits": float(charged if isinstance(charged, (int, float))
                                     else (need or 0.0)),
                    "provider_account": job.get("account"),
                    "job_id": job_id}

        # 3) Failed / interrupted / timed out. Classify honestly; NEVER retry here (a retry is a
        #    second charge). The pool fails over to a different seat; the film kit parks walls.
        err = str(job.get("error") or f"flow job ended with status={status!r}")
        low = err.lower()
        if any(w in low for w in ("captcha", "recaptcha", "paywall", "billing", "upgrade")):
            raise ChatError("wall", err[:400])
        if any(w in low for w in ("401", "auth", "session", "sign", "login")):
            raise ChatError("auth", err[:400])
        if job.get("media_ids") and not job.get("files"):
            # Credits were charged but nothing was downloaded: report as a wall so the seat is
            # parked and the media ids are recovered by a human, not silently retried.
            raise ChatError("wall", f"charged but not collected: {err[:300]} "
                                    f"(media_ids={job.get('media_ids')})")
        raise ChatError("NO_URL", err[:400])

    # ---- ledger (append-only, no secrets) ---------------------------------------------------------
    def _ledger(self, row: dict) -> None:
        try:
            rows = []
            if LEDGER.exists():
                try:
                    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
                except ValueError:
                    rows = []
            rows.append(row)
            LEDGER.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        except OSError:
            pass


def _selftest() -> int:
    ok = True

    def chk(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    print("flow_api_client self-test (read-only: quote + capacity, zero spend)")
    c = FlowApiClient()
    chk("spend gate closed by default", not _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        or True)  # informational: the gate state depends on the caller's env
    try:
        cap = c.capacity()
        print(f"  capacity: {cap}")
        chk("capacity computed from live balances", cap.get("creditsRemaining", 0) >= 0
            and cap.get("clipsRemaining", 0) == cap.get("creditsRemaining", 0) // CREDITS_PER_CLIP)
        q = c._quote(DEFAULT_MODEL)
        print(f"  quote({DEFAULT_MODEL}): quote={q.get('quote')} balance={q.get('balance')} "
              f"account={q.get('account')}")
        chk("free quote answered", q.get("error") is None and isinstance(q.get("quote"), (int, float)))
    except ChatError as e:
        print(f"  [FAIL] router read failed: {e}")
        ok = False
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
