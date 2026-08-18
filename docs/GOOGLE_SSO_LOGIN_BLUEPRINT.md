# Autonomous Google SSO Login — PROVEN BLUEPRINT (t3.chat)

> **STATUS: PROVEN WORKING** — 2026-08-18. This is the exact, verified click-through
> sequence that achieved a REAL autonomous Google SSO login on the pure Chrome
> profile (CDP 9223). Reuse this blueprint for every `NEEDS_BROWSER` provider.
> Do NOT improvise or "skip" steps — follow this exactly.

---

## 1. The Core Principle (Why This Works)

The whole point is **the AUTOMATION does the clicking** — never skip on weak
"already signed in" heuristics, never harvest cookies and claim success without
a real login. The pure Chrome profile (`d:\omniroute-pure-chrome`, Profile 14 =
`xxpertcomments@gmail.com`) is already signed into Google, so:

- No CAPTCHA / anti-bot (real fingerprint)
- Google auto-selects the remembered account → no email OTP
- Zero human handoff

The automation performs REAL clicks: Google sign-in button → account chooser →
consent → redirect back with strong auth cookies.

---

## 2. The Proven Sequence (t3.chat — VERIFIED END-TO-END)

### Step 0 — Connect to the pure Chrome profile
```python
browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=30000)
ctx = browser.contexts[0]
```

### Step 1 — Navigate to the provider login page
- t3.chat login URL: `https://t3.chat/auth/login` (redirects to `signin.t3.chat`)
- **IMPORTANT:** The Google button on t3.chat is an `<A>` anchor, NOT a `<button>`.
  Selector: `a:has-text('Continue with Google')` (href `/api/login?provider=GoogleOAuth...`)

### Step 2 — Click the Google sign-in button (REAL click)
```python
loc = page.locator("a:has-text('Continue with Google')").first
loc.click()
```
- **KEY INSIGHT:** The Google OAuth navigation happens in the **SAME page**, NOT a
  popup. Do NOT rely on `context.expect_page()` popup handling — check all pages
  in `ctx.pages` for `accounts.google.com`.

### Step 3 — Handle the Google account chooser
After clicking, the page lands on:
`https://accounts.google.com/v3/signin/accountchooser?...`
showing **"Choose an account to continue to t3.chat"** with the remembered account:
```
Kunal Das
xxpertcomments@gmail.com
```
The account is a `<DIV class='VV3oRb YZVTmd SmR8'>`. Click it via:
```python
page.locator("[data-email*='xxpertcomments']").first.click()
# fallback: page.locator("div:has-text('xxpertcomments@gmail.com')").first.click()
# fallback: page.locator("div.VV3oRb:has-text('xxpertcomments')").first.click()
```

### Step 4 — Handle the Google consent page
After selecting the account, the page lands on the consent screen:
`https://accounts.google.com/signin/oauth/consent?...`
showing **"Sign in to t3.chat"** with "Google will allow t3.chat to access this info about you".
Click **Continue**:
```python
page.locator("button:has-text('Continue')").first.click()
# fallback: button:has-text('Allow'), button:has-text('Continue as')
```

### Step 5 — Verify strong auth cookies appear
After consent, the page redirects back to t3.chat and **strong auth cookies** appear:
```
session          len=25    httpOnly=True
access-token     len=749   httpOnly=True
wos-session      len=2300  httpOnly=True
__recent_auth    len=350   httpOnly=True
```
**These are the proof of login.** Weak/anonymous cookies (convex-session-id,
t3-anon-visitor, datr, rd_challenge) are NOT proof.

---

## 3. The Driver Code (autonomous_sso_login.py)

The working driver is at `scratch/autonomous_sso_login.py`. Key functions:

| Function | Purpose |
| :--- | :--- |
| `click_google_button(page, cfg)` | REAL click on Google button (button OR anchor, with JS fallback) |
| `handle_google_account_chooser(page)` | Auto-select remembered account on accounts.google.com |
| `handle_google_consent(page)` | Click Continue/Allow on consent page |
| `login_provider(p, ctx, slug, cfg)` | Full flow: navigate → click → chooser → consent → verify |
| `strong_cookies_present(ctx, cfg)` | Check for strong auth cookies (proof of login) |

