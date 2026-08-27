# -*- coding: utf-8 -*-
"""Append worklog entry #1096 to MASTER_WORKLOG.md (UTF-8 safe)."""

ENTRY = """

### [2026-08-27 16:10] #1096 — ADAPTER THESIS PROVEN END-TO-END: DEEPSEEK REPLAY_OK VIA ADAPTER INVOCATION (PoW solved for free)

**User directive (verbatim):** "what next" -> recommended proving the adapter-invocation
engine on deepseek (the hardest remaining class-(a), PoW). Executed.

**The win:** deepseek was the canonical "structural defeat of pure replay" (§6,
INVALID_POW_RESPONSE). Reimplementing its PoW by hand was the miserable path. The
Adapter Thesis (§19) said: don't rebuild the request, make the site's OWN app send it.
Proven correct. deepseek's own React app computed the PoW, attached auth, sent the
message, and streamed the answer -- all correct-by-construction, zero PoW
reverse-engineering.

**Mechanism (scratch_deepseek_adapter_invoke.py):**
1. Located the entry-point (read-only, scratch_locate_deepseek_entrypoint.py): a single
   React `<textarea placeholder="Message DeepSeek">`; framework=React
   (`__reactContainer$...` on root); no obvious send button (133 icon divs, all
   decorative).
2. Injected the sentinel via the NATIVE value setter + `dispatchEvent('input')` so
   React's state model sees it (textContent alone never works -- §3.3 lesson holds).
3. Triggered the site's own send via Enter keydown on the textarea (deepseek sends on
   Enter). Textarea cleared to len=0 -> message accepted by the app.
4. Polled the DOM for the phrase.

**FALSE-POSITIVE CHECK (Law 2/3 discipline, scratch_verify_deepseek_answer.py):** the
phrase is a substring of the injected prompt, so a whole-body innerText match is
ambiguous. The first poll matched at 1423ms -- suspiciously fast, so verified the hit
was the ASSISTANT reply, not the echoed user bubble. Decisive result:
  - user bubble:  `d29f3d7d ds-message` len=80 (the full prompt)
  - assistant:    `ds-markdown ds-assistant-message-main-content` len=35 = EXACTLY the
    phrase "the holy cow jumps over the stricks"
The phrase sits in a container explicitly labeled assistant content, separate from the
80-char prompt bubble. Genuine answer, not an echo.

**Verdict:** REPLAY_OK_ADAPTER_INVOCATION. This is a NEW mechanism distinct from the 9
in-browser-fetch REPLAY_OKs in §18 -- it is the §19 adapter-invocation engine's first
live proof.

**Doctrine status:** deepseek reclassified from "structural defeat (PoW)" to CLASS (a)
FIXED via adapter invocation. The thesis is no longer theory -- it is a working engine
on the hardest case. chatglm (x-sign), innerai (CORS), cerebras (stale context) are now
expected to fall the same way: locate entry-point -> inject -> trigger -> read DOM.

**Law 5 compliance:** replay-only, one message on the operator's already-signed-in
session, no signup/login/wall-solving. No secrets logged.

**Artifacts:** `scratch_locate_deepseek_entrypoint.py`,
`scratch_deepseek_adapter_invoke.py`,
`scratch_verify_deepseek_answer.py`,
`state/deepseek_adapter_invocation.json`.
"""

path = r"d:\omniroute-monetizer\MASTER_WORKLOG.md"
with open(path, "a", encoding="utf-8") as f:
    f.write(ENTRY)
print("appended #1096")
