# -*- coding: utf-8 -*-
"""RCA: for each 'dead' host, dump the recorded exchange structure (secrets redacted)
to classify the gap: (a) fixable send-time gap, (b) real server-side death, (c) capture bug."""
import json, pathlib, re, urllib.parse

SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")

# host -> session file
TARGETS = {
    "aymo (RATE 429)": "session_aymo_ai.json",
    "chathub (RATE 429)": "session_chathub_web.json",
    "chatx (WALL)": "session_chatx.json",
    "huggingface (WALL)": "session_huggingchat.json",
    "veoaifree_chat (WALL)": "session_veoaifree_chat_web.json",
    "groq (AUTH 401)": "session_groq_chat.json",
    "veoaifree (AUTH 403)": "session_veoaifree.json",
    "deepseek (SINGLE_USE pow)": "session_deepseek_chat.json",
    "felo (SINGLE_USE message_id)": "session_felo_ai_web.json",
    "mistral (SINGLE_USE 409)": "session_mistral_le_chat.json",
    "cerebras (HTTP_400)": "session_cerebras_inference_chat.json",
    "chatglm (HTTP_400 40013)": "session_zhipu_glm_chat.json",
    "chatgpt (wrong endpoint)": "session_chatgpt_free_web.json",
    "meta (wrong endpoint)": "session_meta_ai_web.json",
    "innerai (Failed to fetch)": "session_inner_ai_web.json",
    "you_com/cr-proxy (EMPTY)": "session_you_com_chat.json",
    "digen (errcode 4000)": "session_digen_ai.json",
}

SECRET_HDR = re.compile(r"auth|token|key|cookie|bearer|x-api|csrf|session", re.I)
DYNAMIC_HDR = re.compile(r"nonce|timestamp|request-id|trace|idempot|device|fingerprint|sentinel|sec-|version|client", re.I)

def redact(v: str) -> str:
    v = str(v)
    if len(v) <= 12:
        return "***"
    return v[:6] + "...REDACTED..." + str(len(v)) + "ch"

for label, fname in TARGETS.items():
    p = SECRETS / fname
    print("=" * 78)
    print("###", label, "->", fname)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("  UNREADABLE:", e)
        continue
    ex = d.get("recorded_exchange") or {}
    url = ex.get("url", "?")
    method = ex.get("method", "?")
    print(f"  {method} {url}")
    hdrs = ex.get("request_headers") or {}
    dyn = [k for k in hdrs if DYNAMIC_HDR.search(k)]
    sec = [k for k in hdrs if SECRET_HDR.search(k)]
    print(f"  headers({len(hdrs)}): {sorted(k.lower() for k in hdrs)}")
    if dyn: print("  DYNAMIC-LOOKING HEADERS:", dyn)
    if sec: print("  SECRET HEADERS (redacted):", {k: redact(hdrs[k]) for k in sec})
    body = ex.get("request_body") or ""
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    body = str(body)
    print(f"  body({len(body)}ch): {body[:300]}")
    # look for dynamic fields inside body
    for pat, name in [(r'"(nonce|timestamp|ts|request_id|idempotency[_-]?key|csrf|device_id|fingerprint|parent_id|conversation_id|chat_id|message_id|pow|challenge|token)"\s*:', "BODY-DYNAMIC")]:
        m = re.findall(pat, body, re.I)
        if m: print(f"  {name} fields:", sorted(set(m)))
    st = d.get("status") or {}
    print(f"  session status: alive={st.get('alive')} reason={st.get('reason')}")
    print()
