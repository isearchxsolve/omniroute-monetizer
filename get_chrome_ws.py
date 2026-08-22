"""RETIRED 2026-08-22. Do not revive this. Read the whole docstring before you try.

WHAT IT USED TO DO
------------------
Read `DevToolsActivePort` out of the operator's LIVE Chrome user-data directory, then hand back
a WebSocket URL so automation could attach to the operator's own browser over CDP and reuse
their logged-in sessions.

WHY IT IS RETIRED -- THREE INDEPENDENT REASONS
---------------------------------------------
1. **It cannot work.** From Chrome 136 onward, `--remote-debugging-port` and
   `--remote-debugging-pipe` are IGNORED when they target the default user-data directory
   (developer.chrome.com/blog/remote-debugging-port). Google made that change precisely because
   attackers were using CDP to lift cookies. This machine runs Chrome 151, so
   `DevToolsActivePort` will not be there to read.

2. **It is an attractive nuisance.** The filename promises exactly what a future agent wants
   when it hits a login wall. It fails, the agent notices Chrome's non-default-directory rule,
   and the obvious workaround is to point Chrome at a junction that resolves back to the live
   tree -- which is bit-for-bit the 2026-08-22 incident that revoked the operator's Google
   sessions on all four profiles, repeatedly, for days. See MASTER_WORKLOG.md #1026.

3. **Even working, it is the wrong trade.** An open DevTools port has no authentication: any
   process on this machine could read every cookie in every profile. And automated activity on
   a genuinely signed-in account risks a flag on the ACCOUNT, which is worse than a revoked
   session -- a session you can re-create, an account you may not.

   To be fair to the idea, since a future agent will reason about this: attaching to the
   operator's own Chrome would NOT reproduce the 2026-08-22 revocation. That needed a foreign
   browser presenting the session. The reasons above are sufficient on their own.

WHAT TO DO INSTEAD
------------------
Give automation its own Chrome, its own profile, and its own debugging port:

    import sys
    sys.path.insert(0, r"D:\\omniroute-monetizer\\scripts\\automation")
    from chrome_live_guard import safe_profile_dir
    udd = safe_profile_dir("providers")   # state/automation_profiles/providers

The operator signs that profile in ONCE, by hand, via `SignInToProviders.cmd` (which runs
`scripts/automation/provider_login_helper.py`, so the guard applies). Note that as of 2026-08-22 it
has NOT been signed in and does not need to be: the remaining providers are `authClass=apikey` and
their keys are already collected and verified. Check
`paste_provider_key.py --status` before assuming a browser is needed at all.

If automation's own profile hits a login wall: **report the login wall.** Say which provider,
which URL, and what the page asked for, then stop. That is a correct, complete result -- not a
failure to route around. The operator would far rather sign in once than be silently logged out
forever.

See CHROME_RULES_FOR_AGENTS.md, AGENTS.md items 5 and 14, MASTER_WORKLOG.md #1026 and #1032.
"""

_REFUSAL = (
    "REFUSED: get_chrome_ws.py is permanently retired.\n"
    "\n"
    "It read DevToolsActivePort from the operator's LIVE Chrome profile so automation could\n"
    "attach to their browser over CDP. Three reasons it is gone:\n"
    "  1. Chrome 136+ ignores --remote-debugging-port for the default profile directory, so\n"
    "     this cannot work at all on Chrome 151.\n"
    "  2. Working around that with a junction is exactly the 2026-08-22 bug that revoked the\n"
    "     operator's Google sessions on all four profiles for days.\n"
    "  3. An open DevTools port is unauthenticated -- it exposes every cookie in every profile.\n"
    "\n"
    "Do this instead:\n"
    "    from chrome_live_guard import safe_profile_dir\n"
    "    udd = safe_profile_dir('providers')\n"
    "The operator signs that profile in once. If it hits a login wall, REPORT the login wall.\n"
    "\n"
    "See CHROME_RULES_FOR_AGENTS.md and MASTER_WORKLOG.md #1032."
)


def get_chrome_ws_url():
    """Always raises. Kept so any existing caller fails loudly with an explanation."""
    raise RuntimeError(_REFUSAL)


if __name__ == "__main__":
    import sys

    print(_REFUSAL, file=sys.stderr)
    sys.exit(2)
