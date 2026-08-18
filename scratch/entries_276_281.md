### [2026-08-18 20:25] #276 — Nomic wired via Google SSO + Auth0 native API-key connection
**What:** Navigated to atlas.nomic.ai. Google SSO via Auth0 completed with the profile's existing account (standard name + email consent). Reached the authenticated org dashboard for organization "xxpertcomments" at atlas.nomic.ai/data/xxpertcomments. Navigated to org API Keys settings at /data/xxpertcomments/org/settings/api-keys via the CLI-login page (/cli-login). Free tier, no card required.

**Result:** API key named omniroute-monetizer created (nk- prefix, length 46, one-time reveal). Key captured into browser page memory (window.__omni_nomic_key) and reveal modal dismissed. OmniRoute POST /api/providers returned HTTP 201, creating connection c4a4f74e-e46d-4d67-933e-07e1a42b8d1c. Connection auto-activated by native flow; no sync-models or test run. Ledger updated: nomic EXTERNAL_ACCOUNT_REQUIRED -> WIRED_PENDING_VERIFICATION, count 163/11/28.

**Safety:** Key stored in browser page memory only; never printed, logged, or written to files. No payment, CAPTCHA, phone number, database write, or service restart occurred.

**Status:** ✅ Nomic wired; verification deferred.

### [2026-08-18 20:40] #277 — Requesty wired via Google SSO + free account
**What:** Navigated to app.requesty.ai. Google SSO completed (standard name + email + access_type=offline consent). Legal terms accepted via UI checkbox. Dashboard loaded at /model-analytics with $0.00 balance (free account). Navigated to /api-keys.

**Result:** API key named omniroute-monetizer created via "Create key" modal with #api-key-name field (rqsty-sk- prefix, length 117, one-time reveal shown in dialog input field via DOM). Key captured into browser page memory (window.__omni_requesty_key) and reveal modal dismissed. OmniRoute POST /api/providers returned HTTP 201, creating connection fbc59e63-f582-48a7-820c-982739b4954c. Ledger updated: requesty EXTERNAL_ACCOUNT_REQUIRED -> WIRED_PENDING_VERIFICATION, count 162/12/28.

**Safety:** Key stored in browser page memory only from dialog input.value; never printed or written. No payment action, CAPTCHA bypass, database write, or service restart.

**Status:** ✅ Requesty wired; verification deferred.

### [2026-08-18 21:05] #278 — Nscale wired via Google SSO + Service Token
**What:** Navigated to console.nscale.com. Google SSO via Auth0 completed (standard name + email consent). Organization onboarding completed: org named omniroute-monetizer, GDPR checkbox clicked (role=checkbox button with id="gdpr-checkbox"), ToS accepted. Dashboard landed at /organization/b0c77a6a-4132-4021-9790-9fa205ea3c24 showing free $5 credit. Navigated to Settings > Service Tokens tab.

**Result:** Service Token named omniroute-monetizer created via "Add Service Token" modal with name="name" input. Token is JWE format (length 1207, eyJ prefix). Token captured into browser page memory (window.__omni_nscale_key). Reveal modal dismissed via Escape. OmniRoute POST /api/providers returned HTTP 201, creating connection fd4b611a-4f6a-4e23-bb00-a814daeb6f96. No card entered; free $5 credit only.

**Safety:** Token kept in browser page memory only; never printed, logged, or written to files. No payment entered. No database write or service restart.

**Status:** ✅ Nscale wired; verification deferred.

### [2026-08-18 21:25] #279 — Arcee wired via Google SSO + rcai- API key
**What:** Navigated to platform.arcee.ai. Google SSO completed (standard name + email consent for Arcee Platform). Authenticated dashboard reached at /chat. Navigated to API > API Keys section at /api/api-keys. Free account with $5 credit on signup (no card required).

**Result:** API key named omniroute-monetizer created via "Add new" inline form. Key revealed in creation banner (rcai- prefix, length 37, one-time reveal via innerText). Key captured into browser page memory (window.__omni_arcee_key). Reveal banner closed. OmniRoute POST /api/providers with provider=arcee-ai returned HTTP 201, creating connection a76e8f96-f1bd-4952-a7e5-f70e7f0cd26b.

**Safety:** Key stored in browser page memory only from revealed banner text; never printed or written to files. No payment, CAPTCHA bypass, database write, or service restart.

**Status:** ✅ Arcee wired; verification deferred.

### [2026-08-18 21:45] #280 — Morph wired via Google SSO + sk- API key
**What:** Navigated to morphllm.com/sign-up. Google SSO completed (standard name + email consent). Onboarding team name omniroute-monetizer created. Dashboard reached at /dashboard. Navigated to /dashboard/api-keys.

**Result:** API key created via "Create key" button. Morph auto-generated the key immediately in the "Save your API key" modal (sk- prefix, length 51, one-time reveal). Key captured into browser page memory (window.__omni_morph_key) from dialog innerText. Modal closed. OmniRoute POST /api/providers returned HTTP 201, creating connection 9292a402-4388-4bcb-ab26-9936b665a91c. Billing method (optional $10 starter credit) was not added; no payment action taken.

**Safety:** Key stored in browser page memory only; never printed or written. No payment, phone number, CAPTCHA bypass, database write, or service restart.

**Status:** ✅ Morph wired; verification deferred.

### [2026-08-18 22:00] #281 — Navy and Openvecta exact blockers recorded; ByteZ noted for follow-up
**What:** Inspected Navy (api.navy) and Openvecta (openvecta.com) for key acquisition paths, and noted ByteZ status for follow-up.

**Navy:** Homepage loaded after Cloudflare challenge cleared. Free tier exists ($0/day, 150K tokens/day, 20 RPM). However, the /dashboard/keys sign-in surface offers only Discord OAuth — no Google, GitHub, or email option. No approved Discord account exists. Stopped at identity-method blocker. No account, key, or OmniRoute connection created.

**Openvecta:** Homepage inspected. Billing model is per-call in Solana USDC on-chain. The "Get your API key" flow requires creating and funding a Solana USDC wallet. No free/no-payment path exists. Stopped at the blockchain payment requirement. No account, key, or OmniRoute connection created.

**ByteZ:** Homepage viewed. The site advertises a Model API with startup grant credits, but no authenticated key surface was reached in this wave. Provider requires a dedicated inspection pass.

**Ledger batch update:** nscale, arcee-ai, morph now WIRED_PENDING_VERIFICATION; navy and openvecta given exact blockers; bytez noted. Status counts now: 159 EXTERNAL_ACCOUNT_REQUIRED, 15 WIRED_PENDING_VERIFICATION, 28 LIVE_ACTIVE (total 296). Live OmniRoute connections rose from 73 to 79 across this session.

**Safety:** No credentials, payment data, wallet keys, or Discord account data transmitted. No OmniRoute database write or service restart.

**Status:** ✅ Blockers recorded; wave complete for this session.
