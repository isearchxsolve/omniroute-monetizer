# -*- coding: utf-8 -*-
"""chrome_video_client.py — Chrome-doctrine video pool client (THE business bridge for video).

THE DOCTRINE (TECHNOLOGY_TRANSFER.md §19, AGENTS.md Chrome Gap Doctrine):
  Chrome knows nothing provider-specific. The per-provider adaptation is the provider's
  OWN JavaScript, shipped on every page load. So we never reconstruct a request from
  Python (no custom HTTP bridges, no replayed stale bytes): we drive the site's own UI
  inside the LIVE signed-in tab — type the prompt into the site's own input, press the
  site's own generate button, and watch the site's own DOM for the finished video URL.
  Fresh CSRF / nonce / bearer / PoW come free, correct-by-construction.

  A login wall in automation's own profile is a CORRECT, reportable outcome (Law 5:
  report the wall, never solve it). Rate limits and paywalls are reported, never retried.

WHAT THIS SERVES (14 hosts, all via the live tab):

  Dedicated video hosts (tabs found in the seat Chromes, worklog #1106):
    labs.google      Google Flow / Veo 3.1   — delegates to the PROVEN FlowSession adapter
    veoaifree.com    VEO 3.1 free            — delegates to the PROVEN VeoFreeSession adapter
    akool.com        image-to-video 4K       — generic UI driver
    magichour.ai     Magic Hour              — generic UI driver
    www.giz.ai       GizAI                   — generic UI driver
    www.creen.ai     Creen                   — generic UI driver
    app.heygen.com   HeyGen avatars          — generic UI driver
    digen.ai         Digen                   — generic UI driver
    www.nemovideo.com Nemo                   — generic UI driver

  Dual-modal CHAT hosts (already REPLAY_OK / Chrome-bridged for chat; their web UIs also
  generate video — same signed-in session, zero extra sign-in cost):
    grok.com         Grok Imagine video
    gemini.google.com Veo (via Gemini UI)
    chat.qwen.ai     Wan (Qwen Studio)
    www.meta.ai      Imagine video
    chatglm.cn       CogVideoX

  rtst.ai is deliberately NOT here: it is served by RtstApiClient (api.kind=rtst), a
  documented quote/create/poll API contract — proven, and cheaper than UI driving.

POOL CONTRACT (same as ChromeReplayClient, see session_pool._client_for):
    __init__(secret=<path>)          # secret unused; the live Chrome IS the credential
    chat(messages, model, **kw)      # -> {"text": ..., "label": ..., "video_url": ...}
    raises ChatError / SessionExpired so the pool's cooldown + failover logic applies.

  The result's "text" carries the video URL (so the OpenAI-shaped shim passes it
  through unchanged) and "video_url" carries it explicitly for video-aware faces.

MULTI-PORT: the four seat Chromes live on CDP ports 9222 (providers), 9223 (niloy),
9224 (seat2), 9225 (seat3). A host may have a tab on several ports (several accounts =
several allowances). The client scans all ports for the host's tab and uses the first
live one; a per-host port hint in the seat file's "chrome_port" field pins one account.

TRANSPORT: raw CDP over websocket (cdp.py), NOT Selenium and NOT Playwright. Selenium's
debuggerAddress attach is a single global driver (chrome_replay_client's _DRIVER_LOCK);
Playwright's connect_over_cdp attaches to EVERY target and has wedged twice on heavy
pages (cdp.py docstring). Raw CDP attaches to ONE page target, never wedges, never kills
anything, and works per-port.

CLI (self-test, zero cost unless --yes):
    python chrome_video_client.py tabs                       # which hosts have live tabs where
    python chrome_video_client.py doctor <host>              # prove tab + input, no generation
    python chrome_video_client.py gen <host> "<prompt>" [--port N] [--yes]
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Raise the SAME exception classes the pool catches (session_pool.py imports ChatError
# from veoaifree_chat_client and SessionExpired from veo_session_replay). Local lookalikes
# would slip past the pool's except-clauses and crash the shim instead of failing over.
from veoaifree_chat_client import ChatError          # noqa: E402
from veo_session_replay import SessionExpired        # noqa: E402
from cdp import Page, list_targets                   # noqa: E402

# The four automation seat Chromes. NEVER the operator's personal profile (rule 0).
CDP_PORTS = [9222, 9223, 9224, 9225]

# Video generation is slow (renders take 40s–5min). Poll budget per call.
VIDEO_TIMEOUT_S = 420
POLL_EVERY_MS = 2500

# ------------------------------------------------------------------ registry ----
# host (as recorded in state/secrets/session_*.json) -> how to drive its live tab.
#   tab      : URL substring that identifies the host's tab
#   kind     : "adapter"  — delegate to a PROVEN protocol adapter (FlowSession / VeoFreeSession)
#              "ui"       — generic UI driver: type prompt, press the site's own generate,
#                           watch the DOM for a video URL
#   port     : optional pin to one seat Chrome (multi-account hosts)
#   gen      : optional extra generate-button regex for the UI driver
VIDEO_HOSTS: Dict[str, Dict[str, Any]] = {
    # ---- dedicated video hosts ----
    # labs.google MIGRATED to flow.google.com (measured 2026-09-05): every
    # /api/auth/session shape returns the SPA shell, the frontend speaks
    # /_/AiSandboxAngularFrontend/data/batchexecute with cookies — the old
    # FlowSession REST+bearer stack is dead. The "flow-ui" adapter drives the
    # provider's OWN UI in the live signed-in project tab (proven seat1 path).
    "labs.google":       {"tab": "flow.google.com/project", "kind": "adapter", "adapter": "flow-ui"},
    "veoaifree.com":     {"tab": "veoaifree.com", "kind": "adapter", "adapter": "veofree"},
    "akool.com":         {"tab": "akool.com", "kind": "ui"},
    "magichour.ai":      {"tab": "magichour.ai", "kind": "ui"},
    "www.giz.ai":        {"tab": "giz.ai", "kind": "ui"},
    "www.creen.ai":      {"tab": "creen.ai", "kind": "ui"},
    "app.heygen.com":    {"tab": "heygen.com", "kind": "ui"},
    "digen.ai":          {"tab": "digen.ai", "kind": "ui"},
    "www.nemovideo.com": {"tab": "nemovideo.com", "kind": "ui"},
    # ---- dual-modal chat hosts (video through the same signed-in session) ----
    "grok.com":          {"tab": "grok.com", "kind": "ui",
                          "gen": r"imagine|video|generate|create"},
    "gemini.google.com": {"tab": "gemini.google.com", "kind": "ui",
                          "gen": r"video|veo|generate"},
    "chat.qwen.ai":      {"tab": "chat.qwen.ai", "kind": "ui",
                          "gen": r"video|wan|generate|create"},
    "www.meta.ai":       {"tab": "meta.ai", "kind": "ui",
                          "gen": r"imagine|video|generate|create"},
    "chatglm.cn":        {"tab": "chatglm.cn", "kind": "ui",
                          "gen": r"video|cogvideo|生成视频|生成"},
}

# --------------------------------------------------------------------- JS bits ----
_VISIBLE_GUARD = r"""
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  function isTrap(el){
    const s = ((el.id||'')+' '+(el.className||'')+' '+(el.name||'')).toLowerCase();
    return s.includes('recaptcha') || s.includes('hpcomp');
  }
