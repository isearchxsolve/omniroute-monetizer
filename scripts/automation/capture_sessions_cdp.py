#!/usr/bin/env python3
"""Capture a genuine chat exchange per provider, over RAW CDP, and save it for replay.

Why not launch_and_harvest_chats.py
-----------------------------------
That script cannot reach the seat that holds the sign-ins, and when it does reach one it can write
files the replay client rejects. Three concrete defects, all measured 2026-08-26:

  * it connects with playwright `connect_over_cdp`, which attaches to EVERY target before returning.
    The `providers` seat holds 69 tabs and that call timed out at 15s and again at 90s. This script
    opens one websocket straight to one page target, so tab count is irrelevant.

  * its capture filter accepts a body containing merely `"prompt"` or `"messages"`
    (launch_and_harvest_chats.py:205). `universal_replay.py:253` then refuses the file with
    SENTINEL_NOT_FOUND, because with no sentinel in the body there is nothing to string-replace and
    a replay would re-send the recorded prompt forever. That is how the sentinel-less session files
    in state/secrets came to exist. Here the sentinel is a hard precondition: no sentinel, no file.

  * it sets `inputEl.innerText` on contenteditable composers. Every modern editor (ProseMirror,
    Lexical, Slate -- ChatGPT, Claude, Perplexity, Gemini) ignores that, and because the element WAS
    found the keyboard fallback never fires, so the tab reports success and sends nothing. Here the
    text goes in with `Input.insertText` and is then READ BACK before Enter is dispatched; a composer
    that did not accept the text is reported as such and never counted as a capture.

The omni way
------------
One sentinel prompt for every provider -- no per-provider adapters. Submit it in a real signed-in
tab, record the genuine outgoing POST plus the cookie jar, and at call time string-replace the
sentinel with the real prompt. Never reconstruct a request from scratch; reconstruction gets gated.

Walls are terminal, not retryable
---------------------------------
A captcha, a card prompt, a phone-verify or a quota/upgrade wall means STOP for that provider. It is
recorded as a wall and the tab is left completely alone -- never solved, never hammered, never paid.

Secrets
-------
Cookie values and request bodies are written only into state/secrets/ (gitignored). Nothing secret
reaches stdout: the log prints hosts, paths, byte counts and booleans.

Usage
-----
    python capture_sessions_cdp.py --list                       # what is capturable right now
    python capture_sessions_cdp.py --sites "Puter Chat,DeepSeek Chat"
    python capture_sessions_cdp.py --output-dir state/candidates/example --sites "Aymo AI"
    python capture_sessions_cdp.py --volatile-first --limit 3   # session_only sites first
    python capture_sessions_cdp.py --all --limit 10
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
SECRETS = STATE / "secrets"
SITES_FILE = STATE / "free_llm_chat_sites.json"
READINESS = STATE / "seat_readiness.json"
REPORT = STATE / "capture_report.json"

SENTINEL = "Reply exactly one word: Omni."

# Kept in sync with universal_replay.py's placeholder list -- a body that encodes the sentinel is
# still replayable, so it is still a valid capture.
SENTINEL_FORMS = (
    SENTINEL,
    urllib.parse.quote_plus(SENTINEL),
    urllib.parse.quote(SENTINEL),
    json.dumps(SENTINEL)[1:-1],          # JSON-escaped, in case of nested-string bodies
)

# A POST carrying the sentinel to one of these is instrumentation, not the chat call.
NOISE = ("telemetry", "analytics", "tracking", "/track", "beacon", "segment", "sentry",
         "metrics", "/log", "logging", "clarity.ms", "doubleclick", "google-analytics",
         "browser.events.data.microsoft.com", "datadog", "amplitude", "mixpanel", "posthog",
         "/title", "/translatehtml")



WALL_TEXT = ("verify you are human", "i'm not a robot", "im not a robot", "recaptcha", "hcaptcha",
             "cloudflare", "complete the captcha", "add a payment method", "add payment method",
             "enter your card", "credit card", "upgrade to continue", "upgrade your plan",
             "subscribe to continue", "you've reached your limit", "youve reached your limit",
             "message limit reached", "out of credits", "insufficient credits", "free trial ended",
             "verify your phone", "phone number to continue", "confirm your identity")

# free_llm_chat_sites.json holds each provider's MARKETING url. Measured 2026-08-26: six sites
# reported NO_COMPOSER purely because the tab was sitting on a landing page or a dashboard, not on
# the chat app -- console.groq.com/home has no composer, console.groq.com/playground does. Two of
# these providers also serve chat from a different registrable domain than they market from, which is
# why the override carries the full url rather than a path.
#
# A site listed here always gets a FRESH tab at the override, because reusing the tab that is already
# open would land back on the page that has no composer.
CHAT_URL_OVERRIDES = {
    "Groq Chat": "https://console.groq.com/playground",
    "Coze Web": "https://www.coze.com/home",
    "Microsoft Copilot Web": "https://copilot.microsoft.com/",
    "SambaNova Cloud Chat": "https://cloud.sambanova.ai/playground",
    "iFlytek SparkDesk": "https://xinghuo.xfyun.cn/desk",
    "StepFun Web": "https://yuewen.cn/chat",              # StepFun ships chat as Yuewen
    "Baichuan Web": "https://ying.baichuan-ai.com/chat",  # yi.* is the model page, ying.* is chat
    "Together AI Chat": "https://api.together.ai/playground/v2/chat",
    "Claude Official Web": "https://claude.ai/new",
}



# Video generators. They have no chat composer, so a chat sweep can only ever report NO_COMPOSER for
# them -- which reads as a failure when it is a category error. They are Task 2's targets and are
# skipped explicitly here rather than silently.
VIDEO_ONLY = ("Google Flow (labs.google)", "rtst.ai", "digen.ai")


# Finds the composer, focuses it, and reports what it found. Focus is all that is needed -- the text
# then arrives via Input.insertText, which every editor honours because it is a real IME-level edit.
JS_FOCUS_COMPOSER = r"""
(() => {
  const shadows = (root, acc = []) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
    return acc;
  };
  const roots = [document, ...shadows(document)];
  const cands = [];
  for (const r of roots) {
    for (const el of r.querySelectorAll('textarea, [contenteditable="true"], [contenteditable=""], input[type="text"], input[type="search"]')) {
      const rect = el.getBoundingClientRect();
      const st = el.ownerDocument.defaultView.getComputedStyle(el);
      if (rect.width < 80 || rect.height < 18) continue;
      if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) === 0) continue;
      if (el.disabled || el.readOnly) continue;
      // Prefer the biggest box that sits low on the page: that is the composer, not a search field.
      // Area alone can lie: on Google Flow a wide 370x38 search bar at top=19 out-scored the slim
      // 522x20 one-line contenteditable composer at top=629, and the prompt landed in search.
      // Editable affordances (textarea / contenteditable / role=textbox) are almost always the
      // composer, so give them a decisive bonus over plain inputs.
      let bonus = 0;
      if (el.tagName === 'TEXTAREA') bonus = 1000000;
      else if (el.isContentEditable || (el.getAttribute && el.getAttribute('role') === 'textbox')) bonus = 1000000;
      if (el.id && el.id.toLowerCase().includes('prompt')) bonus += 5000000;
      if (el.placeholder && el.placeholder.toLowerCase().includes('message')) bonus += 5000000;
      if ((el.placeholder && el.placeholder.toLowerCase().includes('search')) ||
          (el.getAttribute && (el.getAttribute('aria-label') || '').toLowerCase().includes('search'))) bonus -= 5000000;
      cands.push({ el, score: rect.width * rect.height + rect.top * 2 + bonus });
    }
  }
  if (!cands.length) return { ok: false, error: 'no visible composer' };
  cands.sort((a, b) => b.score - a.score);
  const el = cands[0].el;
  el.scrollIntoView({ block: 'center' });
  el.focus();
  const r = el.getBoundingClientRect();
  return { ok: true, tag: el.tagName.toLowerCase(),
           editable: el.isContentEditable === true,
           candidates: cands.length, score: cands[0].score,
           x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
})()
"""

# Reads back whatever the focused composer now holds. Pierces shadow roots, because
# document.activeElement stops at the shadow host.
JS_READ_ACTIVE = r"""
(() => {
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  if (!a) return { ok: false, text: '' };
  const t = ('value' in a && typeof a.value === 'string') ? a.value : (a.innerText || a.textContent || '');
  return { ok: true, tag: a.tagName.toLowerCase(), text: String(t).slice(0, 400) };
})()
"""

JS_PAGE_TEXT = "(() => (document.body ? document.body.innerText : '').slice(0, 6000))()"

# 4th composer strategy: DIRECT ELEMENT TARGETING. Strategies 1-3 deliver text through the browser's
# own input pipeline (IME insertText / pointer+insertText / per-char key events) and model-backed
# editors (ProseMirror/Lexical-class) rejected all of them. Those editors still hold their model in
# the DOM element's handlers, so the remaining gap is editors that ignore emulated input but DO run
# their input/change listeners when the element's own content is rewritten. This snippet re-locates
# the composer with the same scoring as JS_FOCUS_COMPOSER (shadow-piercing, biggest editable box low
# on the page), focuses it, writes the sentinel through it, and dispatches input+change so framework
# listeners execute. Two write paths, because they fail differently:
#   - contenteditable -> textContent assignment;
#   - textarea/input  -> the NATIVE prototype .value setter. React tracks .value and silently reverts
#     a naive `el.value = x`, but a setter call from HTMLTextAreaElement/HTMLInputElement.prototype
#     (el.constructor.prototype) is the one React's own event delegation honours.
# `__SENTINEL_JSON__` is replaced from Python with the JSON-quoted sentinel literal.
JS_FORCE_TEXT = r"""
(() => {
  const SENT = __SENTINEL_JSON__;
  const shadows = (root, acc = []) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
    return acc;
  };
  const roots = [document, ...shadows(document)];
  const cands = [];
  for (const r of roots) {
    for (const el of r.querySelectorAll('textarea, [contenteditable="true"], [contenteditable=""], input[type="text"], input[type="search"]')) {
      const rect = el.getBoundingClientRect();
      const st = el.ownerDocument.defaultView.getComputedStyle(el);
      if (rect.width < 80 || rect.height < 18) continue;
      if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) === 0) continue;
      if (el.disabled || el.readOnly) continue;
      let bonus = 0;
      if (el.tagName === 'TEXTAREA') bonus = 1000000;
      else if (el.isContentEditable || (el.getAttribute && el.getAttribute('role') === 'textbox')) bonus = 1000000;
      if (el.id && el.id.toLowerCase().includes('prompt')) bonus += 5000000;
      if (el.placeholder && el.placeholder.toLowerCase().includes('message')) bonus += 5000000;
      if ((el.placeholder && el.placeholder.toLowerCase().includes('search')) ||
          (el.getAttribute && (el.getAttribute('aria-label') || '').toLowerCase().includes('search'))) bonus -= 5000000;
      cands.push({ el, score: rect.width * rect.height + rect.top * 2 + bonus });
    }
  }
  if (!cands.length) return { ok: false, error: 'no visible composer' };
  cands.sort((a, b) => b.score - a.score);
  const el = cands[0].el;
  el.scrollIntoView({ block: 'center' });
  el.focus();
  const tag = el.tagName.toLowerCase();
  const editable = el.isContentEditable === true;
  let via = 'none';
  try {
    if (editable) {
      el.textContent = SENT;
      via = 'textContent';
    } else {
      const desc = Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value');
      const setter = (desc && desc.set) || null;
      if (setter) { setter.call(el, SENT); via = 'native-value-setter'; }
      else { el.value = SENT; via = 'plain-value'; }
    }
  } catch (e) {
    if (editable) { el.textContent = SENT; via = 'textContent-fallback'; }
    else { el.value = SENT; via = 'plain-value-fallback'; }
  }
  try { el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true })); }
  catch (e) { try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e2) {} }
  try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  const t = ('value' in el && typeof el.value === 'string') ? el.value : (el.innerText || el.textContent || '');
  return { ok: true, tag, editable, via,
           landedHere: String(t).indexOf(SENT.split(':')[0]) !== -1 };
})()
"""

# Finds -- and optionally clicks -- the send control. Needed because Enter is not universal: some
# composers treat it as a newline and only submit on the button, and a few bind the handler to the
# button alone. Deliberately prefers a button that sits to the RIGHT of and level with the composer,
# which is where send lives, over any button merely containing an svg (that matches attach, mic and
# settings buttons too, which is what launch_and_harvest_chats.py:108 gets wrong).
#
# `__CLICK__` is substituted with true/false so the same scoring serves two strategies: a JS .click()
# and a real trusted mouse event at the returned coordinates.
JS_SEND = r"""
(() => {
  const shadows = (root, acc = []) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
    return acc;
  };
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  const box = a ? a.getBoundingClientRect() : null;
  const composerForm = a ? (a.closest ? a.closest('form') : null) : null;
  const roots = [document, ...shadows(document)];
  const words = ['send', 'submit', 'ask', 'search', 'generate', 'run',
                 '\u53d1\u9001', '\u63d0\u4ea4', '\u9001\u4fe1', '\uc804\uc1a1', '\ubcf4\ub0b4\uae30'];
  let best = null, bestScore = -1, disabledMatches = 0;
  for (const r of roots) {
    for (const b of r.querySelectorAll('button, [role="button"], input[type="submit"]')) {
      const rect = b.getBoundingClientRect();
      if (rect.width < 12 || rect.height < 12) continue;
      const label = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '') +
                     ' ' + (b.getAttribute('data-testid') || '') + ' ' +
                     (b.innerText || b.textContent || '')).toLowerCase().trim();
      let score = 0;
      if (words.some(w => label.includes(w))) score += 100;
      if (b.type === 'submit') score += 40;
      if (box && rect.left >= box.right - 90 && Math.abs(rect.top - box.top) < box.height + 60) score += 60;
      if (box && rect.top > box.top - 120 && rect.bottom < box.bottom + 120) score += 20;
      // Suggestion chips masquerade as send controls: right of the composer, vertically level,
      // no send word -- exactly +80 like a real icon-only send button, and on yi.baichuan-ai.com
      // the chip ("Interpretation of medical orders") won the tie and the submit went nowhere.
      // Two discriminators that never hurt a real send button:
      if (label.length > 24 || label.split(/\s+/).length >= 4) score -= 60;   // sentence-like chip
      if (composerForm && composerForm.contains(b)) score += 50;              // lives with the composer
      if (score <= 0) continue;
      // A MATCHING BUT DISABLED send button is the most valuable diagnostic on the page: it means
      // the app's own editor model still thinks the composer is empty, so Enter was never going to
      // submit either. Counted rather than silently skipped.
      if (b.disabled || b.getAttribute('aria-disabled') === 'true') { disabledMatches++; continue; }
      if (score > bestScore) { bestScore = score; best = b; }
    }
  }
  if (!best) return { ok: false, error: 'no enabled send control', disabledMatches };
  if (__CLICK__) best.click();
  const r2 = best.getBoundingClientRect();
  return { ok: true, score: bestScore, clicked: __CLICK__, disabledMatches,
           label: ((best.getAttribute('aria-label') || best.innerText || '') + '').trim().slice(0, 40),
           x: Math.round(r2.left + r2.width / 2), y: Math.round(r2.top + r2.height / 2) };
})()
"""


class CDPError(RuntimeError):
    pass


def assert_safe_cdp_port(port: int) -> None:
    """Fail closed before raw HTTP/WebSocket CDP access.

    The Playwright guard cannot intercept direct urllib and websocket-client use.
    This local gate refuses any endpoint advertised by the operator's live Chrome
    tree.  Callers that need stronger process/profile attestation use
    tab_graduation_sweep.py first; this is the non-bypassable minimum for direct
    invocation of this script.
    """
    try:
        from chrome_live_guard import assert_cdp_safe
    except Exception as exc:
        raise CDPError(f"chrome live-profile guard unavailable: {type(exc).__name__}") from exc
    try:
        assert_cdp_safe(f"http://127.0.0.1:{port}")
    except Exception as exc:
        raise CDPError(f"refusing raw CDP access on :{port}: {type(exc).__name__}") from exc


class CDP:
    """One websocket to ONE page target. Flat session: no sessionId plumbing needed.

    `suppress_origin` is required -- Chrome's DevTools endpoint refuses a handshake that carries an
    Origin header, and websocket-client sends one by default.
    """

    def __init__(self, ws_url: str, timeout: float = 30.0):
        import websocket                                        # websocket-client
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True,
                                              max_size=96 * 1024 * 1024)
        self._wse = websocket
        self._id = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = self._recv(end)
            if msg is None:
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(f"{method}: {str(msg['error'])[:120]}")
                return msg.get("result") or {}
            if "method" in msg:
                self.events.append(msg)                         # keep, we are mid-capture
        raise CDPError(f"{method}: no reply in {timeout}s")

    def _recv(self, end: float) -> dict | None:
        self.ws.settimeout(max(0.4, end - time.monotonic()))
        try:
            return json.loads(self.ws.recv())
        except self._wse.WebSocketTimeoutException:
            return None
        except (ValueError, self._wse.WebSocketException):
            return None

    def pump(self, seconds: float) -> list[dict]:
        """Collect events for a while, returning everything buffered so far."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            msg = self._recv(end)
            if msg and "method" in msg:
                self.events.append(msg)
        return self.events

    def evaluate(self, expr: str, timeout: float = 20.0) -> Any:
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True},
                      timeout=timeout)
        if r.get("exceptionDetails"):
            raise CDPError(f"eval: {str(r['exceptionDetails'])[:120]}")
        return (r.get("result") or {}).get("value")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def has_sentinel(body: str) -> bool:
    return any(f in body for f in SENTINEL_FORMS if f)


