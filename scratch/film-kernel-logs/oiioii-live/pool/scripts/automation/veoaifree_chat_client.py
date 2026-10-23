"""veoaifree CHAT client — free, unlimited, frontier chat driven IN-PAGE over CDP.

Mirrors veoaifree_client.py (the video sibling): the request executes inside the logged-in
veoaifree.com/gemini tab over the Chrome remote-debugging port, so the WordPress session cookie
never leaves the browser and no secret ever enters Python. The chat backend is veo-proxy.php
(Perplexity-style SSE); we let the site's own assembler (window.VeoChat.send.getFinalAnswer)
turn the stream into clean text.

Contract (reverse-engineered + verified live 2026-08-24): POST veo-proxy.php with
{query_str, prompt, user_name, model:<label>, model_preference:<id>, frontend_uuid, is_related,
web_search, messages[]}. Cookie auth only (no nonce). See the veoaifree-chat-harness-contract memo.

CONCURRENCY: one CDP websocket per tab is not safe for parallel Runtime.evaluate, so every chat()
serializes on a module lock. Each call is ~3-7s (Claude Sonnet 5 was fastest in probing).
Strictly no state mutation on the account: this standalone fetch does not call the site's
persistToDb, so it does not write to the user's chat history.
"""
from __future__ import annotations
import base64, json, threading, time
from typing import Any, Dict, List, Optional, Tuple

from cdp import Page, DEFAULT_PORT

MATCH = "veoaifree.com/gemini"          # the logged-in chat tab
PROXY_PATH = "/wp-content/themes/really-simple-child/veo-proxy.php"

# Live models (label + preference) exactly as veo-chat-config.js ships them. The map is keyed by a
# stable short id; we also accept the label or the raw preference as an alias so a pool can address
# a model however it likes. `thinking` is the preference used when the caller asks for reasoning.
MODELS: List[Dict[str, Optional[str]]] = [
    {"id": "gpt-terra",     "label": "GPT-5.6 Terra",    "pref": "gpt56_terra",         "thinking": "gpt56_terra_thinking"},
    {"id": "gemini",        "label": "Gemini 3.1 Pro",   "pref": "gemini31pro_high",    "thinking": None},
    {"id": "gemini_pro",    "label": "Gemini 3.7 Flash", "pref": "gemini37flash",       "thinking": "gemini37flashthinking"},
    {"id": "claude-sonnet", "label": "Claude Sonnet 5",  "pref": "claude50sonnet",      "thinking": "claude50sonnetthinking"},
    {"id": "kimi",          "label": "Kimi K3",          "pref": "kimik3",              "thinking": "kimik3thinking"},
    {"id": "glm",           "label": "GLM 5.2",          "pref": "glm_5_2",             "thinking": None},
    {"id": "grok",          "label": "Grok 4.5",         "pref": "grok45medium",        "thinking": None},
    {"id": "nemotron",      "label": "Nemotron 3 Ultra", "pref": "nv_nemotron_3_ultra", "thinking": None},
]
# Commented-out "Max" tiers in the live UI. Disabled by default; opt in explicitly (untested — may
# be rejected server-side). This is the "extra edge" reach, not a promise.
MODELS_MAX: List[Dict[str, Optional[str]]] = [
    {"id": "gpt-sol",     "label": "GPT-5.6 Sol",   "pref": "gpt56_sol",   "thinking": "gpt56_sol_thinking"},
    {"id": "claude-opus", "label": "Claude Opus 5", "pref": "claude50opus", "thinking": "claude50opusthinking"},
]

_ALL = MODELS + MODELS_MAX
DEFAULT_ID = "gemini_pro"   # Gemini 3.7 Flash — fast, "New"; a safe default head

_LOCK = threading.Lock()    # one CDP evaluate against the single tab at a time


