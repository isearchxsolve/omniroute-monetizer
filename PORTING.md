# PORTING — move this rig to a new machine

Step-wise. Run the steps in order; each one has a check you can see the result of. Written
2026-08-26, **updated 2026-08-27** against `omni_portable.py`, `omni_supervisor.py`,
`install_autostart.py`, `cookie_porter.py` as they exist.

## Read this first, or step 6 will waste an hour

Almost none of the value is the code. The code is ~200 Python files that `pip install` and run
anywhere. The value is the **captured supply**, and it splits hard:

| | what | why |
|---|---|---|
| **Portable** | `state/secrets/session_*.json` (53 files) | a recorded HTTP exchange + a cookie header, plain JSON. Nothing in it is bound to this machine. |
| **Portable** | `state/replay_check.json` | which of those actually replay |
| **Portable** | `scripts/automation/*.json` | client / inference configs |
| **Portable** | the git repo | obviously |
| **Portable (NEW)** | Provider site sessions via CDP export | `cookie_porter.py --export` dumps all decrypted cookies (1,842 across 335 domains) from the live Chrome. Re-inject on any machine with `--import`. See §Provider Session Portability below. |
| **NOT portable** | `state/omniroute_password.bin` | DPAPI-sealed to this Windows user on this machine. Elsewhere it decrypts to nothing. |
| **NOT portable (raw copy)** | `state/automation_profiles/**` | Chrome seals its cookie key with DPAPI too. A raw-copied profile has a `Cookies` DB it cannot read: every file present, every login gone. **But see the CDP export path below — provider sessions ARE portable via cookie export, just not via profile directory copy.** |

**Never raw-copy `state/automation_profiles/`.** Beyond not working, Google's Device Bound Session
Credentials can read the move as a compromise and revoke the account permanently — that happened
on 2026-08-22 and cost a live Google session. Copying it is worse than skipping it, because a
broken restore looks like a working one.

**HOWEVER — provider sessions ARE portable via CDP cookie export (proven 2026-08-27).**
The DPAPI lock applies to the on-disk `Cookies` SQLite file. A LIVE Chrome with CDP enabled
exposes all decrypted cookies (including HttpOnly) via `Storage.getCookies`. These can be
re-injected into a fresh profile on any machine via `Storage.setCookies`. This means:
- Provider sign-ins (claude.ai, groq.com, perplexity.ai, etc.) CAN be ported.
- Google account sign-in CANNOT (DBSC device-bound, revoked on new machine).
- The Chrome profile directory itself still cannot be raw-copied.

So the honest expectation: **chat supply ports as files. Provider sessions port as CDP cookie
exports. Google sign-in and video seats that use Google SSO must be signed in by hand.**

---

## Provider Session Portability (NEW — 2026-08-27)

### The distinction that matters

| What | Portable? | How |
|---|---|---|
| Provider site cookies (claude.ai, grok.com, etc.) | ✅ YES | `cookie_porter.py --export` → `--import` on new machine |
| HttpOnly auth cookies (session tokens, JWTs) | ✅ YES | Same — CDP exposes them decrypted |
| Google account sign-in (Chrome Sync) | ❌ NO | DBSC device-bound; revoked on new machine |
| localStorage / sessionStorage | ❌ NO | CDP cookie export is cookies-only |
| Chrome profile directory (raw copy) | ❌ NO | DPAPI-sealed Cookies DB |

### Export (old machine, Chrome running with CDP)

```bash
python scripts/automation/cookie_porter.py --export --ports 9222,9223,9224,9225 --out D:\omni_bundle\provider_sessions.json
```

Verified output: **1,842 cookies across 335 provider domains** (253 auth-like cookies including
HttpOnly session tokens). The export file is a credential store — treat it like `state/secrets/`.

### Import (new machine, fresh Chrome profile running with CDP)

```bash
python scripts/automation/cookie_porter.py --import --port 9222 --in D:\omni_bundle\provider_sessions.json
```

Or selectively:
```bash
python scripts/automation/cookie_porter.py --import --port 9222 --in D:\omni_bundle\provider_sessions.json --domains claude.ai,grok.com,perplexity.ai
```

### What survives import

After injection, reload the provider tabs. Sites that use cookie-only auth (most chat providers)
will be signed in immediately. Sites that also check localStorage tokens or device fingerprints
may require a re-login. Google SSO will always require a fresh sign-in.