"""

# Type the prompt into the site's own visible input (textarea first, then contenteditable).
# cdp.py's Page.evaluate takes ONE expression string (no arguments[]), so the prompt is
# inlined as a JSON literal at call time via __PROMPT_JSON__.
INJECT_JS = r"""
(function(){
  const prompt = __PROMPT_JSON__;
%s
  let ta = Array.from(document.querySelectorAll('textarea'))
             .find(el=>visible(el) && !isTrap(el));
  if(ta){
    ta.focus();
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(ta, prompt);
    ta.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'textarea', len:(ta.value||'').length};
  }
  let ce = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]'))
             .find(el=>visible(el));
  if(ce){
    ce.focus();
    // REPLACE, never append. A leftover prompt from a previous run sitting in the
    // composer would otherwise get duplicated in front of the new one (worklog #1123:
    // gemini contenteditable appended "a red ball..." to the stale sweep prompt).
    // Select-all first so insertText overwrites the existing content.
    try{
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(ce);
      sel.removeAllRanges();
      sel.addRange(range);
    }catch(e){}
    let inserted=false;
    try{ inserted=document.execCommand('insertText', false, prompt); }catch(e){}
    if(!inserted){ ce.textContent = prompt; }
    ce.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'contenteditable', len:(ce.innerText||'').length};
  }
  return {ok:false, why:'no visible textarea or contenteditable found'};
})()
""" % _VISIBLE_GUARD

# Press the site's OWN generate/send button. Tries, in order: submit-type buttons,
# buttons whose label matches the host's gen regex, aria-label send/generate, then the
# enabled button nearest the input. Never touches cookie-consent buttons.
# genRe is inlined as a JSON literal at call time via __GENRE_JSON__.
CLICK_GEN_JS = r"""
(function(){
  const genRe = __GENRE_JSON__;
%s
  const re = new RegExp(genRe, 'i');
  const cands = Array.from(document.querySelectorAll('button,[role="button"]'))
    .filter(el=>visible(el) && !el.disabled
      && !/cky-|cookie|consent|accept all/i.test((el.className||'')+' '+(el.getAttribute('aria-label')||'')+' '+(el.innerText||'')));
  if(!cands.length) return {ok:false, why:'no enabled button'};
  const label = el => ((el.getAttribute('aria-label')||'')+' '+(el.getAttribute('data-testid')||'')+' '+(el.innerText||'')).slice(0,120);
  let pick = cands.find(el=>el.getAttribute('type')==='submit' && re.test(label(el)))
          || cands.find(el=>re.test(label(el)))
          || cands.find(el=>/^(send|submit|generate|create)$/i.test((el.getAttribute('aria-label')||'').trim()))
          || null;
  if(!pick){
    const input = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'))
                    .find(e=>visible(e) && !isTrap(e));
    if(input){
      const ir = input.getBoundingClientRect();
      const cx = ir.x+ir.width/2, cy = ir.y+ir.height/2;
      pick = cands.map(el=>{
        const r = el.getBoundingClientRect();
        return {el, d: Math.hypot(r.x+r.width/2-cx, r.y+r.height/2-cy)};
      }).sort((a,b)=>a.d-b.d)[0].el;
    }
  }
  if(!pick) pick = cands[cands.length-1];
  pick.click();
  return {ok:true, picked:label(pick).replace(/\s+/g,' ').slice(0,60)};
})()
""" % _VISIBLE_GUARD

# Watch the site's own DOM for the finished video. Returns the first video URL that was
# NOT present before the submit (attribute-marked by SNAP_VIDEO_JS). Sources, in order:
# <video src>, <video><source src>, <a href=*.mp4|*.webm|*.mov>, any element with a
# data-attribute holding a video URL.
# runid is inlined as a JSON literal at call time via __RUNID_JSON__.
SNAP_VIDEO_JS = r"""
(function(){
  const runid = __RUNID_JSON__;
  let n = 0;
  const mark = el => { el.setAttribute('data-cvc-seen', runid); n++; };
  document.querySelectorAll('video').forEach(mark);
  document.querySelectorAll('a[href]').forEach(el=>{
    if(/\.(mp4|webm|mov|m4v)(\?|$)/i.test(el.getAttribute('href')||'')) mark(el);
  });
  return n;
})()
"""

# Wrapped in a Promise so cdp.py's awaitPromise=True holds until the video appears or
# the budget expires. runid inlined via __RUNID_JSON__; TIMEOUT_MS/POLL_MS substituted.
POLL_VIDEO_JS = r"""
new Promise((resolve)=>{
  const runid = __RUNID_JSON__;
  const t0 = Date.now();
  const timer = setInterval(()=>{
    // 1. <video> elements added after the snapshot
    let hit = null;
    document.querySelectorAll('video').forEach(v=>{
      if(hit) return;
      if(v.getAttribute('data-cvc-seen') === runid) return;
      const src = v.currentSrc || v.getAttribute('src') || '';
      if(src){ hit = src; return; }
      const s = v.querySelector('source[src]');
      if(s && s.getAttribute('src')) hit = s.getAttribute('src');
    });
    // 2. download links added after the snapshot
    if(!hit){
      document.querySelectorAll('a[href]').forEach(a=>{
        if(hit) return;
        if(a.getAttribute('data-cvc-seen') === runid) return;
        const h = a.getAttribute('href')||'';
        if(/\.(mp4|webm|mov|m4v)(\?|$)/i.test(h)) hit = h;
      });
    }
    // 3. blob: URLs in new <video> (some UIs play via MediaSource) — report, not downloadable
    if(!hit){
      document.querySelectorAll('video').forEach(v=>{
        if(hit) return;
        if(v.getAttribute('data-cvc-seen') === runid) return;
        const src = v.currentSrc || v.getAttribute('src') || '';
        if(src.startsWith('blob:')) hit = src;
      });
    }
    if(hit){ clearInterval(timer); resolve({found:true, ms:Date.now()-t0, url:hit}); return; }
    if(Date.now()-t0 > TIMEOUT_MS){ clearInterval(timer); resolve({found:false, ms:Date.now()-t0}); }
  }, POLL_MS);
})
"""


def _flatten_prompt(messages: List[Dict[str, Any]]) -> str:
    """Video UIs take ONE text box. Use the last user message; prepend a system prompt
    compactly if present (same contract as ChromeReplayClient)."""
    sys_txt = " ".join(m.get("content", "") for m in messages if m.get("role") == "system").strip()
    user_txts = [m.get("content", "") for m in messages if m.get("role") == "user"]
    last = user_txts[-1].strip() if user_txts else ""
    if not last:
        raise ChatError("NO_MESSAGES", "no user message to send")
    if sys_txt:
        return f"[Instructions: {sys_txt[:400]}]\n{last}"
    return last


# ------------------------------------------------------------- tab discovery ----
def find_tab(substr: str, ports: Optional[List[int]] = None,
             prefer_port: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Scan the seat Chromes for a live page tab whose URL matches `substr`.
    Returns the CDP target dict (with 'port' added) or None."""
    order = list(ports or CDP_PORTS)
    if prefer_port and prefer_port in order:
        order.remove(prefer_port)
        order.insert(0, prefer_port)
    for port in order:
        try:
            for t in list_targets(port):
                if t.get("type") != "page":
                    continue
                if substr.lower() in (t.get("url", "") or "").lower():
                    t = dict(t)
                    t["port"] = port
                    return t
        except Exception:
            continue                                        # that seat Chrome is down
    return None