**Critical loop in `login_provider`:** after clicking the Google button, loop over
ALL pages in `ctx.pages` (not just the current page) checking for
`accounts.google.com`, and run both `handle_google_account_chooser` and
`handle_google_consent` on each. This handles both same-page navigation and popups.

---

## 4. Provider Configs (strong_cookies = proof of login)

| Provider | login_url | Google button selector | Strong auth cookies |
| :--- | :--- | :--- | :--- |
| `t3-web` | `https://t3.chat/auth/login` | `a:has-text('Continue with Google')` | `session`, `access-token`, `sessionToken`, `t3-session`, `authjs.session-token` |
| `perplexity-web` | `https://www.perplexity.ai/` (onboarding) | entry: `button:has-text('Get started')` → then Google SSO | `__Secure-next-auth.session-token`, `__Secure-perplexity_session` |
| `blackbox-web` | `https://app.blackbox.ai/login` (NOT www) | `button:has-text('GOOGLE')` | `next-auth.session-token` (NO `__Secure-` prefix) |
| `muse-spark-web` | `https://www.meta.ai` | **NO Google SSO** — only Facebook/Instagram/email | `abra_sess`/`ecto_1_sess` (needs Meta creds) |

**Verified entry points (worklog #123):**
- Perplexity: the login entry is `Get started` on the onboarding page, not a "Log in" button.
- Blackbox: `www.blackbox.ai/login` only has a link "SIGN IN TO BLACKBOX" → the real Google button is on `app.blackbox.ai/login` (`button:has-text('GOOGLE')`).
- Meta.ai: `Log in` → `auth.meta.com` offers only Facebook/Instagram/mobile-email. Google SSO is NOT available — honest blocker without Meta credentials.

---

## 5. Injection Format (per provider executor)

- **perplexity-web** (`open-sse/executors/perplexity-web.ts`): reads
  `credentials.apiKey` as a full Cookie header string (or `accessToken` as Bearer).
  Uses `buildSessionCookieHeader(cookieBlob)` which accepts bare values,
  unchunked/chunked cookie lines, or full "Cookie: ..." headers.
  Strong auth cookie: `__Secure-next-auth.session-token`.
- **t3-chat-web** (`open-sse/executors/t3-chat-web.ts`): `parseT3Credentials` reads
  `credentials.apiKey` (fallback `accessToken`) as a Cookie header string.
  Accepted forms: (a) `"convex-session-id=abc; sessionToken=xyz"`,
  (b) full Cookie header, (c) `"cookies=<header>\nconvexSessionId=<id>"`.
  Strong auth cookies: `sessionToken`, `t3-session`, `authjs.session-token`
  (NOT convex-session-id which is anonymous).

---

## 6. Anti-Confusion Rules (DO NOT repeat past mistakes)

1. **Executor source path has NO `dist` prefix:**
   `C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\open-sse\executors\`
   (NOT `dist\open-sse\executors`).
2. **Google OAuth may navigate the SAME page, not a popup.** Always scan all
   `ctx.pages` for `accounts.google.com`, not just the current page.
3. **The Google button may be an `<A>` anchor, not a `<button>`.** Use
   `a:has-text(...)` selectors too.
4. **Weak cookies ≠ login.** Only strong auth cookies prove login.
5. **The whole point is the AUTOMATION clicks.** Never skip on weak heuristics.
6. **When a button isn't found, analyze the DOM** (recon script) to find the real element.
7. **T11:** cookie/token values NEVER printed; saved only to gitignored
   `state/generated_keys.json`.

---

## 7. Verification Evidence (2026-08-18)

- Clicked `[data-email*=xxpertcomments]` on account chooser → landed on consent page.
- Clicked `button:has-text('Continue')` on consent → redirected back to t3.chat.
- Strong auth cookies appeared: `session`, `access-token`, `wos-session`, `__recent_auth`.
- **t3.chat login = COMPLETE and VERIFIED.**
