# Chrome Profile / “Sign in to Chrome” Repeated Failure — Complete RCA

**Incident status:** Root cause confirmed; local profile data preserved; Chrome Sync authentication remains unavailable without Google accepting a normal account sign-in.

**Date:** 2026-08-22  
**Scope:** `C:\Users\Admin\AppData\Local\Google\Chrome\User Data`, four profiles (`Default`, `Profile 14`, `Profile 16`, `Profile 17`), browser automation under `D:\omniroute-monetizer`, and the recovery tooling added during this incident.

## Executive conclusion

The recurring problem is not one bug. It is a chain of four failures that were repeatedly conflated:

1. Automation sometimes launched Chrome against the wrong directory. A failed junction created a fresh scaffold with empty profiles, so automation inspected or harvested from a browser that was not the operator’s real Chrome.
2. The real Chrome profile folders were later treated as “restored” when only `Local State > profile.info_cache` account labels had been repaired. That metadata controls names/account display; it does not authenticate Chrome Sync.
3. Chrome Sync / Google authentication is a separate, server-backed credential state. The screenshots prove that all four profiles still show **“Sign in to Chrome”**. Copying cookies, profile folders, or account labels cannot mint or refresh that Google session.
4. The recovery process lacked a durable, verified pre-incident snapshot and lacked a fail-closed verification gate that checked the actual Chrome UI/auth state. It therefore allowed a false success claim.