def all_video_tabs() -> List[Dict[str, Any]]:
    """Every live tab across all seat Chromes that belongs to a registered video host."""
    out = []
    for host, spec in VIDEO_HOSTS.items():
        for port in CDP_PORTS:
            try:
                for t in list_targets(port):
                    if t.get("type") == "page" and spec["tab"].lower() in (t.get("url", "") or "").lower():
                        out.append({"host": host, "port": port, "url": t.get("url", ""),
                                    "title": (t.get("title", "") or "")[:60]})
            except Exception:
                continue
    return out


# ------------------------------------------------------- proven adapter paths ----
def _gen_flow(prompt: str, port: Optional[int]) -> Dict[str, Any]:
    """Google Flow via the PROVEN FlowSession adapter (googleflow_client.py). Mints the
    reCAPTCHA token inside the live tab and speaks Flow's real batchAsyncGenerateVideoText
    RPC. Costs Flow credits (~20/clip) — the pool's cooldown spaces calls out."""
    import googleflow_client as gf
    sess = gf.FlowSession(port=port or 9222).refresh()
    try:
        r = gf.submit(sess, prompt)
    except RuntimeError as e:
        raise ChatError("FLOW_SUBMIT", str(e)[:300])
    media_list = r.get("media") or []
    media_id = media_list[0].get("name") if media_list else None
    if not media_id:
        raise ChatError("FLOW_SUBMIT", f"no media name in submit result: {str(r)[:200]}")
    try:
        gf.wait(sess, media_id, budget=VIDEO_TIMEOUT_S)
    except (RuntimeError, TimeoutError) as e:
        raise ChatError("FLOW_STATUS", str(e)[:300])
    url = gf.MEDIA_URL.format(media_id)
    return {"text": url, "video_url": url, "label": "chrome-video/labs.google",
            "media_id": media_id}


