# CHROME RULES FOR AGENTS

**Read this before you touch anything Chrome-related in this repository. It is short on purpose.**

On 2026-08-22 this project's own automation silently signed the operator out of all four of their
Google accounts, repeatedly, for an unknown number of days. They re-authenticated by hand more
than once before anyone found the cause. Then a first "fix" patched a single file and was reported
as complete — while eight more call sites were still live. Assume you are about to make the same
mistake.

Full history: `MASTER_WORKLOG.md` #1017–#1030, `CHROME_PROFILE_RCA.md`, `AGENTS.md` items 5 and 14.

---

## The one rule

**Automation never opens the operator's Chrome profile. Ever. For any reason.**

Not to read a cookie. Not to reuse a login. Not "just headless". Not "just once".

---

## Why — the mechanism, so you don't talk yourself out of it

Chrome binds a signed-in session to a specific browser instance (Device Bound Session
Credentials). When a *different* browser presents that session, Google does not error — it
**revokes the session server-side**.

So the failure is invisible and permanent:

1. Operator signs in. Everything looks fine.
2. Automation opens their profile to "reuse" the login.
3. Google kills the session.
4. Operator is logged out, blames Chrome, signs in again.
5. Automation runs again. Go to 3.

Once revoked, **no local file can bring it back.** Proven on 2026-08-22: a byte-perfect
credential pair was restored to `Profile 17` with the correct account and matching encryption
lineage. Chrome wiped it within sixty seconds because Google had already killed it. Do not spend
hours attempting local recovery. It is a dead end, and it has already been walked.

---

## What to do instead

```python
import sys
sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from chrome_live_guard import safe_profile_dir, assert_safe

udd = safe_profile_dir("my_task")       # state/automation_profiles/my_task
assert_safe(udd, who="my_task")         # belt and braces

ctx = pw.chromium.launch_persistent_context(user_data_dir=str(udd), channel="chrome")
```

The profile directory for provider work already exists: `state/automation_profiles/providers`.
**Reuse it. Do not create a fresh profile per script** — every new profile is another login the
operator has to do. The launcher that opens it is `SignInToProviders.cmd`, which goes through
`scripts/automation/provider_login_helper.py` **so the guard applies**. Launch it that way, never
by calling `chrome.exe` from a `.cmd` — a `.cmd` bypasses the guard entirely (see the coverage note
below).

Do **not** assume that profile is signed in. As of 2026-08-22 nobody has signed it in, and for the
current provider list nobody needs to — see the next section.

**If that profile hits a login wall: report the login wall.** That is a correct, complete,
professional result. It is not a failure to route around. Say which provider, which URL, and what
the page asked for, then stop. The operator would far rather sign in once than be silently logged
out forever.

### Before you reach for a browser at all

**First check what is already done.** On 2026-08-22 an agent (me) was one step away from handing the
operator a launcher telling them to sign in to seven sites and collect API keys — when four of those
keys were already collected and provider-verified. Do not repeat that. Run these two, in this order:

```bash
python scripts/automation/paste_provider_key.py --status   # which keys exist and verify
python scripts/automation/paste_provider_key.py --list     # which sites still need a human
```

**There are two paste tools with near-anagram names. Read this before editing either.**

| File | Launcher | Lines | Wires into OmniRoute | `--list` means |
|---|---|---|---|---|
| `scripts/automation/paste_provider_key.py` | `WireKeyFromClipboard.cmd` | 686 | **yes** | "print the sites to visit" |
| `scripts/automation/provider_key_paste.py` | `PasteAKey.cmd` | 395 | no | "show saved keys, redacted" |

`paste_provider_key.py` is the superset — clipboard mode, `--status`, `--reverify`, `--only`, and the
only one that sets the key on the OmniRoute connection. **Prefer it.** Both write to the same
`state/generated_keys.json`, so they do not corrupt each other, but the same flag means opposite
things in each, and patching one leaves the other live. That pattern already caused one false "fixed"
report in this repo. Consolidating them is unfinished work.

Measured on 2026-08-22: `kie`, `segmind`, `novita`, `aistudio` all **VERIFIED** (the provider's own
endpoint answered HTTP 200); `kie`, `segmind`, `novita` are **wired and active** in OmniRoute.
Only `leonardo` has no key, and `--list` marks it SKIP — its API is behind a paid plan the operator
hit on 2026-08-22, for 1 model. `runwayml`, `haiper` and `deepinfra` are also on the documented skip
list. So the "six blocking providers" framing is out of date; do not resurrect it.

**`state/all_296_providers_execution_ledger.json` is a stale snapshot, not current state.** The
`evidence` fields are stamped `upstream-scan 2026-08-18` — four days before the keys were collected.
It still reports `EXTERNAL_ACCOUNT_REQUIRED` and `in_db_connections=0` for providers that are now
live in OmniRoute. Believe OmniRoute and `--status` over the ledger, and say which one you checked.