The local data is still present. The part that cannot be restored from local files alone is the Google Chrome Sync authentication session. Google’s own documentation says Chrome Sync requires signing in with a Google Account; it also says that when sync pauses after sign-out, the supported fix is to sign in again. [Google: Sign in and sync in Chrome](https://support.google.com/chrome/answer/185277), [Google: Fix issues with sync in Chrome](https://support.google.com/chrome/answer/9175737).

## What the screenshots prove

The operator supplied two Chrome profile-menu screenshots. Both show:

- a named local profile (`Kunal` or `Niloy`);
- the message **“Sign in to Chrome”**;
- a **“Sign in to Chrome”** button;
- other local profiles listed under “Other Chrome profiles.”

That is not an empty-profile problem. It is direct UI evidence that Chrome Sync authentication is not active for those profiles. A profile name appearing in the menu is not proof that the Google account session is valid.

## Ground-truth evidence collected

### Live profile root

The genuine root is:

```text
C:\Users\Admin\AppData\Local\Google\Chrome\User Data
```

The four live directories were present and non-empty:

| Profile | Cookies DB | History DB | Registry account state at final inspection |
|---|---:|---:|---|
| `Default` | 557,056 bytes | 12,058,624 bytes | `kunal.colab@gmail.com` |
| `Profile 14` | 1,507,328 bytes | 25,919,488 bytes | `xxpertcomments@gmail.com` |
| `Profile 16` | 262,144 bytes | 4,030,464 bytes | `niloydassana@gmail.com` |
| `Profile 17` | 2,195,456 bytes | 76,578,816 bytes | `isearch.xsolve@gmail.com` |

The presence of these files proves local profile data was not wiped. It does not prove that Chrome Sync is authenticated.

### Process/path evidence

The running Chrome process used the normal executable and the real default User Data root. Earlier automation runs, however, launched against `state/live_link`, which was discovered to be a real directory rather than a junction. Chrome scaffolded fresh `Default`, `Profile 14`, `Profile 16`, and `Profile 17` folders there. This explains earlier false “not signed in” observations: those probes were looking at empty profiles.

### Historical snapshot evidence

`D:\omniroute-chrome-profile-v2\Local State` contains account-registration records for all four profiles and has the same Chrome encryption-key fingerprint as the live `Local State`. That source is safe as a same-Windows-account metadata reference, but it does not contain a verified active Chrome Sync session for all four accounts.

### Cookie evidence

Earlier read-only inspection found Google PSID entries for `Default`, `Profile 16`, and `Profile 17`, but not `Profile 14`. These are website-cookie observations, not proof of Chrome Sync authentication. A Google website cookie can be absent, expired, scoped differently, or unrelated to the Chrome Sync credential.

### Backup evidence

A complete current snapshot now exists at:

```text
D:\omniroute-backups\chrome-profiles\chrome_profile_20260822_080520
```

It contains all four profiles and approximately 5.53 GiB / 46,043 files. It is a rollback snapshot of the post-incident state, not proof that the profiles were already signed into Chrome Sync.

## Timeline

1. Browser automation needed access to logged-in provider sessions.
2. A junction/link-based profile handoff was attempted.
3. The link creation silently failed; `state/live_link` became a normal directory.
4. Chrome created fresh profile scaffolding under that path.
5. Automation inspected those fresh profiles and reported login walls.
6. The real Chrome root was later found with four substantial profile directories.
7. Local State account labels were compared/repaired, and the result was incorrectly described as fully “logged in.”
8. The operator opened Chrome and supplied screenshots showing **“Sign in to Chrome”** for the profiles.
9. The distinction between local profile registration and Google Sync authentication was confirmed.
10. A full 5.53 GiB safety snapshot was finalized; no destructive restore was performed from an unproven older source.

## Five-whys analysis

### Why did Chrome repeatedly ask for sign-in?

Because the live Chrome profiles do not have an active Google Chrome Sync authentication session. Chrome Sync is account/server-backed and requires a valid Google sign-in.

### Why did copying profile files and Local State not fix it?

Because copying local profile metadata can restore profile names and account labels, but it cannot create, refresh, or validate a server-side Google authentication session. Encrypted cookies are also protected by the Windows account and may be expired or invalidated.

### Why did we initially think it was fixed?

Because local `profile.info_cache` showed the expected account emails after repair. That field was treated as a proxy for actual Chrome UI authentication, but the screenshot demonstrates those are different states.

### Why were some earlier probes inconsistent?

Because automation sometimes used a failed junction alias that pointed to a newly scaffolded empty directory instead of the real Chrome User Data root.

### Why could this recur without being caught?

Because there was no mandatory fail-closed gate requiring all of the following before success: exact root identity, verified junction type, profile byte/cookie baseline, actual profile selection, and a visual/API check of Chrome’s sign-in state. The automation also allowed a metadata-only check to stand in for authentication verification.

## Root causes

### R1 — Wrong-root / failed-junction launch (primary automation root cause)

The automation assumed `mklink /J` succeeded. It did not verify that the resulting path was a junction. Chrome then created a new directory tree. This caused false diagnostics and repeated attempts to “repair” the wrong data.

### R2 — Authentication-state conflation (primary interpretation root cause)

Three states were conflated:

| State | Meaning | Evidence available |
|---|---|---|
| Profile directory exists | Local files are present | Directory, Cookies, History, Preferences |
| Profile registry has account fields | Chrome can display a name/email label | `Local State > profile.info_cache` |
| Chrome Sync is authenticated | Google accepted a current account session | Chrome UI shows account/sync state; Google-backed session works |

Only the first two were verified. The third was incorrectly inferred.

### R3 — No valid all-four authentication source

The available snapshots are partial, older, or metadata-only for the profiles that matter. None is proven to contain a currently accepted Google Chrome Sync session for all four accounts.

### R4 — Missing fail-closed recovery acceptance test

The recovery path had file validation but no acceptance criterion such as: “Chrome profile menu must no longer show `Sign in to Chrome` for each required profile.” Without that test, a false green result was possible.

### R5 — Backup and recovery were introduced after the incident

Before this incident there was no verified full snapshot of the four real profiles. Older directories were created for automation purposes and were not guaranteed to be complete, current, or authentication-valid.

### R6 — Tooling compatibility failure weakened the first backup attempt

The backup script initially used `utf8NoBOM`, unavailable in Windows PowerShell 5.1. The copy itself completed, but finalization failed. This was fixed and the complete staging copy was finalized. It did not cause the sign-out, but it delayed the first durable backup and increased operator confusion.

## Contributing factors

- Chrome was launched by multiple automation paths with different profile roots.
- Profile names/accounts were inferred from registry JSON rather than verified through Chrome’s visible state.
- “Logged in” was used ambiguously for provider cookies, Google website cookies, Chrome profile metadata, and Chrome Sync.
- The process was optimized for credential harvesting, which increased the risk of probing a disposable automation profile instead of the operator’s profile.
- Older snapshots were not labeled with scope, account, timestamp, root identity, or authentication-verification status.
- The recovery utility’s original success language was broader than its evidence.
- The user was given a multi-mode command interface before a one-click guided launcher was added.

## What is not the root cause

- The four live profile folders were not deleted.
- The current Chrome User Data root is not the accidental `state/live_link` scaffold.
- The PowerShell PSReadLine cursor exception is a terminal-rendering problem, not Chrome authentication loss.
- The missing `sqlite3` executable prevented a database integrity check, but it did not cause the sign-out state.
- Restoring profile names or changing `Local State` account labels cannot, by itself, restore Google authentication.

## Corrective and preventive controls

### Already implemented

- Full timestamped backup of all four live profiles.
- Staged `.incomplete` backups that are not advertised as restorable.
- Windows PowerShell 5.1-compatible manifest writing.
- Explicit confirmation for destructive full restore.
- Pre-restore backup before any full restore.
- Same-encryption-key check for metadata-only registry repair.
- Junction handling changed to fail closed when an alias is a real directory.
- One-click `Chrome Profile Rescue.cmd` with plain-English menu.
- Honest separation of profile metadata repair from Chrome Sync authentication in this RCA.

### Required controls to prevent recurrence

1. **Never launch Chrome through an unverified alias.** Before launch, assert `LinkType -eq Junction` and that the resolved target equals the intended Chrome User Data root. A normal directory at the alias path must abort.
2. **Use one canonical root.** All scripts must obtain the root from one shared function; no script may invent `state/live_link`, `harvest_profile`, or another profile root without an explicit isolated-test flag.
3. **Make profile identity explicit.** Every probe/launch must record the absolute root, profile directory, account label, and a profile fingerprint before interacting with a provider.
4. **Separate status labels.** Use `LOCAL_DATA_PRESENT`, `PROFILE_METADATA_REGISTERED`, `GOOGLE_SYNC_AUTHENTICATED`, and `PROVIDER_SESSION_AUTHENTICATED`; never collapse them into `SIGNED_IN`.
5. **Require visual/UI evidence for claims.** A profile is not `GOOGLE_SYNC_AUTHENTICATED` unless Chrome’s profile UI no longer shows `Sign in to Chrome` and the expected account is visible.
6. **Back up before automation.** The one-click rescue tool should be run while Chrome is healthy; retain at least three dated snapshots and record whether each has been visually verified.
7. **Do not use provider-cookie harvesters as Chrome health checks.** Provider cookies and Google website cookies cannot certify Chrome Sync.
8. **Add a startup health check.** On each automation launch, abort with a clear message if Chrome is already running with a different root, if the target profile is missing, or if the profile UI state is not the expected state.
9. **Make backup verification periodic.** A scheduled task should verify that the latest snapshot is finalized, contains all four profile directories, contains `Local State`, and has nonzero Cookies/History databases. It must not claim authentication health.
10. **Use precise reporting.** Reports must include evidence and timestamp; “restored” is reserved for the exact acceptance criteria below.

## Definition of done for a future incident

A future recovery may be marked `MONETIZER_READY` only when all are true:

- Chrome is closed during file operations.
- The exact intended User Data root is verified.
- The target profile directory and its Cookies/History databases exist and pass integrity checks.
- A pre-restore backup is finalized and independently readable.
- The profile menu has been checked for the target profile.
- The result is labeled accurately as one of:
  - `LOCAL_DATA_PRESENT`
  - `PROFILE_METADATA_REGISTERED`
  - `GOOGLE_SYNC_AUTHENTICATED`
  - `PROVIDER_SESSION_AUTHENTICATED`
- No claim of Google authentication is made when Chrome displays `Sign in to Chrome`.

If the operator refuses normal Google authentication and Chrome displays `Sign in to Chrome`, the correct status is `MONETIZER_BLOCKED` for Chrome Sync, while local profile data can still be certified as preserved.

## Final answer to “why does it keep happening?”

It keeps happening because the system repeatedly repairs or tests **local Chrome files** while the user’s visible failure is **Google’s separate Chrome Sync authentication state**, and because earlier automation sometimes operated on a **fresh wrong profile directory**. The first problem creates false evidence; the second cannot be solved by copying files. Prevention requires both canonical-root fail-closed checks and honest authentication-state verification.