def _gen_flow_ui(prompt: str, port: Optional[int]) -> Dict[str, Any]:
    """Google Flow via the MIGRATION-FITTED UI adapter (flow_ui_client.py, worklog #1637).

    Google migrated labs.google -> flow.google.com and retired the NextAuth session JSON
    endpoint entirely, so the REST+bearer FlowSession path is dead on every seat. This
    adapter drives the provider's own UI in the live signed-in project tab: credits
    gate -> insertText+Enter submit -> queue-aware DOM poll -> in-run signed-URL HEAD
    proof. Spend-gated inside the client (OMNI_VIDEO_CONFIRM_SPEND / OMNI_VIDEO_MAX_SPEND).
    """
    from flow_ui_client import FlowUiClient
    c = FlowUiClient()
    c.port_hint = port
    r = c.chat([{"role": "user", "content": prompt}])
    return {"text": r.get("text"), "video_url": r.get("video_url"),
            "label": "chrome-video/labs.google", "url_proof": r.get("url_proof"),
            "credits_before": r.get("credits_before")}


def _gen_veofree(prompt: str, port: Optional[int]) -> Dict[str, Any]:
    """veoaifree.com via the PROVEN VeoFreeSession adapter (veoaifree_client.py): the
    site's own admin-ajax nonce protocol, executed inside the logged-in tab. Free, but
    the free allowance is 2 videos/account and may already be exhausted — a Limit/Rate
    Limit answer is reported as a wall (Law 5), never retried."""
    from veoaifree_client import VeoFreeSession, VeoFreeError
    sess = VeoFreeSession(port=port or 9222)
    try:
        scene = sess.submit(prompt)
    except VeoFreeError as e:
        kind = getattr(e, "args", [""])[0] if e.args else ""
        if kind in ("LIMIT", "BUSY"):
            raise ChatError("WALL", f"veoaifree allowance: {str(e)[:200]}")
        raise ChatError("VEOFREE_SUBMIT", str(e)[:200])
    try:
        url = sess.wait(scene, timeout=VIDEO_TIMEOUT_S)
    except VeoFreeError as e:
        kind = e.args[0] if e.args else ""
        if kind == "LIMIT":
            raise ChatError("WALL", f"veoaifree allowance: {str(e)[:200]}")
        raise ChatError("VEOFREE_POLL", str(e)[:200])
    if not url:
        raise ChatError("VEOFREE_POLL", "poll never reached a terminal state")
    return {"text": url, "video_url": url, "label": "chrome-video/veoaifree.com",
            "scene": scene}