The auth class lives inside `details.blocker` as a substring (`authClass=apikey`), **not** as a
top-level `authClass` field — querying the top level returns `None` and will mislead you.

These providers need an **API key in the vault**, not a browser session. A browser is only the means
for a *human* to reach the dashboard once and copy the key. Novita is a separate case: its
credential is verified and it returns `403 NOT_ENOUGH_BALANCE` — a **credit** problem, not a login
problem, and no amount of automation fixes it.

Reaching for browser automation when an API key would do is how this project ended up touching
the operator's Chrome in the first place.

**Reading a key back out of OmniRoute proves nothing about *which* key is set.** The management API
returns a mask, shape `XX-XX-X.****XXXX`, a uniform 16 characters for every connection. `keyPresent`
and `isActive` are all you can honestly conclude from it. To prove the key works, call the
provider's endpoint (`--reverify`) or run an end-to-end job.

---

## Traps that have already caught someone here

| Trap | Reality |
|---|---|
| `os.path.islink()` to detect an alias | Returns **False** for a Windows junction. This is exactly how the bug hid. Use `os.path.realpath()`. |
| `shutil.rmtree()` on a suspicious link | Deletes **through** the junction into the real profile. Use `os.rmdir()` — it removes only the link. |
| Checking profile health by file size | SQLite never reclaims pages. A bulk `DELETE` leaves the file the same size. Count rows and check `PRAGMA freelist_count`. |
| Trusting `Local State > profile.info_cache` | That is a **display label**. Chrome wipes it if no credential backs it. A profile can show the right name and email while being fully signed out. |
| "The profile folder exists, so it's fine" | Five different states get conflated. See below. |
| Assuming `mklink /J` succeeded | It can fail silently; Chrome then scaffolds empty profiles at the alias path and every later probe reads the wrong data. |
| Patching the one file you found | There were nine. Sweep the whole repo. |
| `sitecustomize.py` in the repo root | **Does not load.** cwd is not on `sys.path` when `site` runs. Tested and discarded. Use a `.pth` in site-packages. |

---

## Never conflate these five states

Name the one you actually verified. Vague "signed in" is banned.

1. `LOCAL_DATA_PRESENT` — the profile directory exists on disk
2. `PROFILE_METADATA_REGISTERED` — `Local State` lists it with a name and email (a **label only**)
3. `GOOGLE_SYNC_AUTHENTICATED` — `Web Data > token_service` has rows **AND** `Preferences >
   account_info` has the matching account **AND** Chrome's own UI shows "Sign out of Chrome"
4. `PROVIDER_SESSION_AUTHENTICATED` — the specific website (Leonardo, Runway, …) is logged in
5. `MONETIZER_READY` / `MONETIZER_BLOCKED` — the actual business outcome

The Chrome sync credential is **two paired artifacts**: `Web Data > token_service` (the
OS-encrypted refresh token) and `Preferences > account_info`. Both, or neither — Chrome clears one
if the other is missing. Never edit either by hand. Never edit a Chrome SQLite database to fake a
session.

---

## The guard, and why you must not disable it

`scripts/automation/chrome_live_guard.py` refuses any path that **is**, is **inside**, or
**contains** `%LOCALAPPDATA%\Google\Chrome\User Data`, resolving junctions first. It also refuses
**attaching** to a browser running on that tree.

It is armed automatically by two files in each relevant interpreter's `site-packages`:

- `chrome_live_guard.pth`
- `chrome_live_guard_boot.py`

Installed in **both** interpreters on this machine, because getting this wrong is silent:

| Interpreter | Has Playwright | Armed |
|---|---|---|
| `C:\Users\Admin\AppData\Local\hermes\hermes-agent\venv` (the `python` on PATH) | yes | yes |
| `D:\omniroute-monetizer\.venv` (the project venv) | yes | yes — **added 2026-08-22** |

The project venv was **unarmed until 2026-08-22** while the hermes venv was armed. Since the
project venv is the one a script in this repo naturally runs under, the global net had a hole in
exactly the place it mattered. If you add a third venv, copy those two files into it, then prove
it with the checks below. Do not assume.

It patches Playwright's `launch_persistent_context`, `launch`, `connect_over_cdp`, and
`subprocess.Popen/run/call/check_call/check_output`. Refused shapes, each individually tested from
a script that never imports the guard:

- `launch_persistent_context(user_data_dir=<live>)`
- `launch_persistent_context(<live>\Profile 17)`
- `launch(args=["--user-data-dir=<live>"])`
- `chrome.exe --user-data-dir=<live> --remote-debugging-port=9222`
- `cmd /c mklink /J <alias> <live>`
- `chrome.exe <live>` as a bare argument
- `connect_over_cdp("http://127.0.0.1:<port>")` where `<port>` is advertised by
  `DevToolsActivePort` inside the live tree — matched as `http://`, `ws://`, `localhost`, and bare
  `host:port`