def capture_payload(hits: list[dict], cookie_header: str, site: str,
                    pending: bool = False) -> dict[str, Any]:
    """Build the session artifact from the ordered sentinel-bearing exchanges.

    `hits` is ordered as Chrome sent them. The FIRST exchange stays in `recorded_exchange`
    (the schema every replay reader consumes), so a single-exchange artifact is byte-shape
    identical to the pre-multi-exchange format. When a multi-step flow produced more than
    one sentinel-bearing POST (chatgpt prepare -> conversation, giz planner ->
    assistantMessage -- both measured), every exchange is additionally stored, in order, in
    `recorded_exchanges`; replay walks them as one pipeline with values threaded forward.
    Dropping the later exchanges was the first-hit selection defect (Giz RCA #1190/#1194):
    the seat's real answer transport was discarded because an earlier sentinel POST won.
    """
    if not hits:
        raise ValueError("capture_payload: no sentinel-bearing exchanges")
    first = hits[0]
    payload: dict[str, Any] = {
        "host": first["host"],
        "modality": "chat",
        "site": site,
        "sentinel": SENTINEL,
        "updated_at": int(time.time()),
        "cookie_header": cookie_header,
        "recorded_exchange": {"url": first["url"], "method": first.get("method"),
                              "request_headers": first.get("request_headers") or {},
                              "cookie_header": cookie_header,
                              "request_body": first.get("request_body") or "",
                              "host": first["host"]},
        "status": {"alive": not pending,
                   "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "reason": "pending_replay_verification" if pending else "capture_sessions_cdp"},
    }
    payload["exchangeCount"] = len(hits)
    if len(hits) > 1:
        payload["recorded_exchanges"] = [
            {"url": h["url"], "method": h.get("method"),
             "request_headers": h.get("request_headers") or {},
             "request_body": h.get("request_body") or "", "host": h["host"]}
            for h in hits]
    return payload


def targets(port: int) -> list[dict]:
    assert_safe_cdp_port(port)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return [t for t in data if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]


def reg(host: str) -> str:
    parts = (host or "").lstrip(".").lower().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def slug(name: str) -> str:
    """Site display name -> secrets filename stem. One definition, used by both the writer and the
    already-done check; they were spelled differently before, so every captured site was retried."""
    return name.replace(" ", "_").replace("/", "_").replace(".", "_").lower()


def atomic_json_write(path: pathlib.Path, payload: dict[str, Any]) -> None:
    """Write a capture atomically so a hot-scanning pool never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def validated_session_filename(name: str | None, site: str) -> str:
    """Return one safe, pool-recognised filename for a captured artifact."""
    candidate = name or f"session_{slug(site)}.json"
    path = pathlib.PurePath(candidate)
    if path.name != candidate or not candidate.startswith("session_") or not candidate.endswith(".json"):
        raise ValueError("output filename must be a simple session_*.json basename")
    return candidate


def open_tab(port: int, url: str) -> dict | None:
    """Open a tab and return its target once it has a debugger url.

    A full sweep has to reach providers with no tab open. Chrome's `/json/new` moved to PUT, so that
    is tried first and `Target.createTarget` over the browser websocket is the fallback for builds
    that refuse it.
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe=':/?=&')}",
                                     method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            t = json.loads(r.read().decode("utf-8", "replace"))
        if t.get("webSocketDebuggerUrl"):
            return t
    except Exception:
        pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=8) as r:
            ws_url = json.loads(r.read().decode("utf-8", "replace"))["webSocketDebuggerUrl"]
        b = CDP(ws_url)
        try:
            tid = b.call("Target.createTarget", {"url": url}).get("targetId")
        finally:
            b.close()
        if not tid:
            return None
        for _ in range(20):                                       # the target list lags the create
            time.sleep(0.5)
            for t in targets(port):
                if t.get("id") == tid and t.get("webSocketDebuggerUrl"):
                    return t
    except Exception:
        return None
    return None