class ChatError(Exception):
    def __init__(self, kind: str, message: str, status: Optional[int] = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.status = status


# One in-page POST to veo-proxy.php. user_name + frontend_uuid are filled INSIDE the page (from
# window.VEO_CHAT_CONFIG / crypto) so no identity or session material is ever passed from Python.
# The payload the caller controls (query/label/pref/messages/flags) arrives base64'd to dodge all
# quoting hazards. Returns clean assembled text via the site's own getFinalAnswer.
CHAT_JS = r"""
(async () => {
  const inp = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob("__B64__"), c=>c.charCodeAt(0))));
  const cfg = window.VEO_CHAT_CONFIG || {};
  if (!cfg.proxyUrl) return {ok:false, kind:"NO_CONFIG", err:"VEO_CHAT_CONFIG.proxyUrl missing (wrong tab?)"};
  const payload = {
    query_str: inp.query, prompt: inp.query,
    user_name: cfg.currentUserName || "",
    model: inp.label, model_preference: inp.pref,
    frontend_uuid: (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())+String(Math.random()).slice(2)),
    is_related: !!inp.is_related, web_search: !!inp.web_search,
    messages: Array.isArray(inp.messages) ? inp.messages : []
  };
  const t0 = performance.now();
  let r;
  try {
    r = await fetch(cfg.proxyUrl, {method:"POST",
      headers:{"Content-Type":"application/json","Accept":"text/event-stream"},
      body: JSON.stringify(payload)});
  } catch(e){ return {ok:false, kind:"NETWORK", err:String(e)}; }
  let raw = "";
  try { raw = await r.text(); } catch(e){ return {ok:false, kind:"READ", status:r.status, err:String(e)}; }
  if (!r.ok) return {ok:false, kind:"HTTP", status:r.status, err:(raw||"").slice(0,300)};
  let answer = "";
  try { answer = window.VeoChat.send.getFinalAnswer(raw); }
  catch(e){ return {ok:false, kind:"ASSEMBLE", status:r.status, err:String(e), rawLen: raw.length}; }
  return {ok:true, status:r.status, ms: Math.round(performance.now()-t0), rawLen: raw.length, answer: answer||""};
})()
"""

def normalize_model(name: Optional[str], allow_max: bool = False) -> Tuple[str, str, bool]:
    """Resolve a caller model name -> (label, preference, is_thinking).

    Accepts a short id ('claude-sonnet'), the UI label ('Claude Sonnet 5'), the raw preference
    ('claude50sonnet'), an optional 'veoaifree/' prefix, and a '-thinking'/':thinking' suffix that
    flips to the model's reasoning preference. Unknown -> ChatError so the pool learns immediately.
    """
    raw = (name or DEFAULT_ID).strip()
    if raw.lower().startswith("veoaifree/"):
        raw = raw.split("/", 1)[1]
    thinking = False
    for suf in ("-thinking", ":thinking", " (thinking)", "_thinking"):
        if raw.lower().endswith(suf):
            thinking, raw = True, raw[: -len(suf)].strip()
            break
    low = raw.lower()
    pool = _ALL if allow_max else MODELS
    for m in pool:
        if low in (m["id"].lower(), (m["label"] or "").lower(), (m["pref"] or "").lower()):
            pref = m["thinking"] if (thinking and m["thinking"]) else m["pref"]
            return m["label"], pref, bool(thinking and m["thinking"])
    # tolerate the thinking-preference string itself
    for m in pool:
        if m["thinking"] and low == m["thinking"].lower():
            return m["label"], m["thinking"], True
    raise ChatError("UNKNOWN_MODEL", f"{name!r} is not a veoaifree model; try one of "
                    + ", ".join(m["id"] for m in pool))


def build_payload_fields(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, str]], bool]:
    """OpenAI-style messages -> (query, convo, is_related) for veo-proxy.php.

    veoaifree has no system slot, so system text is folded as a prefix onto the current prompt.
    `convo` mirrors what the site sends (full turn list incl. the current user turn, role 'bot'
    normalized to 'assistant'); `query` is that current prompt. is_related once there's prior turns.
    """
    sys_txt = "\n\n".join(str(m.get("content", "")).strip()
                          for m in messages if m.get("role") == "system" and m.get("content"))
    convo: List[Dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        if role in ("user", "assistant", "bot"):
            convo.append({"role": "assistant" if role in ("assistant", "bot") else "user",
                          "content": str(m.get("content", ""))})
    if not convo:
        convo = [{"role": "user", "content": sys_txt or ""}]
    # locate the current prompt = last user turn (fallback: last turn)
    idx = next((i for i in range(len(convo) - 1, -1, -1) if convo[i]["role"] == "user"), len(convo) - 1)
    if sys_txt:
        convo[idx]["content"] = f"{sys_txt}\n\n{convo[idx]['content']}".strip()
    query = convo[idx]["content"]
    is_related = len(convo) > 1
    return query, convo, is_related


class VeoChatClient:
    def __init__(self, match: str = MATCH, port: int = DEFAULT_PORT, timeout: int = 120):
        self.match = match
        self.port = port
        self.timeout = timeout

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             web_search: bool = False, allow_max: bool = False,
             timeout: Optional[int] = None) -> Dict[str, Any]:
        """Blocking completion. Returns {text, model, label, ms}. Raises ChatError on failure."""
        label, pref, thinking = normalize_model(model, allow_max=allow_max)
        query, convo, is_related = build_payload_fields(messages)
        # Faithful to veo-chat-send.js: history is sent ONLY when is_related (else []). Sending a
        # non-empty messages[] on a fresh turn trips the backend's "Sign up and repeat" guard.
        inp = {"query": query, "label": label, "pref": pref,
               "messages": convo if is_related else [], "is_related": is_related,
               "web_search": bool(web_search)}
        b64 = base64.b64encode(json.dumps(inp, ensure_ascii=False).encode("utf-8")).decode("ascii")
        expr = CHAT_JS.replace("__B64__", b64)
        to = timeout or self.timeout
        with _LOCK:
            with Page(self.match, port=self.port, timeout=to + 10) as p:
                res = p.evaluate(expr, timeout=to)
        if not isinstance(res, dict):
            raise ChatError("BAD_EVAL", f"unexpected evaluate result: {type(res).__name__}")
        if not res.get("ok"):
            raise ChatError(res.get("kind") or "ERROR", str(res.get("err") or "unknown"),
                            status=res.get("status"))
        text = (res.get("answer") or "").strip()
        if not text:
            raise ChatError("EMPTY", "assembler produced no text", status=res.get("status"))
        return {"text": text, "model": pref + (" (thinking)" if thinking else ""),
                "label": label, "ms": res.get("ms"), "raw_len": res.get("rawLen")}

    def list_models(self, allow_max: bool = False) -> List[Dict[str, Optional[str]]]:
        return list(_ALL if allow_max else MODELS)

    def doctor(self) -> Dict[str, Any]:
        """Zero-cost health probe: confirms the tab + config + assembler are present. No POST."""
        js = r"""(() => { const c = window.VEO_CHAT_CONFIG||{}; return {
          href: location.href, hasProxy: !!c.proxyUrl,
          hasAssembler: !!(window.VeoChat && window.VeoChat.send && window.VeoChat.send.getFinalAnswer),
          userSet: !!c.currentUserName, loggedIn: !!c.isLoggedIn }; })()"""
        with _LOCK:
            with Page(self.match, port=self.port, timeout=20) as p:
                return p.evaluate(js, timeout=15)


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="veoaifree chat client (CDP, in-page)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--match", default=MATCH)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("models")
    s = sub.add_parser("chat")
    s.add_argument("prompt")
    s.add_argument("--model", default=DEFAULT_ID)
    s.add_argument("--max", action="store_true", help="allow the commented-out Opus/Sol tiers")
    s.add_argument("--web", action="store_true")
    a = ap.parse_args()
    c = VeoChatClient(match=a.match, port=a.port)
    if a.cmd == "doctor":
        print(json.dumps(c.doctor(), indent=2)); return 0
    if a.cmd == "models":
        for m in c.list_models(allow_max=True):
            print(f'  {m["id"]:14s} {m["label"]:18s} pref={m["pref"]}')
        return 0
    if a.cmd == "chat":
        t0 = time.time()
        r = c.chat([{"role": "user", "content": a.prompt}], model=a.model,
                   web_search=a.web, allow_max=a.max)
        print(f'[{r["label"]} | {r["model"]} | {r.get("ms")}ms | {int((time.time()-t0)*1000)}ms wall]\n')
        print(r["text"])
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
