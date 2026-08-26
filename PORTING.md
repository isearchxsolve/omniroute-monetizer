# PORTING — move this rig to a new machine

Step-wise. Run the steps in order; each one has a check you can see the result of. Written
2026-08-26 against `omni_portable.py`, `omni_supervisor.py`, `install_autostart.py` as they exist.

## Read this first, or step 6 will waste an hour

Almost none of the value is the code. The code is ~200 Python files that `pip install` and run
anywhere. The value is the **captured supply**, and it splits hard:

| | what | why |
|---|---|---|
| **Portable** | `state/secrets/session_*.json` | a recorded HTTP exchange + a cookie header, plain JSON. Nothing in it is bound to this machine. |
| **Portable** | `state/replay_check.json` | which of those actually replay |
| **Portable** | `scripts/automation/*.json` | client / inference configs |
| **Portable** | the git repo | obviously |
| **NOT portable** | `state/omniroute_password.bin` | DPAPI-sealed to this Windows user on this machine. Elsewhere it decrypts to nothing. |
| **NOT portable** | `state/automation_profiles/**` | Chrome seals its cookie key with DPAPI too. A copied profile has a `Cookies` DB it cannot read: every file present, every login gone. |

**Never copy `state/automation_profiles/`.** Beyond not working, Google's Device Bound Session
Credentials can read the move as a compromise and revoke the account permanently — that happened
on 2026-08-22 and cost a live Google session. Copying it is worse than skipping it, because a
broken restore looks like a working one.

So the honest expectation: **chat supply ports as files. Video seats must be signed in by hand
on the new machine.** There is no way around step 6.

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
Check the printed manifest lists your `session_*.json` count (28 as of this writing).

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

### 8. Re-sign-in the video seats (human, unavoidable, the long one)

Video supply needs a signed-in Chrome per seat. Order matters:

1. Launch Chrome **without** CDP and sign in normally. Google **refuses sign-in on a
   CDP-enabled Chrome**, so this must come first.
2. Close Chrome fully.
3. Relaunch with CDP using **all three** of these, or it silently fails:
   - `--profile-directory=<sub>` — always pin it explicitly
   - `--remote-allow-origins=*`
   - process creation flags `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` — `DETACHED_PROCESS`
     alone dies with the parent
4. Confirm the tab is reachable: `http://127.0.0.1:9222/json/list` should list your pages.

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

## Two failure modes that look like success

1. **Copied Chrome profile.** Every file present, every login gone, and possibly a permanently
   revoked Google account. If you skipped step 8 because the profiles "came across", you have
   this. Delete them and do step 8.
2. **A video seat that accepts jobs and never delivers.** A recorded capture whose *result*
   exchange was never observed will replay a submit, get a job id, and then have nothing to poll
   for. Captures in `state/captures_pending/` are marked `replayable: false` for exactly this
   reason — never hand-copy one into `state/secrets/` to raise the capacity number.