_ADAPTERS = {"flow": _gen_flow, "flow-ui": _gen_flow_ui, "veofree": _gen_veofree}


# ------------------------------------------------------------ generic UI driver ----
def _gen_ui(prompt: str, spec: Dict[str, Any], port: Optional[int]) -> Dict[str, Any]:
    """Drive the site's own UI in the live tab: inject prompt -> press the site's own
    generate -> poll the site's own DOM for the finished video URL."""
    tab = find_tab(spec["tab"], prefer_port=port)
    if not tab:
        raise ChatError("NO_TAB", f"no open tab matching {spec['tab']!r} on any seat Chrome")
    port = tab["port"]
    gen_re = spec.get("gen", r"generate|create|send|submit")

    with Page(match=spec["tab"], timeout=30, port=port) as pg:
        # Heavy video-site pages (heygen/magichour/giz) took >45s just to answer the
        # inject/click evaluates (worklog #1122: three "Runtime.evaluate did not answer
        # within 45s" false failures). Give setup steps real headroom; the long wait is
        # the poll below, which already carries VIDEO_TIMEOUT_S.
        inject = INJECT_JS.replace("__PROMPT_JSON__", json.dumps(prompt))
        r1 = pg.evaluate(inject, timeout=120)
        if not (isinstance(r1, dict) and r1.get("ok")):
            raise ChatError("NO_INPUT",
                            (r1 or {}).get("why", "no visible input") if isinstance(r1, dict)
                            else "inject returned nothing")
        runid = f"cvc-{int(time.time()*1000)}"
        pg.evaluate(SNAP_VIDEO_JS.replace("__RUNID_JSON__", json.dumps(runid)), timeout=120)
        click = CLICK_GEN_JS.replace("__GENRE_JSON__", json.dumps(gen_re))
        r2 = pg.evaluate(click, timeout=120)
        if not (isinstance(r2, dict) and r2.get("ok")):
            raise ChatError("NO_GENERATE",
                            (r2 or {}).get("why", "no generate button") if isinstance(r2, dict)
                            else "click returned nothing")

        # Poll in the SAME websocket — the Promise holds until the video appears or the
        # budget expires (awaitPromise=True in cdp.py's evaluate).
        poll = POLL_VIDEO_JS.replace("__RUNID_JSON__", json.dumps(runid)) \
                            .replace("TIMEOUT_MS", str(VIDEO_TIMEOUT_S * 1000)) \
                            .replace("POLL_MS", str(POLL_EVERY_MS))
        r3 = pg.evaluate(poll, timeout=VIDEO_TIMEOUT_S + 60)

    if not (isinstance(r3, dict) and r3.get("found")):
        raise ChatError("NO_VIDEO", f"no video URL appeared within {VIDEO_TIMEOUT_S}s")
    url = r3.get("url", "")
    if url.startswith("blob:"):
        # The UI plays via MediaSource; the bytes never surface as a URL. Report honestly.
        raise ChatError("BLOB_ONLY", "video rendered as blob: only — no downloadable URL in DOM")
    host = next((h for h, s in VIDEO_HOSTS.items() if s is spec), spec["tab"])
    return {"text": url, "video_url": url, "label": f"chrome-video/{host}",
            "chrome_ms": r3.get("ms"), "tab": tab.get("url", "")}


