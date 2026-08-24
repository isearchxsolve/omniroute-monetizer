"""Read-only recon of the veoaifree chat surface (task 1).

Attaches to the logged-in veoaifree chat tab over CDP (port 9222) and inspects the chat
protocol WITHOUT sending a message and WITHOUT exfiltrating secrets:
  - which chat routes exist (nav links + open tabs)
  - the admin-ajax action name(s) the composer uses (regex-extracted from plugin JS)
  - the model selector options (UI label -> internal value)
  - localized config-object shapes (key names; nonce/token/high-entropy -> length only)
  - storage KEY NAMES only (never values)

Anything secret-shaped (nonce/security/token/... by key name, OR any bare high-entropy
string value) is reduced to 'len:N' / 'type:T'. No script BODIES are returned — only safe
regex matches (action names, endpoint paths, chat-y identifiers). Strictly read-only:
no POST, no click, no navigation, no state change.
"""
from __future__ import annotations
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "automation"))
from cdp import Page, DEFAULT_PORT, list_targets

PORT = DEFAULT_PORT

RECON_JS = r"""
(async () => {
  const out = {href: location.href, title: document.title};
  const uniq = (a) => Array.from(new Set(a));
  const SECRET = /(nonce|token|secret|_wpnonce|security|apikey|api_key|auth|session|cookie|jwt|bearer|csrf|password|passwd|sign|hash)/i;
  const looksToken = (s) => typeof s === 'string' && /^[A-Za-z0-9_\-]{16,}$/.test(s);

  // --- config objects on window (wp_localize_script targets) ---
  try {
    const cfg = {};
    for (const k of Object.getOwnPropertyNames(window)) {
      let v; try { v = window[k]; } catch(e){ continue; }
      if (!v || typeof v !== 'object' || Array.isArray(v)) continue;
      let keys; try { keys = Object.keys(v); } catch(e){ continue; }
      const low = keys.join(',').toLowerCase();
      if (!/ajax|nonce|action|rest|api|endpoint|url/.test(low)) continue;
      const desc = {};
      for (const kk of keys.slice(0, 40)) {
        let vv; try { vv = v[kk]; } catch(e){ desc[kk]='<err>'; continue; }
        if (SECRET.test(kk) || looksToken(vv)) { desc[kk] = (typeof vv==='string')?('len:'+vv.length):('type:'+typeof vv); }
        else if (typeof vv === 'string') { desc[kk] = vv.length>160 ? (vv.slice(0,160)+'…') : vv; }
        else if (vv && typeof vv === 'object') { desc[kk] = 'obj{'+Object.keys(vv).slice(0,15).join(',')+'}'; }
        else { desc[kk] = 'type:'+typeof vv; }
      }
      cfg[k] = desc;
    }
    out.configObjects = cfg;
  } catch(e){ out.configErr = String(e); }

  // --- same-origin nav links that look like chat routes ---
  try {
    out.chatLinks = uniq(Array.from(document.querySelectorAll('a[href]'))
      .map(a=>a.getAttribute('href')||'')
      .filter(h=>/veoaifree\.com/i.test(h) || h.startsWith('/'))
      .filter(h=>/(gemini|claude|chatgpt|gpt|grok|chat|kimi|glm|nemotron|deepseek|llm|ai-)/i.test(h)))
      .slice(0, 40);
  } catch(e){ out.linksErr = String(e); }

  // --- model selector(s): UI label -> internal value ---
  try {
    const models = [];
    document.querySelectorAll('select').forEach(sel => {
      const opts = Array.from(sel.options||[]).map(o=>({value:o.value, text:(o.textContent||'').trim().slice(0,60)}));
      if (opts.some(o=>/gpt|claude|grok|gemini|kimi|glm|nemotron|deepseek|opus|sonnet|flash|pro/i.test(o.text+o.value)))
        models.push({sel: sel.id||sel.name||sel.className||'select', options: opts.slice(0,40)});
    });
    const pick = [];
    document.querySelectorAll('[data-model],[data-value],[role="option"],.model-item,.model-option,li[data-id]').forEach(el=>{
      const label=(el.textContent||'').trim().slice(0,50);
      const dm=el.getAttribute('data-model')||el.getAttribute('data-value')||el.getAttribute('data-id')||'';
      if ((label||dm) && /gpt|claude|grok|gemini|kimi|glm|nemotron|deepseek|opus|sonnet/i.test(label+dm))
        pick.push({label, data: dm});
    });
    out.modelSelects = models;
    out.modelItems = uniq(pick.map(x=>JSON.stringify(x))).slice(0,40).map(s=>JSON.parse(s));
  } catch(e){ out.modelErr = String(e); }

  // --- composer form / send button / input shape ---
  try {
    const forms = [];
    document.querySelectorAll('form').forEach(f=>{
      forms.push({action: f.getAttribute('action')||'', method: f.getAttribute('method')||'',
        fields: Array.from(f.querySelectorAll('input,textarea,select')).map(i=>({name:i.name||i.id||'', type:i.type||i.tagName.toLowerCase()})).slice(0,20)});
    });
    out.forms = forms.slice(0,8);
    const btn = document.querySelector('button[type=submit],[class*="send"],[id*="send"],button');
    if (btn) out.sendBtn = {tag:btn.tagName, id:btn.id||'', cls:(btn.className||'').slice(0,80),
      data: Array.from(btn.attributes||[]).filter(a=>a.name.startsWith('data-')).map(a=>a.name+'='+String(a.value).slice(0,40))};
    const ta = document.querySelector('textarea, input[type=text][class*="chat"], [contenteditable="true"]');
    if (ta) out.input = {tag:ta.tagName, id:ta.id||'', name:ta.name||'', cls:(ta.className||'').slice(0,80), ce: ta.getAttribute('contenteditable')||''};
  } catch(e){ out.formErr = String(e); }

  // --- scan scripts for action names / endpoints (MATCHES only, never bodies) ---
  const ACT = /action['"]?\s*[:=]\s*['"]([a-z0-9_]{3,40})['"]/gi;
  const NAMEY = /['"]([a-z_]{0,20}(?:chat|gemini|veo|generate|complete|message|stream|ai_)[a-z_]{0,20})['"]/gi;
  const EP = /(admin-ajax\.php|wp-json\/[a-z0-9\/_-]{2,60}|\/api\/[a-z0-9\/_-]{2,60}|\/v1\/[a-z0-9\/_-]{2,40})/gi;
  const drop = (s) => /^[a-f0-9]{16,}$/i.test(s) || s.length>40;
  const grab = (txt) => {
    const r = {actions:[], namey:[], endpoints:[]}; let m;
    ACT.lastIndex=0; while((m=ACT.exec(txt))) if(!drop(m[1])) r.actions.push(m[1]);
    NAMEY.lastIndex=0; while((m=NAMEY.exec(txt))) if(!drop(m[1])) r.namey.push(m[1]);
    EP.lastIndex=0; while((m=EP.exec(txt))) r.endpoints.push(m[0]);
    return r;
  };
  try {
    const acc = {actions:[], namey:[], endpoints:[]};
    document.querySelectorAll('script:not([src])').forEach(s=>{
      const g = grab((s.textContent||'').slice(0, 400000));
      acc.actions.push(...g.actions); acc.namey.push(...g.namey); acc.endpoints.push(...g.endpoints);
    });
    const srcs = uniq(Array.from(document.querySelectorAll('script[src]')).map(s=>s.src)
      .filter(u=>/veoaifree\.com/i.test(u) && /(gemini|chat|veo|ai|plugin|wp-content)/i.test(u)))
      .slice(0, 12);
    out.scriptSrcs = srcs;
    for (const u of srcs) {
      try { const t = await (await fetch(u, {credentials:'omit'})).text();
        const g = grab(t.slice(0, 500000));
        acc.actions.push(...g.actions); acc.namey.push(...g.namey); acc.endpoints.push(...g.endpoints);
      } catch(e){}
    }
    out.actions = uniq(acc.actions).slice(0,60);
    out.nameyStrings = uniq(acc.namey).slice(0,60);
    out.endpoints = uniq(acc.endpoints).slice(0,60);
  } catch(e){ out.scriptErr = String(e); }

  // --- storage KEY NAMES only (never values) ---
  try {
    const sk = (store) => { const o=[]; for(let i=0;i<store.length;i++){const k=store.key(i); let L=0; try{L=(store.getItem(k)||'').length;}catch(e){} o.push(k+' (len:'+L+')');} return o.slice(0,40); };
    out.localStorageKeys = sk(localStorage);
    out.sessionStorageKeys = sk(sessionStorage);
  } catch(e){ out.storageErr = String(e); }

  return out;
})()
"""