**If you hit `LiveProfileRefused`, the guard is right and your code is wrong.** Fix the profile
path. Do not delete those two files, do not add a bypass flag, do not catch and continue.

`install()` returns True when the guard is active on Playwright — **including when another copy of
the module already patched it**. Before 2026-08-22 it returned False in that case and printed
"playwright not installed", which was flatly untrue and could have led an agent to "repair" a
working guard. If you see that message now, Playwright genuinely is not importable.

Not covered, so stay disciplined: `.cmd` files, Node scripts, and any Python interpreter without
the `.pth`.

### The attach vector, since it will occur to you

`connect_over_cdp` against a Chrome the operator started themselves is a *different door into the
same room*, and this repo used to contain two files built for it. Both are now retired with a
loud refusal and a full explanation: `get_chrome_ws.py`,
`process_providers_with_existing_chrome.py`. The ledger logic in the second is worth porting —
port it to automation's own profile, not to theirs.

Be accurate about the risk, because overstating it gets it dismissed. Attaching does **not**
reproduce the 2026-08-22 revocation; that needed a *foreign* browser presenting the session, and
here the browser is the operator's own Chrome. It is refused for three other reasons:

1. **Chrome already blocks it.** From Chrome 136, `--remote-debugging-port` and
   `--remote-debugging-pipe` are ignored when they target the default user-data directory
   ([developer.chrome.com/blog/remote-debugging-port](https://developer.chrome.com/blog/remote-debugging-port)).
   This machine runs Chrome 151, so it cannot work. The tempting workaround — a junction whose
   path string looks non-default — is precisely the original bug.
2. An open DevTools port has **no authentication**. Any local process could read every cookie in
   every profile. That is why Google clamped down.
3. Automated activity on a genuinely signed-in account risks a flag on the **account**, not just
   the session. A session you can re-create; an account you may not.

---

## Before and after any Chrome-adjacent work

```bash
python scripts/automation/chrome_selfheal.py --dry-run
```

Or hand the operator `Fix Chrome.cmd` — one double-click, safe any time, read-only with respect to
Chrome. It removes stray aliases, proves the guard is actively refusing, reports per-profile
sign-in state, and backs up when Chrome is closed. Output is tagged `[ok]` / `[FIXED]` / `[YOU]` /
`[PROBLEM]` so the operator knows who owns each line.

Related tools: `chrome_auth_audit.py` (read-only detector), `chrome_session_restore.py` (targeted,
gated, reversible — remember it cannot beat a server-side revocation), `Chrome Health Check.cmd`.

---

## Reporting standards for this operator

They are not a programmer, they are under real financial pressure, and they have been told
"restored" three times when it was not. Because of that:

- **Plain language. Short sentences.** No jargon. If you must name a file, say what to do with it.
- **Never say "restored", "fixed", or "signed in" without naming the state you verified and how.**
- Prefer one double-click file over a list of commands.
- Log every action to `MASTER_WORKLOG.md` with a timestamp, the exact observation, the command and
  its result, what changed, and whether it is **verified** or **blocked**. Never a password, token,
  or cookie value.
- Add an explicit **"what is NOT claimed"** section. It is the most useful part of every entry.
- If you were wrong earlier, correct the record in the worklog. #1025, #1026 and #1030 all correct
  earlier entries. That is the standard, not an embarrassment.
- Verify against documentation or measurement before asserting. When this operator says "check the
  internet and confirm", they are right to.
- Their account labels: `Default` → kunal.colab@gmail.com, `Profile 14` → xxpertcomments@gmail.com,
  `Profile 16` → niloydassana@gmail.com, `Profile 17` → isearch.xsolve@gmail.com. Keep this in sync
  with `EXPECTED_ACCOUNTS` in `chrome_auth_audit.py` and `EXPECTED` in `chrome_selfheal.py`.

## Hardware facts about this machine, so they are not re-litigated

Lenovo 2349A11 (ThinkPad T430 family), Windows 10 Pro build 19045.

- **No Bluetooth adapter.** Not disabled — absent. Cross-device phone passkeys (the QR flow)
  require Bluetooth Low Energy on the client, so that route is blocked by hardware. A USB cable is
  **not** a substitute; Google's documentation lists Bluetooth, or a separate FIDO2 security key.
- **No TPM, no fingerprint reader.** A Windows Hello platform passkey is doubtful here.
- Passwords are fine regardless: Google Password Manager syncs them down (28 / 19 / 1 / 554 rows
  observed on 2026-08-22), so autofill covers provider sign-ins.
