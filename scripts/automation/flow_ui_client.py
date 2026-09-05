"""flow_ui_client.py - Flow (labs.google) pool client for the MIGRATED flow.google.com SPA.

WHY THIS EXISTS (worklog #1630/#1637): Google migrated labs.google -> flow.google.com. The old
adapter stack (FlowSession.refresh SESSION_JS at /fx/api/auth/session + aisandbox-pa REST with
a Bearer token) is dead: every /api/auth/session shape now returns the SPA shell HTML, and the
frontend now speaks `/_/AiSandboxAngularFrontend/data/batchexecute` with cookies + an `at`
CSRF token minted by Google's own JS. Hand-replaying that is exactly the "playing the provider"
anti-pattern; the correct doctrine (Chrome Gap, TT 3a) is to BE CHROME: drive the provider's
own UI in the live signed-in seat tab and let Google's own JS run its own protocol.

WHAT IT DOES (adapter thesis, proven path #1630):
  1. find the seat's flow.google.com/project/<uuid> tab (raw CDP, cdp.py — NOT the fragile
     selenium attach cycle).
  2. focus the ProseMirror composer, insert the caller's prompt with Input.insertText
     (the only text path model-backed editors accept, TT 3.3), submit with a genuine Enter.
  3. poll the SPA's own DOM for the rendered clip tile, then open the player view and
     capture the CDN URL (flow-content.google/video/<uuid>) from performance entries.
  4. Law-5: credits read from the UI ("N credits" chip) BEFORE the submit; if the quoted
     cost exceeds OMNI_VIDEO_MAX_SPEND or the spend gate is closed, refuse BEFORE typing.

Pool contract: constructed with secret=<seat file path>; chat() returns
{"text": <video url>, "video_url": ..., "label": "chrome-video-flow-ui/<seat>"}.

CLI:
  python flow_ui_client.py doctor                  # tab + composer + credits, no typing
  python flow_ui_client.py gen "<prompt>" --yes    # one gated render (spends credits)
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from veoaifree_chat_client import ChatError          # noqa: E402  (canonical exception)
from veo_session_replay import SessionExpired        # noqa: E402  (subclass of ChatError)
from cdp import Page, list_targets                   # noqa: E402

CREDITS_PER_CLIP_DEFAULT = 15          # observed UI chip: fast 8s clip = 15cr on Pro
# Google queues renders under high demand: the 2026-09-05 seat1 graduation render sat
# ~30 MINUTES in "waiting in the queue" before rendering (~4 min) and completing; the
# consumer job's BOTH attempts then queued out a 45-min budget each without collecting.
# Budget covers a worst-case queue (~80 min) so one submit actually collects its clip.
ANSWER_TIMEOUT_S = 4800
CDP_PORTS = [9222, 9223, 9224, 9225, 9226]


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


# ----------------------------------------------------------------- tab discovery ----
def find_flow_project_tab(prefer_port: Optional[int] = None,
                          exclusive: bool = False) -> Optional[Dict[str, Any]]:
    """Live flow.google.com/project/<uuid> tab across the seat Chromes.

    exclusive: when the seat declares its own cdpPort, ONLY that port may be used.
    Falling through to other ports drove one account's client onto ANOTHER account's
    tab (measured 2026-09-05: the P2 client submitted into seat1's isearch.xsolve tab
    because :9226 was down) — cross-account contamination and a double spend. A
    missing tab on the pinned port is a SessionExpired at the caller, not a reason
    to borrow a sibling seat's tab.
    """
    order = list(CDP_PORTS)
    if prefer_port and prefer_port in order:
        order.remove(prefer_port)
        order.insert(0, prefer_port)
    if exclusive:
        order = [prefer_port] if prefer_port in order else []
    for port in order:
        try:
            for t in list_targets(port):
                if t.get("type") != "page":
                    continue
                url = t.get("url", "") or ""
                if "flow.google.com/project/" in url and re.search(r"/project/[0-9a-f-]{36}", url):
                    t = dict(t)
                    t["port"] = port
                    return t
        except Exception:
            continue                                    # that seat Chrome is down
    return None


# ------------------------------------------------------------------------ JS bits ----
JS_CREDITS = r"""
(() => {
  const m = document.body.innerText.match(/(\d{1,5})\s*credits?/i);
  return m ? parseInt(m[1], 10) : null;
})()
"""

# The agent-mode composer is a ProseMirror contenteditable with placeholder text.
JS_COMPOSER_READY = r"""
(() => {
  const v = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const ce = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(v);
  if (!ce) return {ok: false, why: 'no visible contenteditable composer'};
  return {ok: true, cls: (ce.className || '').toString().slice(0, 60)};
})()
"""

# Detect a completed generation: new clip tiles / "generating" gone. The agent chip stream
# prints progress; the render is done when a video tile or duration badge appears and the
# composer is enabled again. QUEUED is a real Google-side state ("scheduled and waiting in
# the queue due to high demand") — credits are already committed while queued.
JS_RENDER_STATE = r"""
(() => {
  const t = document.body.innerText;
  const queued = /waiting in the queue|has been scheduled/i.test(t);
  const generating = !queued && /generating|rendering|processing/i.test(t);
  const videoTiles = Array.from(document.querySelectorAll('video'))
      .filter(el => { const r = el.getBoundingClientRect(); return r.width > 60 && r.height > 40; }).length;
  return JSON.stringify({generating, queued, videoTiles});
})()
"""

# Player-URL harvest: performance entries carry the CDN URL once the player mounts.
# ALL flow-content video URLs (a snapshot before submit lets chat() accept only URLs
# that appear AFTER our send, so a pre-existing clip can never be the proof).
JS_CDN_URL = r"""
(() => {
  const urls = performance.getEntriesByType('resource').map(e => e.name)
      .filter(n => /flow-content\.google\/video\//.test(n));
  return urls.length ? urls[urls.length - 1] : null;
})()
"""

JS_CDN_ALL = r"""
(() => JSON.stringify(performance.getEntriesByType('resource').map(e => e.name)
    .filter(n => /flow-content\.google\/video\//.test(n))))()
"""

# Click the newest clip tile to open the player (thumbnails live in the grid).
JS_OPEN_NEWEST_TILE = r"""
(() => {
  const vids = Array.from(document.querySelectorAll('video'));
  if (!vids.length) return JSON.stringify({ok: false, why: 'no video tiles in DOM'});
  const v = vids[vids.length - 1];
  v.scrollIntoView({block: 'center'});
  const card = v.closest('[role="button"], button, [tabindex]') || v;
  card.click();
  return JSON.stringify({ok: true, tiles: vids.length});
})()
"""


class FlowUiClient:
    """Pool client: Flow renders through the provider's own UI in the live seat tab."""

    def __init__(self, secret=None, host: Optional[str] = None, **kw):
        self.secret = pathlib.Path(secret) if secret else None
        raw: Dict[str, Any] = {}
        if self.secret and self.secret.exists():
            try:
                raw = json.loads(self.secret.read_text(encoding="utf-8-sig"))
            except Exception:
                raw = {}
        self.host = host or raw.get("host") or "labs.google"
        self.port_hint = ((raw.get("seat") or {}).get("port")
                          or (raw.get("chrome") or {}).get("cdpPort"))
        self.label = f"chrome-video-flow-ui/{self.host}"
        self.max_spend = float(os.environ.get("OMNI_VIDEO_MAX_SPEND", "30"))
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        self._last_tab: Optional[Dict[str, Any]] = None

    # ---- readiness ----------------------------------------------------------------
    def capacity(self) -> Dict[str, Any]:
        tab = find_flow_project_tab(self.port_hint)
        if not tab:
            return {"host": self.host, "creditsRemaining": 0, "clipsRemaining": 0,
                    "error": "NO_PROJECT_TAB - open flow.google.com project in the seat"}
        self._last_tab = tab
        with Page(match="flow.google.com/project/", timeout=30, port=tab["port"]) as pg:
            credits = pg.evaluate(JS_CREDITS, timeout=30)
        credits = int(credits) if credits else 0
        return {"host": self.host, "creditsRemaining": credits,
                "clipsRemaining": credits // CREDITS_PER_CLIP_DEFAULT,
                "creditsPerClip": CREDITS_PER_CLIP_DEFAULT, "tab": tab["url"][:60]}

    # ---- the one path that spends ---------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = str(messages[-1].get("content") or "").strip()
        if len(prompt.split()) < 5:
            raise ChatError("SHORT_PROMPT", "flow video prompts need a real scene "
                                            "description (5+ words)")

        tab = find_flow_project_tab(self.port_hint, exclusive=bool(self.port_hint))
        if not tab:
            raise SessionExpired(
                "NO_PROJECT_TAB",
                f"no flow.google.com/project tab on pinned port :{self.port_hint}"
                if self.port_hint else
                "no flow.google.com/project tab on any seat Chrome - open the project once "
                "in the seat profile (operator step) or restore the seat Chrome")
        port = tab["port"]

        with Page(match="flow.google.com/project/", timeout=60, port=port) as pg:
            # 1) credits gate BEFORE typing anything (Law 5)
            credits = pg.evaluate(JS_CREDITS, timeout=30)
            credits = int(credits) if credits else None
            if credits is not None and credits < CREDITS_PER_CLIP_DEFAULT:
                raise ChatError("wall", f"flow credits {credits} < {CREDITS_PER_CLIP_DEFAULT} "
                                        f"per clip: seat is dry")
            if not self.confirm_spend:
                raise ChatError(
                    "wall", f"spend gate closed: flow clip costs ~{CREDITS_PER_CLIP_DEFAULT} "
                            f"credits (balance {credits}); set OMNI_VIDEO_CONFIRM_SPEND=1 "
                            f"to allow this seat to charge")
            if self.max_spend < CREDITS_PER_CLIP_DEFAULT:
                raise ChatError("wall", f"OMNI_VIDEO_MAX_SPEND={self.max_spend:g} below "
                                        f"the ~{CREDITS_PER_CLIP_DEFAULT}cr clip price")

            # 2) insert prompt + submit (the proven #1630 sequence)
            ready = pg.evaluate(JS_COMPOSER_READY, timeout=60)
            if not (isinstance(ready, dict) and ready.get("ok")):
                raise ChatError("NO_INPUT",
                                (ready or {}).get("why", "composer not ready")
                                if isinstance(ready, dict) else "composer check failed")
            focus_js = (
                "(() => { const v = el => { const r = el.getBoundingClientRect();"
                " return r.width > 0 && r.height > 0; };"
                " const ce = Array.from(document.querySelectorAll('[contenteditable=\"true\"]'))"
                "   .find(v); if (!ce) return 'NO_CE'; ce.focus(); return 'FOCUSED'; })()"
            )
            state = pg.evaluate(focus_js, timeout=30)
            if state != "FOCUSED":
                raise ChatError("NO_INPUT", "composer focus failed")
            pg.send("Input.insertText", {"text": prompt}, timeout=30)
            ok = pg.evaluate(
                "(() => { const sel = window.getSelection();"
                " return sel && sel.anchorNode !== null ? 'SEATED' : 'NO_SEL'; })()",
                timeout=30)
            if ok != "SEATED":
                raise ChatError("NO_INPUT", "insertText did not seat in the composer")

            for etype, down in (("keyDown", True), ("keyUp", False)):
                pg.send("Input.dispatchKeyEvent", {
                    "type": etype, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                    "text": "\r" if down else "", "unmodifiedText": "\r" if down else "",
                }, timeout=30)
            t0 = time.time()

            # 3) poll the render to completion in the SPA's own DOM
            baseline = set(json.loads(pg.evaluate(JS_CDN_ALL, timeout=30) or "[]"))
            result_url = None
            tiles_seen = 0
            last_sig = ""
            deadline = time.time() + ANSWER_TIMEOUT_S
            opened_player = False
            while time.time() < deadline:
                time.sleep(6)
                st = json.loads(pg.evaluate(JS_RENDER_STATE, timeout=60) or "{}")
                tiles_seen = max(tiles_seen, st.get("videoTiles", 0))
                sig = f"queued={st.get('queued')} generating={st.get('generating')} tiles={tiles_seen}"
                if sig != last_sig:
                    print(f"[flow-ui] {int(time.time() - t0)}s {sig}")
                    last_sig = sig
                if tiles_seen and not opened_player:
                    opened = json.loads(pg.evaluate(JS_OPEN_NEWEST_TILE, timeout=60) or "{}")
                    opened_player = bool(opened.get("ok"))
                if opened_player:
                    fresh = [u for u in json.loads(pg.evaluate(JS_CDN_ALL, timeout=30) or "[]")
                             if u not in baseline]
                    if fresh:
                        result_url = fresh[-1]
                        break

            if not result_url:
                # wall-class, NOT a per-seat transient: the prompt was already submitted
                # and credits are committed. A retry by the caller's failover would be a
                # SECOND charge for the same job (measured 2026-09-05). The pool's video
                # worker treats wall as job-terminal (Law 5 / flow_api_client precedent).
                raise ChatError(
                    "wall", f"flow render submitted but not collected in "
                            f"{ANSWER_TIMEOUT_S}s (tiles={tiles_seen}, player={opened_player}); "
                            f"credits charged - the clip stays recoverable in the project tab; "
                            f"do NOT retry blind")

        # In-run HEAD proof: the CDN signature is short-lived, so verify INSIDE the same
        # call (a proof collected by a later script can arrive after expiry and read 403
        # on a perfectly good URL — measured 2026-09-05 seat1 graduation).
        url_proof = {"http": None}
        try:
            import urllib.error as _ue
            import urllib.request as _ur
            _req = _ur.Request(result_url, method="HEAD")
            with _ur.urlopen(_req, timeout=30) as _r:
                url_proof = {"http": _r.status,
                             "contentType": _r.headers.get("Content-Type"),
                             "bytes": _r.headers.get("Content-Length")}
        except Exception as _e:
            url_proof = {"http": None, "error": str(_e)[:120]}

        return {"text": result_url, "video_url": result_url, "label": self.label,
                "modality": "video", "credits_before": credits,
                "url_proof": url_proof,
                "duration_s": int(time.time() - t0), "tab": tab["url"][:60]}


# ---------------------------------------------------------------------- CLI ----
def _cmd_doctor() -> int:
    tab = find_flow_project_tab()
    if not tab:
        print("NO_TAB: no flow.google.com/project tab on ports", CDP_PORTS)
        return 1
    print(f"tab on :{tab['port']}  {tab['url'][:80]}")
    with Page(match="flow.google.com/project/", timeout=30, port=tab["port"]) as pg:
        credits = pg.evaluate(JS_CREDITS, timeout=30)
        ready = pg.evaluate(JS_COMPOSER_READY, timeout=30)
    print("credits chip:", credits)
    print("composer:", ready)
    return 0 if (ready or {}).get("ok") else 1


def _cmd_gen(prompt: str, yes: bool, port: Optional[int]) -> int:
    if not yes:
        print("refusing to generate without --yes (this spends Flow credits)")
        return 2
    c = FlowUiClient()
    c.port_hint = port
    t0 = time.time()
    try:
        r = c.chat([{"role": "user", "content": prompt}])
    except (ChatError, SessionExpired) as e:
        print(f"ERR {e}")
        return 1
    print(f"OK {int(time.time() - t0)}s label={r['label']}")
    print(f"video_url={r.get('video_url')}")
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p_gen = sub.add_parser("gen")
    p_gen.add_argument("prompt")
    p_gen.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "doctor":
        return _cmd_doctor()
    return _cmd_gen(a.prompt, a.yes, a.port)


if __name__ == "__main__":
    raise SystemExit(main())
