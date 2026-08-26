"""capture_video_job_cdp.py — autonomously TRIGGER and RECORD one genuine video job.

This joins two halves that were both already built, both `[VERIFIED]`, and never connected:

  * `capture_sessions_cdp.py` — the autonomous trigger (technology transfer §3.3): the prompt goes in
    with `Input.insertText` and is READ BACK before submit, then four submit strategies are tried
    cheapest-first, **each verified against the network**, and the winner is recorded.
  * `record_video_job.py` — the passive multi-exchange recorder that writes a `recorded_job`
    (submit -> poll -> result) into `state/secrets/session_<host>.json`.

Every file carrying `recorded_job` had ZERO trigger-gesture calls, and every file with the trigger
stopped at chat's single POST. So video capture was the one path still asking for an operator's hand,
purely because nobody had joined them — not for any structural reason. No hand is needed.

Why this cannot just call the chat capture: chat's value is ONE post, so it returns on the first
sentinel POST. A video job's supply value is the WHOLE async sequence (submit -> poll... -> result
URL), which arrives over minutes. So the trigger half is reused verbatim and the recording half keeps
running after submit is verified, until a result URL appears or the sequence goes quiet.

Substitution note: `VideoUniversalSessionClient._transform_video_payload` swaps by JSON *key*
(`prompt`, `video_gen_prompt`, Digen's nested `scene_params`, ...) and only falls back to
string-replacement of the recorded text. Planting a distinctive sentinel keeps BOTH paths working, so
a provider whose key we do not know yet is still replayable.

Law 5 is absolute here: a captcha/card/quota wall is a **full stop** and a reportable outcome. The
page is checked for wall text BEFORE the composer is touched, and wall language in any response body
is reported. Nothing is ever solved, hammered, or paid.

STDOUT is metadata only — method, host+path with the query STRIPPED, status, sizes, payload key
shapes. Never a cookie, token, nonce, or query string. The wire lands in the gitignored secret.

    # prove the trigger works on a seat WITHOUT spending a clip:
    python capture_video_job_cdp.py --port 9222 --match rtst.ai --host rtst.ai --dry-run

    # the real thing (spends one clip of that seat's credits):
    python capture_video_job_cdp.py --port 9222 --match rtst.ai --host rtst.ai --seat niloy
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.parse
from typing import Any

from capture_sessions_cdp import (CDP, CDPError, JS_FOCUS_COMPOSER, JS_PAGE_TEXT, JS_READ_ACTIVE,
                                  JS_SEND, NOISE, SECRETS, WALL_TEXT, host_of, open_tab, targets)

# A legitimate, generatable scene AND a distinctive needle. A nonsense sentinel risks the provider
# refusing the job (which would look like a capture failure), and a generic one ("a cat") risks
# matching unrelated text in the body.
VIDEO_SENTINEL = ("Omni sentinel shot: a lone lighthouse beam sweeping across dark ocean waves "
                  "at midnight")

# Response-body language meaning the account cannot generate. Reported, never worked around (Law 5).
_PAYWALL = ("insufficient", "upgrade your plan", "not enough credit", "payment required", "subscribe",
            "quota exceeded", "purchase", "out of credit", "no credit", "upgrade to", "buy credits",
            "free trial has ended", "limit reached")

# Named so the capture can say WHICH auth headers exist without ever printing one.
_SENSITIVE_HDR = {"cookie", "authorization", "x-wp-nonce", "x-csrf-token", "set-cookie", "x-api-key",
                  "x-auth-token", "x-session-token", "token", "x-digen-token", "x-token"}

# Evidence the async job actually produced something. Finding one of these means the recording holds a
# complete submit->poll->result sequence, which is the whole point.
_RESULT_HINTS = ("videourl", "video_url", "\"url\"", ".mp4", "download_url", "downloadurl",
                 "resulturl", "result_url", "output_url", "outputurl", "playurl", "play_url", ".webm")

# Key fragments that look id-shaped but identify the CONNECTION, not the job. These ride along on
# every subsequent request, so a job id set containing one of them correlates with anything.
_NOT_A_JOB_ID = ("session", "token", "csrf", "nonce", "secret", "auth", "cookie", "device",
                 "client", "trace", "request", "sign", "apikey", "api_key", "visitor", "anon")


def _result_for_our_job(body: str, ids: set) -> bool:
    """Is the result in the SAME OBJECT as our job id -- not merely the same response body?

    Measured on digen: `/v1/queue/list` returns `{data:{list:[row,...]}}` where each row is one
    gallery entry. Our freshly-submitted row sits at `status:2` with an empty result, while four
    older rows sit at `status:3` carrying finished `.mp4` URLs. An id test and a `.mp4` test that
    are both scoped to the whole body therefore BOTH pass, and the recording is declared complete
    while our clip has not started. Row scoping is what makes the id test mean anything: find the
    object that actually holds our id, and demand the result evidence inside that object.

    Non-JSON bodies cannot be scoped, so they keep the body-level test -- reported as before.
    """
    try:
        doc = json.loads(body)
    except Exception:
        return any(i in body for i in ids)

    def holds_our_id(node: dict) -> bool:
        for v in node.values():
            if isinstance(v, bool) or v is None or isinstance(v, (dict, list)):
                continue
            if str(v) in ids:          # exact, so an 8-digit id cannot match inside a longer number
                return True
        return False

    def walk(node: Any) -> bool:
        if isinstance(node, dict):
            if holds_our_id(node) and _has_media_value(node):
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    return walk(doc)


def _has_media_value(node: Any) -> bool:
    """Does this subtree carry a rendered artifact in a VALUE (not merely a url-ish KEY)?

    `_RESULT_HINTS` contains `"url"`, which matches the *key* `"coverUrl":""` in a serialized row --
    so testing hints against `json.dumps(row)` says yes for a row whose result fields are all empty.
    digen's queued row is exactly that. Only a value may be evidence.
    """
    _MEDIA_EXT = (".mp4", ".webm", ".mov", ".m4v")
    _MEDIA_KEY = ("video", "result", "output", "download", "play", "render", "clip", "media")

    def walk(o: Any, key: str) -> bool:
        if isinstance(o, dict):
            return any(walk(v, k) for k, v in o.items())
        if isinstance(o, list):
            return any(walk(v, key) for v in o)
        if isinstance(o, str):
            low = o.lower()
            if any(x in low for x in _MEDIA_EXT):
                return True
            # signed URLs often carry no extension; accept one only when its key names an artifact
            return low.startswith("http") and len(o) > 20 and any(k in key.lower()
                                                                  for k in _MEDIA_KEY)
        return False

    return walk(node, "")

_BODY_CAP = 20000        # chars kept per response body; job JSON is small, video bytes are not
_SETTLE_S = 45.0         # quiet period after submit that means the sequence is finished
_TRACKERS = ("google-analytics", "googletagmanager", "doubleclick", "gstatic", "segment.", "intercom",
             "sentry", "amplitude", "mixpanel", "hotjar", "clarity.ms", "fullstory", "datadoghq",
             "posthog", "cloudflareinsights", "facebook", "tiktok", "bytedance", "recaptcha")

# Wall detection has to be POSITIONAL, not a substring scan of the page.
#
# Every free video site puts "Upgrade" in its nav and "Subscribe" in its footer. A page-text scan
# therefore reports WALL on essentially all of them, and a sweep that stops everywhere harvests
# nothing while looking like "all providers are walled" -- the same failure this codebase keeps
# hitting: a callee returning something plausible instead of the truth. Measured on digen.ai, where
# "upgrade your plan to unlock more features" sits at y=-1 (scrolled out of view) and the only real
# dialog is an App-Store download promo.
#
# So a wall counts only with EVIDENCE that it blocks generation: paywall language inside a visible,
# in-viewport, blocking element -- or a captcha, which is fatal wherever it appears. Nothing is ever
# solved, dismissed, hammered, or paid either way; this only decides STOP vs. "keep looking".
JS_WALL_PROBE = r"""(() => {
  const PAY = ['upgrade your plan','upgrade to','payment required','add a card','credit card',
               'billing','subscribe','purchase','buy credits','insufficient','not enough credit',
               'out of credit','quota exceeded','limit reached','free trial has ended',
               'verify your phone','phone number'];
  const vis = (el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden'
           && parseFloat(s.opacity || '1') > 0.1
           && r.bottom > 0 && r.top < innerHeight;          // in-viewport, not scrolled away
  };
  const out = {captcha: null, wall: null, overlay: null};

  // 1. captcha: fatal wherever it is, visible or not-yet-shown
  for (const f of document.querySelectorAll('iframe[src],div[class*=captcha],div[id*=captcha]')) {
    const h = ((f.getAttribute('src') || '') + ' ' + (f.className || '') + ' ' + (f.id || '')).toLowerCase();
    if (/recaptcha|hcaptcha|turnstile|funcaptcha|arkose|geetest|captcha/.test(h) && vis(f)) {
      out.captcha = h.slice(0, 60); return out;
    }
  }

  // 2. blocking elements only: a real dialog, or a fixed overlay covering the page
  const blockers = [];
  for (const el of document.querySelectorAll('[role=dialog],[aria-modal=true],dialog[open]')) {
    if (vis(el)) blockers.push(el);
  }
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if (s.position !== 'fixed' || parseInt(s.zIndex || '0', 10) < 10) continue;
    const r = el.getBoundingClientRect();
    if (r.width >= innerWidth * 0.85 && r.height >= innerHeight * 0.85 && vis(el)) blockers.push(el);
  }
  for (const el of blockers) {
    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
    const hit = PAY.find(p => t.includes(p));
    if (hit) { out.wall = hit; out.wallText = t.slice(0, 110); return out; }
    if (!out.overlay) out.overlay = t.slice(0, 90) || '<empty blocker>';
  }
  return out;
})()"""


def _secret_path(host: str, seat: str = "") -> pathlib.Path:
    """Same convention as record_video_job.py, so `session_pool` globs it as another seat."""
    stem = f"session_{host.replace('.', '_').replace('/', '_')}"
    return SECRETS / (f"{stem}_{seat}.json" if seat else f"{stem}.json")


def _sld(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    return parts[-2] if len(parts) >= 2 else host


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def _sentinel_forms() -> tuple[str, ...]:
    """The sentinel as it may appear in a body: raw, JSON-escaped, and both URL encodings.

    A form-encoded submit carries `+` for spaces and a JSON submit escapes nothing here, but a nested
    JSON-in-JSON string (Digen's `scene_params`, Google's envelope) double-escapes. Checking every form
    is the difference between finding our own submit and declaring the capture failed.
    """
    s = VIDEO_SENTINEL
    return (s, json.dumps(s)[1:-1], urllib.parse.quote_plus(s), urllib.parse.quote(s),
            s.replace(" ", "+"))


def _has_sentinel(body: str) -> bool:
    if not body:
        return False
    low = body.lower()
    return any(f.lower() in low for f in _sentinel_forms())


def _is_noise(url: str) -> bool:
    u = url.lower()
    return any(t in u for t in _TRACKERS) or any(n in u for n in NOISE)


def _activate(port: int, target_id: str) -> bool:
    """Wake a background tab over the DevTools HTTP endpoint BEFORE opening the websocket.

    Chrome discards idle background tabs, and a discarded target accepts a websocket but never
    answers `Runtime.enable` -- measured as "no reply in 25s" on akool/heygen/creen, which reads
    exactly like a dead seat and is not one. Activating first makes the tab reload and respond.
    """
    if not target_id:
        return False
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/activate/{target_id}", timeout=6).read()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------------------------------
# the trigger — reused verbatim from the proven chat path (§3.3), only the text differs
# --------------------------------------------------------------------------------------------------

def _key(c: CDP, key: str, code: str, vk: int, modifiers: int = 0, text: str | None = None) -> None:
    base = {"key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
            "modifiers": modifiers}
    down = dict(base, type="keyDown")
    if text is not None:
        # keyDown WITH text, never rawKeyDown: rawKeyDown suppresses the keypress event and a composer
        # listening on keypress never sees the submit.
        down["text"] = text
        down["unmodifiedText"] = text
    c.call("Input.dispatchKeyEvent", down, timeout=8)
    c.call("Input.dispatchKeyEvent", dict(base, type="keyUp"), timeout=8)


def _press_enter(c: CDP) -> None:
    _key(c, "Enter", "Enter", 13, text="\r")


def _clear_composer(c: CDP) -> None:
    """Select-all the focused composer so the following insertText REPLACES rather than appends.

    Measured on digen.ai: without this the prompt landed twice ("...at midnight...at midnight"), which
    both corrupts the generated clip and spends a real credit on garbage. Ctrl+A via genuine key events
    rather than JS: wiping `value`/`textContent` does not touch a rich editor's own document model, and
    insertText would then append to what the editor still thinks is there.
    """
    _key(c, "a", "KeyA", 65, modifiers=2)          # modifiers=2 == Ctrl on win/linux
    # No Backspace needed -- insertText overwrites the selection, and deleting first gives editors a
    # chance to re-render an empty state that drops focus.


def _fill_composer(c: CDP, focus: dict, row: dict) -> bool:
    """Clear, insertText, then READ BACK. Escalates only as far as it must. Returns whether it landed.

    Reading back matters because a disabled/undiscovered composer accepts the call and keeps nothing,
    and a capture that submits nothing looks identical to a provider that refused us.
    """
    needle = VIDEO_SENTINEL.split(":")[0]

    def landed() -> bool:
        back = (c.evaluate(JS_READ_ACTIVE) or {}).get("text") or ""
        if needle not in back:
            return False
        # Duplicate check: the needle must appear exactly once. Twice means the editor appended.
        row["fillCopies"] = back.count(needle)
        return back.count(needle) == 1

    _clear_composer(c)
    c.call("Input.insertText", {"text": VIDEO_SENTINEL})
    if landed():
        return True

    if focus.get("x") is not None:
        # Some editors wire their input handlers only after a real pointer event lands: focus() alone
        # is not enough.
        for kind in ("mousePressed", "mouseReleased"):
            c.call("Input.dispatchMouseEvent", {"type": kind, "x": focus["x"], "y": focus["y"],
                                                "button": "left", "clickCount": 1})
        time.sleep(0.4)
        _clear_composer(c)
        c.call("Input.insertText", {"text": VIDEO_SENTINEL})
        if landed():
            row["neededClick"] = True
            return True

    # Last resort: every character through the real keyboard pipeline.
    _clear_composer(c)
    _key(c, "Backspace", "Backspace", 8)
    for ch in VIDEO_SENTINEL:
        c.call("Input.dispatchKeyEvent", {"type": "char", "text": ch}, timeout=8)
    if landed():
        row["neededCharTyping"] = True
        return True
    return False


def _submit_strategies(c: CDP, row: dict) -> list[tuple[str, Any]]:
    """Four ways to submit, cheapest first. Each is VERIFIED against the network by the caller.

    `textLanded` does not prove the app agrees: it reads the DOM while a model-backed editor keeps its
    own document, so ten sites once reported text landed and emitted zero posts because Enter hit an
    "empty composer" guard.
    """
    def strat_enter() -> None:
        _press_enter(c)

    def strat_js_click() -> None:
        r = c.evaluate(JS_SEND.replace("__CLICK__", "true")) or {}
        row["sendControl"] = {k: r.get(k) for k in ("ok", "label", "score")}
        if not r.get("ok"):
            raise CDPError(f"send control: {r.get('error') or 'not found'}")

    def strat_mouse_send() -> None:
        r = c.evaluate(JS_SEND.replace("__CLICK__", "false")) or {}
        if not r.get("ok") or r.get("x") is None:
            raise CDPError(f"send control: {r.get('error') or 'not found'}")
        # A trusted pointer sequence, for apps that check event.isTrusted before acting.
        for kind, clicks in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 1)):
            c.call("Input.dispatchMouseEvent", {"type": kind, "x": r["x"], "y": r["y"],
                                                "button": "left", "clickCount": clicks})

    def strat_retype() -> None:
        f2 = c.evaluate(JS_FOCUS_COMPOSER) or {}
        if not f2.get("ok"):
            raise CDPError("composer vanished before retype")
        time.sleep(0.2)
        _key(c, "a", "KeyA", 65, modifiers=2)          # Ctrl+A / Backspace, not JS clearing: wiping
        _key(c, "Backspace", "Backspace", 8)           # textContent leaves the editor's doc untouched
        for ch in VIDEO_SENTINEL:
            _key(c, ch, "", 0, text=ch)
        time.sleep(0.3)
        _press_enter(c)

    return [("enter", strat_enter), ("js_click_send", strat_js_click),
            ("mouse_send", strat_mouse_send), ("retype_keys", strat_retype)]


# --------------------------------------------------------------------------------------------------
# the recorder — keeps running past submit, which is the whole difference from chat capture
# --------------------------------------------------------------------------------------------------

class JobRecorder:
    """Accumulates the first-party async sequence from buffered CDP Network events."""

    def __init__(self, c: CDP, api_substr: str, keep_all: bool):
        self.c = c
        self.api_substr = api_substr
        self.keep_all = keep_all
        self.reqs: dict[str, dict] = {}
        self.extra: dict[str, dict] = {}
        self.order: list[str] = []
        self.handled: set[str] = set()
        self.submit_rid: str | None = None
        self.result_seen = False
        self.result_correlated = False
        self.weak_result = False
        self.job_ids: set[str] = set()
        self.ws_seen = False           # any websocket traffic at all
        self.ws_sentinel = False       # our prompt went out over a websocket, not an HTTP POST
        self.cursor = 0                # CDP.events is append-only, so a cursor is safe
        self.t0 = time.monotonic()

    def _want(self, url: str, rtype: str) -> bool:
        if _is_noise(url):
            return False
        if rtype not in ("XHR", "Fetch", "Other", ""):
            return False
        return True if self.keep_all else (self.api_substr in url.lower())

    def drain(self) -> None:
        """Fold newly-buffered events into the sequence. Safe to call repeatedly.

        Snapshot the length first: `getResponseBody` below is itself a `c.call()`, which appends to the
        very buffer being walked.
        """
        buf = self.c.events
        upto = len(buf)
        for ev in buf[self.cursor:upto]:
            m, p = ev.get("method"), (ev.get("params") or {})
            rid = str(p.get("requestId") or "")

            if m == "Network.requestWillBeSent":
                key = f"rws:{rid}"
                if not rid or key in self.handled:
                    continue
                r = p.get("request") or {}
                url, rtype = r.get("url") or "", p.get("type") or ""
                if not self._want(url, rtype):
                    self.handled.add(key)
                    continue
                self.handled.add(key)
                self.reqs[rid] = {"seq": len(self.order), "url": url, "method": r.get("method"),
                                  "type": rtype, "headers": r.get("headers") or {},
                                  "postData": r.get("postData"), "hasPostData": r.get("hasPostData"),
                                  "ts_rel": round(time.monotonic() - self.t0, 2)}
                self.order.append(rid)

            elif m == "Network.requestWillBeSentExtraInfo":
                # The headers actually SENT, including Cookie — the recorded request_headers from
                # requestWillBeSent can be missing auth entirely (this is why Cerebras captured only
                # six headers and scored auth-dead).
                if rid in self.reqs:
                    self.extra[rid] = p.get("headers") or {}

            elif m == "Network.responseReceived":
                if rid in self.reqs:
                    rr = p.get("response") or {}
                    self.reqs[rid]["status"] = rr.get("status")
                    self.reqs[rid]["resp_headers"] = rr.get("headers") or {}
                    self.reqs[rid]["mimeType"] = rr.get("mimeType")

            elif m == "Network.loadingFinished":
                e = self.reqs.get(rid)
                if not e or "body" in e:
                    continue
                try:
                    b = self.c.call("Network.getResponseBody", {"requestId": rid}, timeout=20)
                    body = b.get("body", "") or ""
                    e["response_base64"] = bool(b.get("base64Encoded"))
                    e["body"] = body[:_BODY_CAP]
                    e["body_truncated"] = len(body) > _BODY_CAP
                except CDPError as ex:
                    e["body"] = f"<no body: {type(ex).__name__}>"
                if not e.get("postData") and e.get("hasPostData"):
                    try:
                        e["postData"] = (self.c.call("Network.getRequestPostData",
                                                     {"requestId": rid},
                                                     timeout=15).get("postData"))
                    except CDPError:
                        pass

            elif m in ("Network.webSocketCreated", "Network.webSocketFrameSent"):
                # Some composers ship the prompt over a socket. That is a real, distinct outcome
                # (WEBSOCKET in the taxonomy) -- reporting it as NO_REQUEST would send the next
                # operator hunting for a submit button that was never the mechanism.
                self.ws_seen = True
                if m == "Network.webSocketFrameSent" and _has_sentinel(
                        ((p.get("response") or {}).get("payloadData") or "")):
                    self.ws_sentinel = True

        self.cursor = upto

        # Find our own submit: the POST whose body carries the sentinel.
        if self.submit_rid is None:
            for rid in self.order:
                e = self.reqs[rid]
                if e.get("method") in ("POST", "PUT", "PATCH") and _has_sentinel(e.get("postData") or ""):
                    self.submit_rid = rid
                    self._harvest_ids()
                    break
        elif not self.job_ids:
            self._harvest_ids()          # the submit's own response body may arrive after the request
        self._recheck_result()

    def _harvest_ids(self) -> None:
        """Pull id-ish values out of the submit's RESPONSE so a later body can be tied to THIS job."""
        try:
            o = json.loads((self.reqs.get(self.submit_rid) or {}).get("body") or "")
        except Exception:
            return

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, bool) or v is None:
                        continue
                    if isinstance(v, (str, int)):
                        s, kl = str(v), k.lower()
                        # A session/trace identifier is NOT a job identifier. digen's submit answers
                        # {data:{queueId:int}, sessionId:"<36 chars>"} and sessionId rides along on
                        # every later request -- so correlating on it declares "result seen" for a
                        # clip still sitting at status=2. Exclude the per-connection identifiers
                        # BEFORE the include test, or the id set poisons the whole verdict.
                        if any(t in kl for t in _NOT_A_JOB_ID):
                            continue
                        if 4 <= len(s) <= 64 and any(t in kl for t in
                                                     ("id", "uuid", "task", "job", "queue", "key")):
                            self.job_ids.add(s)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(o)

    def _recheck_result(self) -> None:
        """A result must belong to OUR job.

        Measured the hard way on digen: `/v1/queue/list` returns the account's EXISTING gallery, so a
        naive "any body containing .mp4" test reported success for a job that had not even started.
        A result therefore counts only when the body carries an id minted by our own submit response;
        anything else is recorded as weak evidence and reported as such, never as success.
        """
        if self.submit_rid is None:
            return
        sub_seq = self.reqs[self.submit_rid]["seq"]
        for rid in self.order:
            e = self.reqs[rid]
            if e["seq"] <= sub_seq or e.get("response_base64"):
                continue
            body = e.get("body") or ""
            low = body.lower()
            if not any(h in low for h in _RESULT_HINTS):
                continue
            if self.job_ids and _result_for_our_job(body, self.job_ids):
                self.result_seen = True
                self.result_correlated = True
                return
            self.weak_result = True

    @property
    def submitted(self) -> bool:
        return self.submit_rid is not None

    def exchanges(self) -> list[dict]:
        out = []
        for rid in self.order:
            e = self.reqs[rid]
            out.append({
                "seq": e["seq"], "ts_rel": e.get("ts_rel"), "method": e.get("method"),
                "url": e.get("url"), "type": e.get("type"),
                # extra-info headers last: they are what actually went on the wire.
                "request_headers": {**e.get("headers", {}), **self.extra.get(rid, {})},
                "request_body": e.get("postData"), "status": e.get("status"),
                "mimeType": e.get("mimeType"), "response_headers": e.get("resp_headers", {}),
                "response_body": e.get("body"), "response_base64": e.get("response_base64", False),
                "body_truncated": e.get("body_truncated", False),
                "is_submit": rid == self.submit_rid,
            })
        return out


