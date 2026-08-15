import os

append_text = """
## CRITICAL ANTI-PATTERNS & PAST FAILURES (DO NOT REPEAT)

1. **RESPECT THE ABSTRACTION LAYER (No DB Hacking):**
   - NEVER write scripts that directly modify `storage.sqlite` (e.g., deleting rate limits or scraping audit logs) to fix provider errors.
   - ALWAYS use OmniRoute's native REST APIs or management scripts. Directly manipulating the DB corrupts state and bypasses business logic.
2. **MAINTAIN FULL CONTEXT (The "Handful" Bug):**
   - NEVER test a small handful of providers and declare global success.
   - ALWAYS establish ground truth by querying the total number of configured providers (all 33+/50+ accounts) before declaring a routing cascade as "fixed".
3. **USE VALID DIAGNOSTIC PAYLOADS:**
   - NEVER test models with `max_tokens=2` or generic system-only prompts like "Keep-alive ping". 
   - Frontier and free-tier models reject invalid/tiny payloads, causing false negatives. ALWAYS use valid, standard chat completion payloads.
4. **VERIFY AUTHENTICATION BEFORE CASCADING:**
   - NEVER inject models into front-end routing configs (like `settings.json`) without verifying that the underlying provider's OAuth token or API key is actually alive. 
5. **EXPLICIT HUMAN HANDOFFS:**
   - When browser automation hits a security gate (MFA/CAPTCHA) and halts, NEVER hide the failure in a JSON artifact.
   - ALWAYS explicitly pause execution, output a giant `[HANDOFF REQUIRED]` block in the chat, and force the user to click the link/re-authenticate manually before proceeding.
6. **OAUTH KEEP-ALIVE REALITY:**
   - Acknowledge that sending inference requests does NOT refresh OAuth sessions. Server-side timers dictate expiry. Do not spam APIs with pings to keep them alive if the token is dead.
"""

path = r"D:\omniroute-monetizer\AGENTS.md"

with open(path, "a", encoding="utf-8") as f:
    f.write(append_text)
    
print("Successfully appended rules to AGENTS.md")