def site_catalog() -> dict[str, str]:
    """name -> url, from the provider directory plus the video generators."""
    out = {"veoaifree": "https://veoaifree.com/", "rtst.ai": "https://rtst.ai/",
           "digen.ai": "https://digen.ai/",
           # Named exactly as seat_readiness_audit.py's VIDEO_TARGETS spells it, or a full sweep
           # reports the seat-defining video provider as "unknown site name" and skips it.
           "Google Flow (labs.google)": "https://labs.google/fx/tools/flow"}
    if SITES_FILE.exists():
        for g in json.loads(SITES_FILE.read_text(encoding="utf-8")):
            for s in g.get("sites") or []:
                if s.get("url"):
                    out[s.get("name") or host_of(s["url"])] = s["url"]
    return out


def plan(a: argparse.Namespace) -> list[tuple[str, str, str]]:
    """[(site name, url, verdict)] to attempt, in priority order."""
    cat = site_catalog()
    if a.sites:
        wanted = [s.strip() for s in a.sites.split(",") if s.strip()]
        return [(w, cat.get(w, ""), "requested") for w in wanted]

    if not READINESS.exists():
        raise SystemExit("run seat_readiness_audit.py first (no state/seat_readiness.json)")
    rd = json.loads(READINESS.read_text(encoding="utf-8"))

    # Only the seat that OWNS this port. A sweep that attempts every seat's sites on one Chrome
    # captures anonymous tabs for the sites that seat never signed into -- a session file with no
    # auth in it, which is worse than no file at all because it looks like supply.
    seat_rows = rd.get("seats", [])
    if not a.any_seat:
        mine = [s for s in seat_rows if a.port in (s.get("ports") or [])]
        if mine:
            seat_rows = mine

    best: dict[str, str] = {}
    for seat in seat_rows:
        for name, s in (seat.get("sites") or {}).items():
            v = s.get("verdict")
            # session_only outranks signed_in_probable here on purpose: it is the one that is LOST
            # when that Chrome closes, so it is the one worth spending the next minute on.
            rank = {"session_only": 0, "signed_in_probable": 1}.get(v)
            if rank is None:
                continue
            if name not in best or rank < {"session_only": 0, "signed_in_probable": 1}[best[name]]:
                best[name] = v
    done = {p.stem for p in SECRETS.glob("session_*.json")} if SECRETS.exists() else set()
    rows = [(n, cat.get(n, ""), v) for n, v in best.items()]
    rows.sort(key=lambda r: (0 if r[2] == "session_only" else 1, r[0]))
    if not a.all and not a.volatile_first:
        rows = [r for r in rows if r[2] == "session_only"]
    return [r for r in rows if f"session_{slug(r[0])}" not in done]