def _watch(rec: JobRecorder, seconds: float, until_submit: bool) -> bool:
    """Pump + drain for a bounded time. Returns early once the goal is met."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        rec.c.pump(0.8)
        rec.drain()
        if until_submit and rec.submitted:
            return True
        if not until_submit and rec.result_seen:
            return True
    rec.drain()
    return rec.submitted if until_submit else rec.result_seen


def capture_video(port: int, match: str, host: str, api_substr: str, seat: str, job_wait: float,
                  ready_wait: float, keep_all: bool, dry_run: bool, url: str = "") -> dict:
    row: dict[str, Any] = {"host": host, "seat": seat or None, "dryRun": dry_run}

    tabs = [t for t in targets(port) if match.lower() in (t.get("url", "") + t.get("title", "")).lower()]
    if not tabs and url:
        t = open_tab(port, url)
        if t:
            tabs = [t]
            time.sleep(3.0)
    if not tabs:
        row.update(status="NO_TAB", note=f"no page target matching {match!r} on port {port}")
        return row
    t = tabs[0]

    # Wake it first: a discarded tab answers the websocket handshake but never Runtime.enable.
    row["activated"] = _activate(port, t.get("id") or "")
    if row["activated"]:
        time.sleep(2.0)

    c = CDP(t["webSocketDebuggerUrl"], timeout=max(60.0, job_wait + 30))
    try:
        try:
            c.call("Runtime.enable", timeout=25)
        except CDPError:
            # Still asleep. bringToFront is the heavier wake; retry once before giving up, so a
            # frozen tab is not misfiled as an unreachable provider.
            c.call("Page.enable", timeout=15)
            c.call("Page.bringToFront", timeout=15)
            time.sleep(3.0)
            c.call("Runtime.enable", timeout=25)
            row["neededWake"] = True
        c.call("Page.enable")
        try:
            c.call("Page.bringToFront", timeout=12)
        except CDPError:
            pass

        # ---- Law 5 first: never touch the composer on a walled page --------------------------
        # Positional, not substring: a real captcha, or paywall language inside something that is
        # actually blocking. Nav/footer/off-screen "Upgrade" copy is not a wall and must not stop us.
        probe = c.evaluate(JS_WALL_PROBE) or {}
        if probe.get("captcha"):
            row.update(status="WALL", wall="captcha", wallDetail=probe["captcha"],
                       note="captcha present -- left untouched by policy, never solved")
            return row
        if probe.get("wall"):
            row.update(status="WALL", wall=probe["wall"], wallDetail=probe.get("wallText"),
                       note="card/credit/plan wall in a BLOCKING element -- STOP, never pay or "
                            "work around; this is a reportable outcome, not a failure")
            return row
        if probe.get("overlay"):
            # Not a wall (no payment language), but it sits over the composer. Recorded so a
            # NO_COMPOSER below is attributable to the overlay rather than a missing composer.
            row["overlay"] = probe["overlay"]

        # A discarded tab RELOADS when activated, so the first DOM look lands on a booting page.
        # Poll for the composer instead of guessing a sleep.
        focus: dict = {}
        deadline = time.monotonic() + ready_wait
        while time.monotonic() < deadline:
            if (c.evaluate("document.readyState") or "") == "complete":
                focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
                if focus.get("ok"):
                    break
            time.sleep(1.5)
        row["readyState"] = c.evaluate("document.readyState")
        if not focus.get("ok"):
            # No composer AND paywall language somewhere on the page: that is a wall rendered inline
            # (a /pricing interstitial, an "out of credits" body) rather than a dialog, which the
            # positional probe deliberately ignores. Attribute it honestly instead of blaming the
            # composer -- "NO_COMPOSER" would send the next run hunting for a selector bug.
            page_text = (c.evaluate(JS_PAGE_TEXT) or "").lower()
            inline = next((w for w in WALL_TEXT if w in page_text), None)
            if inline:
                row.update(status="WALL", wall=inline,
                           note="no composer and paywall language on the page -- inline wall; STOP, "
                                "do not pay or work around")
                return row
            row.update(status="NO_COMPOSER", detail=(focus or {}).get("error") or "page never ready",
                       note="overlay was in the way" if row.get("overlay") else
                            "no text input found -- likely the wrong page (a gallery/explore page "
                            "rather than the generate page); try --url")
            return row
        row["composer"] = {k: focus.get(k) for k in ("tag", "editable", "candidates")}

        # Network on only now: enabling earlier buries the submit under page-load traffic.
        c.call("Network.enable")
        rec = JobRecorder(c, api_substr, keep_all)

        landed = _fill_composer(c, focus, row)
        row["textLanded"] = bool(landed)
        if not landed:
            row.update(status="TEXT_REJECTED",
                       note="composer did not accept the prompt -- nothing was submitted")
            return row

        if dry_run:
            # Everything that proves the trigger works, minus the one act that costs a clip.
            row.update(status="DRY_RUN_OK",
                       note="composer found and prompt landed; submit deliberately NOT sent")
            return row

        # ---- submit: try, then VERIFY against the network -----------------------------------
        row["strategiesTried"] = []
        per = max(8.0, min(40.0, job_wait / 6.0))
        for label, fn in _submit_strategies(c, row):
            try:
                fn()
            except CDPError as e:
                row.setdefault("strategySkipped", {})[label] = str(e)[:90]
                continue
            row["strategiesTried"].append(label)
            if _watch(rec, per, until_submit=True):
                row["submitStrategy"] = label
                break

        if not rec.submitted:
            rec.drain()
            if rec.ws_sentinel:
                row.update(status="WEBSOCKET", exchangesSeen=len(rec.order),
                           note="the prompt was submitted over a WebSocket, not an HTTP POST -- the "
                                "HTTP replay engine cannot serve this seat as-is")
                return row
            row.update(status="NO_REQUEST", exchangesSeen=len(rec.order),
                       websocketTraffic=rec.ws_seen or None,
                       note=f"all submit strategies failed; {len(rec.order)} first-party "
                            f"exchange(s) seen but none carried the prompt")
            return row

        # ---- the video-specific half: keep recording poll -> result -------------------------
        # Chat stops here. A video seat is only supply once the poll shape and the result URL are on
        # record, so keep going until the URL appears or the sequence goes quiet.
        end = time.monotonic() + job_wait
        last_n = len(rec.order)
        quiet_since = time.monotonic()
        while time.monotonic() < end and not rec.result_seen:
            _watch(rec, 5.0, until_submit=False)
            if len(rec.order) != last_n:
                last_n = len(rec.order)
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since > _SETTLE_S:
                break

        # ---- persist ------------------------------------------------------------------------
        jar = c.call("Network.getCookies", {"urls": [t.get("url", ""), f"https://{host}/"]})
        cookies = jar.get("cookies", []) or []
        cookie_header = "; ".join(f"{k['name']}={k['value']}" for k in cookies)

        # Where it lands depends on whether it is PROVEN supply. An uncorrelated capture written into
        # state/secrets/ is served by :8189 as if it were a working seat, so an unproven recording goes
        # to a holding directory instead: evidence kept, pool untouched.
        proven = rec.result_correlated
        if proven:
            path = _secret_path(host, seat)
        else:
            hold = SECRETS.parent / "captures_pending"
            path = hold / (_secret_path(host, seat).name)

        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"host": host}
        data["cookie_header"] = cookie_header
        data["sentinel"] = VIDEO_SENTINEL
        data["updated_at"] = int(time.time())
        data["recorded_job"] = {"recorded_at": int(time.time()), "api_substr": api_substr,
                                "sentinel": VIDEO_SENTINEL, "captured_by": "capture_video_job_cdp",
                                "submit_seq": rec.reqs[rec.submit_rid]["seq"],
                                "result_seen": rec.result_seen,
                                "result_correlated": rec.result_correlated,
                                "job_id_count": len(rec.job_ids),
                                "exchanges": rec.exchanges()}
        if proven:
            # setdefault, never assignment: a host serving BOTH chat and video (veoaifree) must keep
            # its declared modality rather than having its chat dispatch silently converted to video.
            data.setdefault("modality", "video")
        else:
            data["replayable"] = False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)                      # atomic: a half-written secret takes a seat off the pool

        ex = rec.exchanges()
        walled = [e["seq"] for e in ex
                  if e.get("status") == 402
                  or any(w in str(e.get("response_body") or "").lower() for w in _PAYWALL)]
        sub_url = _strip_query(rec.reqs[rec.submit_rid]["url"]).lower()
        # A composer is not always THE composer. On digen the explore-page box created a project
        # ("task_queue_category/create") rather than a clip, and banking that as a video seat would
        # have the :8189 face serving folder-creation calls as generations.
        odd = next((w for w in ("category", "folder", "project/create", "feedback", "comment",
                                "search", "login", "track", "space/create") if w in sub_url), None)
        row.update(status="CAPTURED" if rec.result_correlated else "CAPTURED_NO_RESULT",
                   exchanges=len(ex), submitStrategy=row.get("submitStrategy"),
                   resultSeen=rec.result_seen, resultCorrelated=rec.result_correlated,
                   weakResult=rec.weak_result or None, cookieCount=len(cookies),
                   submitEndpointOdd=odd, walledExchanges=walled or None, file=str(path))
        if not rec.result_correlated:
            row["note"] = ("submit landed but no result could be tied to this job's id -- either the "
                           "queue is slower than --job-wait, or this endpoint does not generate. "
                           "NOT replayable supply yet; re-run with a longer --job-wait.")
        return row
    except CDPError as e:
        d = str(e)[:140]
        frozen = "no reply" in d.lower()
        row.update(status="FAULT_FROZEN" if frozen else "CDP_ERROR", detail=d,
                   note="tab is discarded/frozen -- self-healable; see chrome_no_discard.py "
                        "(close Chrome before --apply). NOT an auth problem." if frozen else None)
        return row
    except Exception as e:                      # one bad tab must never end a sweep
        row.update(status="CDP_ERROR", detail=f"{type(e).__name__}: {str(e)[:120]}")
        return row
    finally:
        c.close()


def _report(row: dict) -> None:
    """Metadata only — never a cookie, token, nonce, or query string."""
    print()
    print(f"[capture-video] {row.get('host')}"
          f"{'/' + row['seat'] if row.get('seat') else ''}  ->  {row.get('status')}")
    for k in ("note", "detail", "wall", "wallDetail", "overlay", "submitStrategy", "textLanded",
              "neededClick", "neededCharTyping", "resultSeen", "exchanges", "exchangesSeen",
              "websocketTraffic", "cookieCount", "readyState"):
        if row.get(k) is not None:
            print(f"    {k:18s} {row[k]}")
    if row.get("composer"):
        print(f"    {'composer':18s} {row['composer']}")
    if row.get("strategySkipped"):
        print(f"    {'strategySkipped':18s} {row['strategySkipped']}")
    if row.get("walledExchanges"):
        print(f"    {'walledExchanges':18s} {row['walledExchanges']}  "
              f"<< credit/plan language present -- STOP, do not pay (Law 5)")
    if row.get("file"):
        print(f"    {'file':18s} {row['file']}  (secret; gitignored)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9222, help="CDP port of the ROBOT Chrome")
    ap.add_argument("--match", required=True, help="substring of the provider tab url/title")
    ap.add_argument("--host", required=True, help="cookie host / secret file key")
    ap.add_argument("--url", default="", help="open a tab at this URL if none matches")
    ap.add_argument("--api-substr", default=None,
                    help="only record URLs containing this (default: the host's second-level label)")
    ap.add_argument("--seat", default="",
                    help="account label; writes session_<host>_<seat>.json so a second account of the "
                         "SAME provider is another pool seat rather than an overwrite")
    ap.add_argument("--job-wait", type=float, default=420.0,
                    help="seconds to keep recording poll->result after submit is verified")
    ap.add_argument("--ready-wait", type=float, default=25.0, help="seconds to wait for the composer")
    ap.add_argument("--keep-all", action="store_true", help="record all XHR/Fetch, not just first-party")
    ap.add_argument("--dry-run", action="store_true",
                    help="find the composer and land the prompt, then STOP without submitting. Proves "
                         "the trigger on a live seat without spending a clip.")
    a = ap.parse_args()

    row = capture_video(a.port, a.match, a.host, (a.api_substr or _sld(a.host)).lower(), a.seat,
                        a.job_wait, a.ready_wait, a.keep_all, a.dry_run, a.url)
    _report(row)
    return 0 if row.get("status") in ("CAPTURED", "CAPTURED_NO_RESULT", "DRY_RUN_OK") else 1


if __name__ == "__main__":
    raise SystemExit(main())