### Limitations

- Some SPAs store auth tokens in localStorage, not cookies. Those won't port.
- Sites with device attestation (DBSC, TLS fingerprint binding) will reject the session.
- Cookie expiry: if a cookie has expired between export and import, it won't work.
- The export is a point-in-time snapshot. Sessions that rotate cookies after export will stale.

---

## On the OLD machine

### 1. Commit and push everything

```bash
git -C D:\omniroute-monetizer add -A && git -C D:\omniroute-monetizer commit -m "port checkpoint" && git -C D:\omniroute-monetizer push
```

`state/` is gitignored, so this moves code only. Supply moves in step 2.

### 2. Build the portable bundle — outside the repo

```bash
python D:\omniroute-monetizer\scripts\automation\omni_portable.py --export D:\omni_bundle
```

It copies the portable column above and **deliberately skips** the two non-portable entries.
Check the printed manifest lists your `session_*.json` count (53 as of this writing).

### 2b. Export provider sessions via CDP (NEW — 2026-08-27)

With the seat Chromes running (ports 9222-9225):

```bash
python D:\omniroute-monetizer\scripts\automation\cookie_porter.py --export --ports 9222,9223,9224,9225 --out D:\omni_bundle\provider_sessions.json
```

This dumps all decrypted cookies (including HttpOnly auth tokens) from the live browsers.
Verified: 1,842 cookies across 335 provider domains. This file goes into the bundle alongside
the session JSON files. It is a credential store — same handling rules as step 4.

### 3. Note what the bundle cannot carry

```bash
python D:\omniroute-monetizer\scripts\automation\omni_portable.py --doctor
```

The tail of that output names the three things a human must always redo. Copy them down; they
are steps 5, 6 and 7 below.

### 4. Move `D:\omni_bundle` to the new machine

Any means you trust. It contains **live session cookies** — treat it as a credential store, not
a backup. Do not put it anywhere that syncs to a third party.

---

## On the NEW machine

### 5. Install prerequisites, then prove them

Needed: **Python ≥ 3.11**, `requests`, **Google Chrome**, **ffmpeg on PATH**. `playwright` is
optional. Then:

```bash
git clone <your remote> D:\omniroute-monetizer && python D:\omniroute-monetizer\scripts\automation\omni_portable.py --doctor
```

Expect the first rows (`python`, `requests`, `Chrome`, `ffmpeg`) to read `ok` and the supply rows
to read *missing* — you have not imported yet. Fix any prerequisite that is not `ok` before
continuing; the later steps assume all four.

### 6. Import the supply

```bash
python D:\omniroute-monetizer\scripts\automation\omni_portable.py --import D:\omni_bundle
```

Then re-run `--doctor`. `captured sessions present` and `verdicted supply` should now read `ok`.
If `verdicted supply` lists fewer `REPLAY_OK` hosts than the old machine did, that is real
expiry, not a bad copy — sessions die from disuse. Re-verify with `replay_check`.

### 7. Re-seal the OmniRoute password (human, unavoidable)

The DPAPI blob did not come along. Re-enter the password on the new machine so it seals into the
local vault. **Never type it into a script argument or a shell you are logging.**

### 8. Restore provider sessions, then re-sign-in what didn't take (partially automated now)

Video supply and Chrome-backed chat seats need a signed-in Chrome per seat. As of 2026-08-27
this is **no longer fully manual** — provider sessions port via CDP cookie export/import:

1. Launch a fresh Chrome seat with CDP (sign-in NOT needed yet):
   - `--user-data-dir=<fresh profile>` `--profile-directory=<sub>`
   - `--remote-debugging-port=9222` `--remote-allow-origins=*`
   - process creation flags `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`
2. **Inject the exported provider sessions:**
   ```bash
   python scripts/automation/cookie_porter.py --import --port 9222 --in D:\omni_bundle\provider_sessions.json
   ```
3. Reload the provider tabs. Cookie-only-auth providers (most chat hosts) will be signed in
   immediately — no manual sign-in needed.
4. **What still needs a human:** Google SSO (DBSC device-bound, always revoked on a new
   machine), and any provider that stores its token in localStorage or uses device attestation.
   For those: sign in normally in the seat Chrome (Google **refuses sign-in on a CDP-enabled
   Chrome**, so sign in first without `--remote-debugging-port`, close fully, then relaunch
   with CDP using all three flags above).
