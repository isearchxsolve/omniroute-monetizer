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

**If that profile hits a login wall: report the login wall.** That is a correct, complete,
professional result. It is not a failure to route around. Say which provider, which URL, and what
the page asked for, then stop. The operator would far rather sign in once than be silently logged
out forever.

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
**contains** `%LOCALAPPDATA%\Google\Chrome\User Data`, resolving junctions first.

It is armed automatically for every Python process on this machine by two files in the hermes
venv's `site-packages`:

- `chrome_live_guard.pth`
- `chrome_live_guard_boot.py`

It patches Playwright's `launch_persistent_context` / `launch`, and
`subprocess.Popen/run/call/check_call/check_output`. Refused shapes, all individually tested:

- `launch_persistent_context(user_data_dir=<live>)`
- the same through a junction alias
- `mklink /J <alias> <live>`
- `chrome.exe --user-data-dir=<live>`
- `chrome.exe <live>` as a bare argument

**If you hit `LiveProfileRefused`, the guard is right and your code is wrong.** Fix the profile
path. Do not delete those two files, do not add a bypass flag, do not catch and continue.

Not covered, so stay disciplined: `.cmd` files, Node scripts, and any Python interpreter without
the `.pth`.

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