# ------------------------------------------------------------------ pool client ----
class ChromeVideoClient:
    """Pool client that serves a VIDEO generation by driving the provider's own UI inside
    the live signed-in Chrome (adapter thesis). Implements the exact pool contract."""

    def __init__(self, secret=None, host: Optional[str] = None, **kw):
        self.secret = pathlib.Path(secret) if secret else None
        raw = {}
        if self.secret and self.secret.exists():
            try:
                # utf-8-sig: a hot-add seat file dropped from PowerShell/Notepad may carry
                # a BOM; json.loads chokes on it and would silently drop the chrome decl.
                raw = json.loads(self.secret.read_text(encoding="utf-8-sig"))
            except Exception:
                raw = {}
        self.host = host or raw.get("host") or ""
        self.spec = VIDEO_HOSTS.get(self.host)
        # One Chrome, infinite sites (worklog #1112): a seat may declare its own video UI
        # inline ("chrome": {"tab": "newsite.com", "gen": "..."} or "chrome": "newsite.com")
        # with NO VIDEO_HOSTS entry. The site's own JS is the adapter, so we build a generic
        # "ui" spec straight from the seat file -- zero registry code for a new provider.
        if self.spec is None:
            chrome_decl = raw.get("chrome")
            tab = None
            if isinstance(chrome_decl, dict) and chrome_decl.get("tab"):
                tab = str(chrome_decl["tab"])
            elif isinstance(chrome_decl, str) and chrome_decl not in ("", "true", "True"):
                tab = chrome_decl
            if tab:
                self.spec = {"tab": tab, "kind": "ui"}
                if isinstance(chrome_decl, dict) and chrome_decl.get("gen"):
                    self.spec["gen"] = str(chrome_decl["gen"])
        # Seat pinning: "chrome_port" (legacy) or the chrome-flow-tab decl's
        # "chrome": {"cdpPort": N} (worklog #1630 shape) — one account per profile.
        self.port_hint = (raw.get("chrome_port")
                          or (raw.get("chrome") or {}).get("cdpPort"))
        self.label = f"chrome-video/{self.host}"

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not self.spec:
            raise ChatError("NO_ADAPTER", f"no video adapter registered for {self.host!r}")
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = _flatten_prompt(messages)

        kind = self.spec["kind"]
        if kind == "adapter":
            fn = _ADAPTERS[self.spec["adapter"]]
            r = fn(prompt, self.port_hint)
        else:
            r = _gen_ui(prompt, self.spec, self.port_hint)
        r.setdefault("label", self.label)
        r["modality"] = "video"
        return r