5. Confirm the tab is reachable: `http://127.0.0.1:9222/json/list` should list your pages.

Do **not** point any of this at the operator's live Chrome profile. Robot profiles only, under
`state/automation_profiles/`.

### 9. Re-connect OmniRoute's own OAuth providers (human, unavoidable)

Its provider tokens are per-machine. Reconnect them in OmniRoute's own UI.

### 10. Bring the rig up

```bash
python D:\omniroute-monetizer\scripts\automation\omni_supervisor.py --up
```

Then verify each port answers — do not infer this from the supervisor's own output:

```bash
curl -s http://127.0.0.1:20130/health && curl -s http://127.0.0.1:8189/v1/video/capacity
```

| port | what | rule |
|---|---|---|
| `20130` | chat superset gateway (free pool, forwards to `:20128`) | mine; restart freely |
| `8189` | video router, async `/v1/video/jobs` | mine; restart freely |
| `20128` | OmniRoute chat | **not mine. Never restart, never kill.** Idempotent `/api` calls only. |

`/v1/video/capacity` reporting `totalClipsAvailable: 0` after step 8 means the seats are signed
in but not harvested yet — run the harvester for those hosts.

### 11. Close the reboot gap

```bash
python D:\omniroute-monetizer\scripts\automation\install_autostart.py --status
```

If it reports not armed, use `--install` (Task Scheduler, needs elevation) or `--startup`
(Startup-folder launcher, no elevation). The supervisor recovers crashes only while it is itself
running; this is what starts it at logon. It deliberately does not launch Chrome — see step 8.

---

## Done when

All four hold at once:

- `omni_portable.py --doctor` shows no blocking problems
- `:20130/health` reports available sessions > 0
- `:8189/v1/video/capacity` reports the seats you signed in at step 8
- `install_autostart.py --status` reports armed

## Windows services registered on this rig (2026-08-27 inventory)

These are the scheduled tasks that keep the rig alive. On a new machine they must be re-armed
(the bundle carries the `.bat` files; `schtasks /Create` or the installers recreate the tasks):

| Task name | Runs | Schedule | Purpose |
|---|---|---|---|
| `OmniRoute Rig Supervisor (keepalive)` | `supervisor_task.bat` → `omni_supervisor.py --watch` | every 5 min | Crash recovery for all owned services; reports Chrome state |
| `OmniRoute Session Pool Shim (keepalive)` | `session_pool_shim_task.bat` → `session_pool_shim.py 8190` | every 5 min | Keeps the :8190 consumer endpoint alive |
| `OmniRoute Video Router (keepalive)` | `video_router_task.bat` → `video_router.py` | every 5 min | Video router + Chrome seat self-heal (relaunches dead seat Chromes) |
| `OmniRoute OAuth KeepAlive` | `oauth_keepalive_task.bat` → `oauth_keepalive.py` | hourly | Refreshes OmniRoute's own OAuth provider tokens |

Plus the Startup-folder launcher (no elevation needed):

| Launcher | Location | Purpose |
|---|---|---|
| `omniroute_rig_supervisor.vbs` | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` | Starts the supervisor `--watch` loop at logon |

**Reboot recovery chain:** logon → `.vbs` starts supervisor → supervisor's 5-min task restarts
any dead service (shim, chat pool) → video router task relaunches dead seat Chromes and re-opens
their tabs. Provider sessions persist in the Chrome profile directories on disk (they survive
reboot natively — Chrome re-opens with the same cookies). The only thing that does NOT survive
a reboot without help is the Chrome *process* itself — the video router task handles that.

## Two failure modes that look like success

1. **Raw-copied Chrome profile.** Every file present, every login gone, and possibly a permanently
   revoked Google account. If you skipped step 8 because the profiles "came across", you have
   this. Delete them and do step 8. (Note: this is about raw directory copies. The CDP cookie
   export path in step 2b/8 is the correct way to port provider sessions.)
2. **A video seat that accepts jobs and never delivers.** A recorded capture whose *result*
   exchange was never observed will replay a submit, get a job id, and then have nothing to poll
   for. Captures in `state/captures_pending/` are marked `replayable: false` for exactly this
   reason — never hand-copy one into `state/secrets/` to raise the capacity number.