def capture(t: dict, name: str, verdict: str, wait: float, ready_wait: float = 25.0,
            output_dir: pathlib.Path = SECRETS, output_name: str | None = None,
            pending: bool = False) -> dict[str, Any]:
    """Submit the sentinel in this tab and record the genuine request it produces."""
    row: dict[str, Any] = {"site": name, "tabUrl": t.get("url", "")[:120],
                           "readinessVerdict": verdict}
    # A tab can close between /json/list and this connect -- Chrome then answers the handshake with
    # "500 No such target id", which is a raw WebSocketBadStatusException, not a CDPError. Left
    # unhandled it killed a whole seat's run with sites still queued. It is a stale tab, not a fault.
    try:
        c = CDP(t["webSocketDebuggerUrl"])
    except Exception as e:
        row.update(status="STALE_TAB", detail=f"{type(e).__name__}: {str(e)[:100]}",
                   note="tab disappeared before it could be attached to -- nothing was submitted")
        return row
    try:
        # A backgrounded tab has a throttled or discarded renderer, and Runtime.enable is
        # renderer-bound: it simply never answers. Measured 11 of 22 tabs failing exactly that way.
        # Page.bringToFront is browser-side, so it still works on a frozen tab and thaws it. This
        # ordering is the whole reason the playwright harvester called bring_to_front() first.
        try:
            c.call("Page.bringToFront", timeout=12)
            time.sleep(1.2)
        except CDPError:
            pass                                                # not fatal; Runtime.enable may work
        try:
            c.call("Runtime.enable", timeout=20)
        except CDPError:
            c.call("Page.bringToFront", timeout=12)              # one retry after a forced activate
            time.sleep(2.0)
            c.call("Runtime.enable", timeout=25)
        c.call("Page.enable")

        page_text = (c.evaluate(JS_PAGE_TEXT) or "").lower()
        hit = next((w for w in WALL_TEXT if w in page_text), None)
        if hit:
            # Terminal. Do not touch the composer, do not retry, do not attempt to satisfy it.
            row.update(status="WALL", wall=hit,
                       note="captcha/card/quota wall on the page -- left untouched by policy")
            return row

        # Activating a discarded tab makes Chrome RELOAD it, so the first look at the DOM lands on a
        # page that is still booting. Measured: 9 of 13 thawed tabs reported "no visible composer"
        # on an immediate search and had one moments later. Poll instead of guessing a sleep.
        focus: dict = {}
        deadline_ready = time.monotonic() + ready_wait
        while time.monotonic() < deadline_ready:
            state = c.evaluate("document.readyState") or ""
            if state == "complete":
                focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
                if focus.get("ok"):
                    # Wait for high-scoring composers (textarea/contenteditable) instead of locking onto a search bar immediately
                    if focus.get("score", 0) >= 100000 or (time.monotonic() > deadline_ready - 10.0):
                        break
                    else:
                        focus = {} # Reset to keep polling
            time.sleep(1.5)
        row["readyState"] = c.evaluate("document.readyState")
        if not focus.get("ok"):
            row.update(status="NO_COMPOSER", detail=(focus or {}).get("error") or "page never ready",
                       waitedSeconds=round(ready_wait, 1))
            return row
        row["composer"] = {k: focus.get(k) for k in ("tag", "editable", "candidates")}

        # Network on only now: everything before this is page inspection, and enabling earlier just
        # buries the one request we care about under page-load traffic.
        c.call("Network.enable")

        c.call("Input.insertText", {"text": SENTINEL})
        back = c.evaluate(JS_READ_ACTIVE) or {}
        landed = SENTINEL.split(":")[0] in (back.get("text") or "")

        if not landed and focus.get("x") is not None:
            # Some editors only wire their input handlers after a real pointer event lands on them
            # (focus() alone is not enough). Click the composer's centre, then try the text again.
            for kind in ("mousePressed", "mouseReleased"):
                c.call("Input.dispatchMouseEvent",
                       {"type": kind, "x": focus["x"], "y": focus["y"],
                        "button": "left", "clickCount": 1})
            time.sleep(0.4)
            c.call("Input.insertText", {"text": SENTINEL})
            back = c.evaluate(JS_READ_ACTIVE) or {}
            landed = SENTINEL.split(":")[0] in (back.get("text") or "")
            row["neededClick"] = bool(landed)

        if not landed:
            # Last resort: real per-character key events. Slower and noisier than insertText, but a
            # few editors only commit text that arrives through the keyboard pipeline.
            c.evaluate("(() => { const a=document.activeElement; if(a){ if('value' in a) a.value=''; "
                       "else a.textContent=''; } })()")
            for ch in SENTINEL:
                c.call("Input.dispatchKeyEvent", {"type": "char", "text": ch}, timeout=8)
            back = c.evaluate(JS_READ_ACTIVE) or {}
            landed = SENTINEL.split(":")[0] in (back.get("text") or "")
            row["neededCharTyping"] = bool(landed)

        if not landed:
            # 4th strategy: direct composer element targeting. Everything above delivered the
            # sentinel through the browser's input pipeline and the editor refused it; this path
            # rewrites the element's own content and fires the DOM events the framework listens
            # for (see JS_FORCE_TEXT). Verified afterwards exactly like the other strategies, by
            # re-reading the focused element -- JS_READ_ACTIVE, not the snippet's own readback.
            try:
                c.evaluate(JS_FORCE_TEXT.replace("__SENTINEL_JSON__", json.dumps(SENTINEL)))
                back = c.evaluate(JS_READ_ACTIVE) or {}
                landed = SENTINEL.split(":")[0] in (back.get("text") or "")
            except CDPError as e:
                back = {"error": f"eval: {str(e)[:100]}"}
                landed = False
            row["neededJsForce"] = bool(landed)
            if not landed and isinstance(back, dict) and back.get("error"):
                row["jsForceDetail"] = str(back.get("error"))[:100]

        row["textLanded"] = bool(landed)
        if not landed:
            # The exact failure launch_and_harvest_chats.py reports as success.
            row.update(status="TEXT_REJECTED",
                       note="composer did not accept Input.insertText -- nothing was submitted")
            return row

        # ---- submit ---------------------------------------------------------------------------
        # One Enter is not enough, and `textLanded` above does not prove the app agrees: it reads the
        # DOM, while a model-backed editor (ProseMirror/Lexical -- Claude, Gemini, Perplexity) keeps
        # its own document. Measured 2026-08-26: ten sites reported textLanded=True and emitted ZERO
        # posts, because Enter hit a "composer is empty" guard. The old char-typing fallback could
        # never help, since it only ran when textLanded was False.
        #
        # So each submit method is tried and then VERIFIED against the network, cheapest first, and
        # the winner is recorded. A site is only declared un-capturable after all four fail.
        seen = {"requests": 0, "posts": 0, "wsFrames": 0}
        handled: set[str] = set()
        ws_hit: dict[str, Any] = {}
        ws_caps: dict[str, dict] = {}   # requestId -> buffered websocket exchange (Chrome-gap)
        http_hits: list[dict] = []      # ordered sentinel-bearing POSTs (multi-step flows)

        def save_ws(rid: str) -> dict[str, Any] | None:
            """Save a WEBSOCKET capture: handshake url + Chrome's headers + every frame, in
            order. Chrome-gap doctrine -- the sentinel left over a websocket, so the seat's
            transport IS a websocket and the exchange is re-sendable over one (ws_replay.py).
            Same filename contract as the HTTP path, plus a transport marker."""
            cap = ws_caps.get(rid) or {}
            ws_url = cap.get("url") or ""
            if not ws_url or not cap.get("sent"):
                return None
            jar = c.call("Network.getCookies",
                         {"urls": ["https://" + host_of(ws_url), t.get("url", "")]}
                         ).get("cookies", [])
            cookie_header = "; ".join(f"{k['name']}={k['value']}" for k in jar)
            skip = ("host", "upgrade", "connection", "content-length", "sec-websocket-key",
                    "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol")
            rh = {k: v for k, v in (cap.get("headers") or {}).items()
                  if not k.startswith(":") and k.lower() not in skip}
            payload = {
                "host": host_of(ws_url), "modality": "chat", "site": name,
                "sentinel": SENTINEL, "transport": "websocket",
                "updated_at": int(time.time()), "cookie_header": cookie_header,
                "recorded_ws": {"url": ws_url, "request_headers": rh,
                                "sent_frames": cap.get("sent") or [],
                                "received_frames": cap.get("recv") or [],
                                "timeoutS": 45.0, "quietS": 6.0},
                "status": {"alive": not pending,
                           "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "reason": "capture_sessions_cdp_ws"},
            }
            out = output_dir / validated_session_filename(output_name, name)
            atomic_json_write(out, payload)
            return {"status": "CAPTURED_WS", "endpointHost": host_of(ws_url),
                    "endpointPath": urllib.parse.urlsplit(ws_url).path[:80],
                    "sentFrames": len(cap.get("sent") or []),
                    "receivedFrames": len(cap.get("recv") or []),
                    "file": str(out.relative_to(ROOT))}

        def scan() -> dict[str, Any] | None:
            """Drain buffered events once. requestIds are remembered so a request is never counted
            or re-fetched twice across strategies."""
            for ev in list(c.events):
                m = ev.get("method")
                p = ev.get("params") or {}
                wrid = str(p.get("requestId") or "")
                if m == "Network.webSocketCreated":
                    if wrid and wrid not in ws_caps:
                        ws_caps[wrid] = {"url": p.get("url") or "", "sent": [],
                                         "recv": [], "headers": {}}
                    continue
                if m == "Network.webSocketWillSendHandshakeRequest":
                    if wrid in ws_caps:
                        ws_caps[wrid]["headers"] = (p.get("request") or {}).get("headers") or {}
                    continue
                if m in ("Network.webSocketFrameSent", "Network.webSocketFrameReceived"):
                    cap = ws_caps.get(wrid)
                    pl = str((p.get("response") or {}).get("payloadData") or "")
                    if not cap or not pl:
                        continue
                    if len(pl) > 32768:
                        pl = pl[:32768]
                    sent = m.endswith("Sent")
                    bucket = cap["sent"] if sent else cap["recv"]
                    if len(bucket) < (200 if sent else 400):
                        bucket.append(pl)
                    if sent:
                        seen["wsFrames"] += 1
                        if has_sentinel(pl) and not ws_hit:
                            ws_hit.update(frameBytes=len(pl), rid=wrid)
                    continue
                if m != "Network.requestWillBeSent":
                    continue
                rid = str(p.get("requestId") or "")
                if not rid or rid in handled:
                    continue
                handled.add(rid)
                seen["requests"] += 1
                req = p.get("request") or {}
                url = req.get("url") or ""
                if req.get("method") not in ("POST", "PUT", "PATCH"):
                    continue
                if any(n in url.lower() for n in NOISE):
                    continue
                seen["posts"] += 1
                body = req.get("postData") or ""
                if not body and req.get("hasPostData"):
                    try:
                        body = (c.call("Network.getRequestPostData", {"requestId": rid},
                                       timeout=10).get("postData") or "")
                    except CDPError:
                        body = ""
                if has_sentinel(body):
                    # Multi-step flows: KEEP buffering instead of returning on the first hit.
                    # Measured (Giz #1194, chatgpt free-web): the first sentinel POST can be a
                    # planner/prepare leg while the answer-producing exchange comes second.
                    # The caller saves once, after the watch window, with the full sequence.
                    http_hits.append({"url": url, "method": req.get("method"),
                                      "request_headers": dict(req.get("headers") or {}),
                                      "request_body": body,
                                      "host": host_of(url)})
            return None

        def watch(seconds: float) -> dict[str, Any] | None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                c.pump(0.8)
                hit = scan()
                if hit:
                    return hit
            return scan()

        def _key(key: str, code: str, vk: int, modifiers: int = 0, text: str | None = None) -> None:
            base = {"key": key, "code": code, "windowsVirtualKeyCode": vk,
                    "nativeVirtualKeyCode": vk, "modifiers": modifiers}
            down = dict(base, type="keyDown")
            if text is not None:
                down["text"] = text
                down["unmodifiedText"] = text
            c.call("Input.dispatchKeyEvent", down, timeout=8)
            c.call("Input.dispatchKeyEvent", dict(base, type="keyUp"), timeout=8)

        def press_enter() -> None:
            # `keyDown` WITH text, not `rawKeyDown`: rawKeyDown suppresses the keypress event, and a
            # composer listening on keypress never sees the submit.
            _key("Enter", "Enter", 13, text="\r")

        def strat_enter() -> None:
            press_enter()

        def strat_js_click() -> None:
            r = c.evaluate(JS_SEND.replace("__CLICK__", "true")) or {}
            row["sendControl"] = {k: r.get(k) for k in ("ok", "label", "score", "disabledMatches")}
            if not r.get("ok"):
                raise CDPError(f"send control: {r.get('error') or 'not found'}")

        def strat_mouse_send() -> None:
            r = c.evaluate(JS_SEND.replace("__CLICK__", "false")) or {}
            if not r.get("ok") or r.get("x") is None:
                raise CDPError(f"send control: {r.get('error') or 'not found'}")
            # A trusted pointer event, for apps that check event.isTrusted before acting.
            for kind, clicks in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 1)):
                c.call("Input.dispatchMouseEvent", {"type": kind, "x": r["x"], "y": r["y"],
                                                    "button": "left", "clickCount": clicks})

        def strat_retype() -> None:
            # Re-focus and use Input.insertText directly into the target WebContents without dispatching raw OS keys
            f2 = c.evaluate(JS_FOCUS_COMPOSER) or {}
            if not f2.get("ok"):
                raise CDPError("composer vanished before retype")
            time.sleep(0.2)
            c.call("Input.insertText", {"text": SENTINEL})
            back2 = c.evaluate(JS_READ_ACTIVE) or {}
            row["retypeLanded"] = SENTINEL.split(":")[0] in (back2.get("text") or "")
            time.sleep(0.3)
            press_enter()

        def strat_paste() -> None:
            # Clipboard paste path (gemini + editors that refused every delivery pipeline above):
            # the seat Chrome runs in the interactive session and shares the user clipboard, so
            # the sentinel is placed there, the composer is clicked for focus, and a real Ctrl+V
            # is dispatched through the browser input pipeline. The user's previous clipboard
            # text is saved and restored afterwards.
            import subprocess
            prev = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=15).stdout
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Set-Clipboard -Value " + json.dumps(SENTINEL)],
                capture_output=True, text=True, timeout=15)
            try:
                f3 = c.evaluate(JS_FOCUS_COMPOSER) or {}
                if not f3.get("ok") or f3.get("x") is None:
                    raise CDPError("composer vanished before paste")
                for kind in ("mousePressed", "mouseReleased"):
                    c.call("Input.dispatchMouseEvent",
                           {"type": kind, "x": f3["x"], "y": f3["y"],
                            "button": "left", "clickCount": 1})
                time.sleep(0.4)
                _key("v", "KeyV", 86, modifiers=2)          # Ctrl+V
                time.sleep(0.4)
                back3 = c.evaluate(JS_READ_ACTIVE) or {}
                row["pasteLanded"] = SENTINEL.split(":")[0] in (back3.get("text") or "")
                time.sleep(0.3)
                press_enter()
            finally:
                if prev.strip():
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Set-Clipboard -Value " + json.dumps(prev.rstrip("\r\n"))],
                        capture_output=True, text=True, timeout=15)


        per = max(6.0, wait / 4.0)
        row["strategiesTried"] = []

        def save_http_buffer(label: str) -> dict[str, Any]:
            """Save ONCE from the ordered buffer. Runs as soon as a strategy's window
            produced sentinel-bearing POSTs, so later strategies never fire (no extra
            submits). The full window is waited out first so follow-on exchanges of a
            multi-step flow (prepare -> conversation, planner -> message) land in the
            buffer next to the first hit."""
            jar = c.call("Network.getCookies",
                         {"urls": [http_hits[0]["url"], t.get("url", "")]}).get("cookies", [])
            cookie_header = "; ".join(f"{k['name']}={k['value']}" for k in jar)
            payload = capture_payload(hits=http_hits, cookie_header=cookie_header,
                                      site=name, pending=pending)
            out = output_dir / validated_session_filename(output_name, name)
            atomic_json_write(out, payload)
            row["submitStrategy"] = label
            row.update({"status": "CAPTURED", "endpointHost": http_hits[0]["host"],
                        "endpointPath": urllib.parse.urlsplit(http_hits[0]["url"]).path[:80],
                        "bodyBytes": len(http_hits[0].get("request_body") or ""),
                        "headerCount": len(http_hits[0].get("request_headers") or {}),
                        "exchangeCount": len(http_hits),
                        "file": str(out.relative_to(ROOT))})
            return row

        for label, fn in (("enter", strat_enter), ("js_click_send", strat_js_click),
                          ("mouse_send", strat_mouse_send), ("retype_keys", strat_retype),
                          ("paste_clipboard", strat_paste)):
            try:
                fn()
            except CDPError as e:
                row.setdefault("strategySkipped", {})[label] = str(e)[:90]
                continue
            row["strategiesTried"].append(label)
            watch(per)
            if ws_hit:
                # The sentinel went out over a websocket: that is the seat's transport, and
                # per the Chrome-gap doctrine it is a BUILD TARGET, not a dead end. A
                # buffered ws exchange is saved as a first-class ws-transport capture
                # (replayable by ws_replay.py); only a buffer that somehow failed to record
                # falls back to the honest not-replayable-as-HTTP verdict.
                saved = save_ws(str(ws_hit.get("rid") or ""))
                if saved:
                    row["submitStrategy"] = label
                    row.update(saved)
                    row["note"] = ("sentinel left over a websocket frame -- captured as a "
                                   "ws-transport session (transport: websocket)")
                    return row
                row.update(status="WEBSOCKET", frameBytes=ws_hit.get("frameBytes"),
                           note="sentinel left over a websocket frame but no ws exchange was "
                                "buffered -- not captured")
                return row
            if http_hits:
                return save_http_buffer(label)

        row.update(requestsSeen=seen["requests"], postsSeen=seen["posts"],
                   wsFramesSeen=seen["wsFrames"])
        if ws_hit:
            # The sentinel went out over a websocket: that is the seat's transport, and per
            # the Chrome-gap doctrine it is a BUILD TARGET, not a dead end. A buffered ws
            # exchange is saved as a first-class ws-transport capture (replayable by
            # ws_replay.py); only a buffer that somehow failed to record falls back to the
            # honest not-replayable-as-HTTP verdict.
            saved = save_ws(str(ws_hit.get("rid") or ""))
            if saved:
                row.update(saved)
                row["note"] = ("sentinel left over a websocket frame -- captured as a "
                               "ws-transport session (transport: websocket)")
                return row
            row.update(status="WEBSOCKET", frameBytes=ws_hit.get("frameBytes"),
                       note="sentinel left over a websocket frame but no ws exchange was "
                            "buffered -- not captured")
            return row
        row.update(status="NO_REQUEST",
                   note=f"all {len(row['strategiesTried'])} submit strategies failed; "
                        f"{seen['requests']} requests / "
                        f"{seen['posts']} posts / {seen['wsFrames']} ws frames seen")
        return row
    except CDPError as e:
        row.update(status="CDP_ERROR", detail=str(e)[:140])
        return row
    except Exception as e:
        # One bad tab must never end a seat's sweep with sites still queued.
        row.update(status="CDP_ERROR", detail=f"{type(e).__name__}: {str(e)[:120]}")
        return row
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--sites", default="", help="comma-separated site names from the directory")
    ap.add_argument("--all", action="store_true", help="every signed-in site, volatile ones first")
    ap.add_argument("--volatile-first", action="store_true",
                    help="session_only sites first, then signed_in_probable")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--any-seat", action="store_true",
                    help="attempt every seat's sites on this port (default: only the seat that owns "
                         "this port, so no anonymous tab is ever captured)")
    ap.add_argument("--wait", type=float, default=25.0, help="seconds to wait for the request")
    ap.add_argument("--open", action="store_true",
                    help="open a tab for sites that have none (a full sweep needs this)")
    ap.add_argument("--output-dir", type=pathlib.Path, default=SECRETS,
                    help="capture destination (default: active state/secrets); use a staged directory "
                    "until independent replay approves promotion")
    ap.add_argument("--output-name", default="",
                    help="simple session_*.json basename; required for a unique per-tab staged artifact")
    ap.add_argument("--pending", action="store_true",
                    help="write status.alive=false for a quarantined candidate pending independent replay")
    ap.add_argument("--target-id", default="",
                    help="capture exactly this current CDP page target; never collapse tabs by domain")
    ap.add_argument("--expected-pid", type=int, default=0,
                    help="require the stronger manifest attestation to still resolve this listener PID")
    ap.add_argument("--report-path", type=pathlib.Path, default=None,
                    help="non-secret capture report destination (default: state/capture_report_<port>.json)")
    ap.add_argument("--list", action="store_true", help="show the plan and the matching tabs, then stop")
    a = ap.parse_args()

    if a.target_id:
        if not a.sites or len([s for s in a.sites.split(",") if s.strip()]) != 1:
            ap.error("--target-id requires exactly one --sites value")
        if a.open or a.all or a.volatile_first or a.any_seat:
            ap.error("--target-id is existing-tab-only; do not combine it with --open, --all, --volatile-first, or --any-seat")
    if a.output_name:
        try:
            validated_session_filename(a.output_name, "unused")
        except ValueError as exc:
            ap.error(str(exc))
    if a.expected_pid:
        # The outer orchestrator's process/profile proof is repeated immediately
        # before stateful CDP work to close its time-of-check/time-of-use window.
        try:
            from tab_graduation_sweep import assert_automation_seat
            current = assert_automation_seat(a.port)
        except Exception as exc:
            raise SystemExit(f"seat attestation failed before capture: {type(exc).__name__}: {str(exc)[:120]}")
        if current.pid != a.expected_pid:
            raise SystemExit(
                f"seat listener changed before capture (expected PID {a.expected_pid}, found {current.pid}); refusing"
            )

    rows = plan(a)
    if a.limit:
        rows = rows[:a.limit]
    tabs = targets(a.port)
    # Per-port file: a multi-seat sweep is four runs, and one shared path would leave only the last.
    report_path = a.report_path or REPORT.with_name(f"capture_report_{a.port}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"port {a.port}: {len(tabs)} page targets   plan: {len(rows)} sites")
    assert_safe_cdp_port(a.port)
    try:
        output_label = a.output_dir.relative_to(ROOT)
    except ValueError:
        output_label = a.output_dir
    print(f"sentinel: {SENTINEL!r}   capture destination -> {output_label}\n")

    by_dom: dict[str, dict] = {}
    for t in tabs:
        by_dom.setdefault(reg(host_of(t.get("url", ""))), t)
    explicit_target = None
    if a.target_id:
        explicit_target = next((t for t in tabs if str(t.get("id") or "") == a.target_id), None)
        if not explicit_target:
            raise SystemExit(f"target {a.target_id} is no longer present on :{a.port}; nothing was submitted")

    report: dict[str, Any] = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "port": a.port, "sentinel": SENTINEL, "results": []}
    if a.list:
        for name, url, verdict in rows:
            d = reg(host_of(url))
            print(f"  {'TAB' if d in by_dom else '  -':4s} {name:32s} {verdict:20s} {d}")
        return 0

    for name, url, verdict in rows:
        if name in VIDEO_ONLY:
            print(f"  --  {name:32s} video generator, no chat composer -- Task 2's target")
            report["results"].append({"site": name, "status": "VIDEO_PROVIDER_SKIPPED"})
            continue
        override = CHAT_URL_OVERRIDES.get(name)
        if a.target_id and override:
            # Overrides exist because a normal invocation should navigate to a
            # different chat surface.  A strict existing-tab sweep must never
            # let that legacy convenience silently create/navigate a new tab.
            report["results"].append({"site": name, "targetId": a.target_id,
                                      "status": "OVERRIDE_REQUIRES_NAVIGATION"})
            continue
        if override:
            url = override
        if not url:
            print(f"  --  {name:32s} unknown site name (not in the directory)")
            continue
        d = reg(host_of(url))
        # An override exists precisely because the already-open tab is on the wrong page, so it is
        # never reused; every other site prefers the tab that is already signed in and warm.
        t = explicit_target if a.target_id else (None if override else by_dom.get(d))
        if not t and (a.open or override):
            print(f"  ..  {name:32s} opening a tab on {d}")
            t = open_tab(a.port, url)
            if t:
                by_dom[d] = t
                time.sleep(3.0)                      # let the sign-in cookie ride the first load
        if not t:
            hint = "no open tab" if not a.open else "could not open a tab"
            print(f"  --  {name:32s} {hint} on {d}")
            report["results"].append({"site": name, "status": "NO_TAB", "domain": d})
            continue
        row = capture(t, name, verdict, a.wait, output_dir=a.output_dir,
                      output_name=a.output_name or None, pending=a.pending)
        report["results"].append(row)
        mark = {"CAPTURED": "OK ", "WALL": "WALL", "NO_COMPOSER": "    ", "WEBSOCKET": "WS  ",
                "TEXT_REJECTED": "TXT ", "NO_REQUEST": "    "}.get(row["status"], "    ")
        tail = ""
        if row["status"] == "CAPTURED":
            tail = (f"{row['endpointHost']}{row['endpointPath']}  {row['bodyBytes']}B body  "
                    f"via {row.get('submitStrategy')}")
        elif row.get("wall"):
            tail = f"wall: {row['wall']!r}"
        elif row.get("detail"):
            tail = str(row["detail"])[:70]
        elif row.get("note"):
            tail = row["note"][:70]
        print(f"  {mark:4s} {name:32s} {row['status']:14s} {tail}")
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    got = [r["site"] for r in report["results"] if r.get("status") == "CAPTURED"]
    walls = [r["site"] for r in report["results"] if r.get("status") == "WALL"]
    ws = [r["site"] for r in report["results"] if r.get("status") == "WEBSOCKET"]
    report["summary"] = {"captured": got, "walls": walls, "websocketOnly": ws,
                         "byStrategy": {s: [r["site"] for r in report["results"]
                                            if r.get("submitStrategy") == s]
                                        for s in ("enter", "js_click_send", "mouse_send",
                                                  "retype_keys")},
                         "failed": [r["site"] for r in report["results"]
                                    if r.get("status") not in ("CAPTURED", "WALL", "WEBSOCKET")]}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\ncaptured ({len(got)}): {', '.join(got) or 'none'}")
    if ws:
        print(f"websocket({len(ws)}): {', '.join(ws)}  <- not replayable as HTTP")
    if walls:
        print(f"WALLS   ({len(walls)}): {', '.join(walls)}  <- left untouched, operator decision")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