# ------------------------------------------------------------- self-test CLI ----
def _cmd_tabs() -> int:
    tabs = all_video_tabs()
    if not tabs:
        print("no video tabs found on any seat Chrome (are 9222-9225 running?)")
        return 1
    for t in tabs:
        print(f":{t['port']}  {t['host']:<20} {t['title']}")
    print(f"\n{len(tabs)} video tabs across {len(set(t['port'] for t in tabs))} seat Chromes")
    return 0


def _cmd_doctor(host: str, port: Optional[int]) -> int:
    spec = VIDEO_HOSTS.get(host)
    if not spec:
        print(f"unknown host {host!r}; have: {', '.join(VIDEO_HOSTS)}")
        return 1
    tab = find_tab(spec["tab"], prefer_port=port)
    if not tab:
        print(f"NO_TAB: no open tab matching {spec['tab']!r}")
        return 1
    print(f"tab found on :{tab['port']}  {tab.get('url','')[:80]}")
    with Page(match=spec["tab"], timeout=30, port=tab["port"]) as pg:
        has_input = pg.evaluate(r"""
        (()=>{ const v=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
          return !!(Array.from(document.querySelectorAll('textarea')).find(v)
                 || Array.from(document.querySelectorAll('[contenteditable="true"]')).find(v)); })()
        """)
    print(f"visible input present: {bool(has_input)}")
    return 0 if has_input else 1


def _cmd_gen(host: str, prompt: str, port: Optional[int], yes: bool) -> int:
    if not yes:
        print("refusing to generate without --yes (this spends the account's free allowance)")
        return 2
    c = ChromeVideoClient(host=host)
    c.port_hint = port
    t0 = time.time()
    try:
        r = c.chat([{"role": "user", "content": prompt}])
    except (ChatError, SessionExpired) as e:
        print(f"ERR {e}")
        return 1
    print(f"OK {int(time.time()-t0)}s label={r['label']}")
    print(f"video_url={r.get('video_url')}")
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=None, help="pin one seat Chrome port")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tabs")
    p_doc = sub.add_parser("doctor"); p_doc.add_argument("host")
    p_gen = sub.add_parser("gen"); p_gen.add_argument("host"); p_gen.add_argument("prompt")
    p_gen.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "tabs":
        return _cmd_tabs()
    if a.cmd == "doctor":
        return _cmd_doctor(a.host, a.port)
    if a.cmd == "gen":
        return _cmd_gen(a.host, a.prompt, a.port, a.yes)
    return 2


if __name__ == "__main__":
    sys.exit(main())