def main():
    port = PORT
    tgts = [t for t in list_targets(port) if t.get("type") == "page"]
    veo = [t for t in tgts if "veoaifree.com" in (t.get("url", "") + t.get("title", "")).lower()]
    print("=== veoaifree page targets ===")
    for t in veo:
        print(f'  {str(t.get("id",""))[:16]}  {t.get("url","")[:82]}')
    if not veo:
        print("\nno veoaifree tab open; recon needs the logged-in chat tab.")
        return 1

    def score(t):
        u = t.get("url", "").lower()
        for i, kw in enumerate(["/gemini", "/claude", "/chatgpt", "/grok", "/chat", "chat", "gemini"]):
            if kw in u:
                return i
        return 99
    chat = sorted(veo, key=score)[0]
    match = chat.get("url", "")  # exact url is a valid (unique) substring match
    print(f'\n=== reconning (read-only): {match[:82]}\n')

    with Page(match, port=port) as p:
        data = p.evaluate(RECON_JS, timeout=60)

    out = pathlib.Path(__file__).resolve().parents[1] / "state" / "harvest" / "veo_chat_recon.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    txt = json.dumps(data, indent=2, ensure_ascii=False)
    print(txt[:6500])
    if len(txt) > 6500:
        print(f"\n... (truncated; full recon -> {out})")
    else:
        print(f"\n(full recon -> {out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
