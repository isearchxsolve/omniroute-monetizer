"""
chrome_live_guard.py -- ONE JOB, AND IT NEVER NEGOTIATES.

Make it structurally impossible for automation in this repository to open, write to,
or scaffold inside the operator's LIVE Chrome profile.

WHY THIS FILE EXISTS
--------------------
2026-08-22 incident. `video_key_harvester.py` created a junction to
`%LOCALAPPDATA%\\Google\\Chrome\\User Data` and drove a Playwright persistent context
through it. Chrome binds a signed-in session to a specific browser instance (Device Bound
Session Credentials). A foreign Chromium presenting that session causes Google to REVOKE it
server-side. The operator signed in; automation ran; the session died. Forever, in a loop.

The first repair patched only the harvester. A later sweep found EIGHT more call sites
pointing at the live root. Per-file patches do not hold, because the next script written
will not remember. So the rule now lives in one place and is enforced two ways:

  1. Explicitly  -- offending modules call `assert_safe()` before launching.
  2. Globally    -- `install()` monkey-patches Playwright itself, so ANY code in this repo
                    (including code not yet written) is refused at the launch boundary.

HARD RULES
----------
* Automation gets its OWN profile directory. Always.
* A login wall in automation's own profile is a CORRECT, REPORTABLE outcome. Report it.
  Do not reach for the operator's browser to get around it.
* Read-only forensic probing of a *temp copy* of a Chrome file is allowed and is NOT
  affected by this guard. Launching a browser against the live tree is not.

See AGENTS.md items 5 and 14, and MASTER_WORKLOG.md #1026 / #1030.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "LiveProfileRefused",
    "LIVE_ROOT",
    "resolve",
    "verdict",
    "is_live",
    "assert_safe",
    "install",
    "safe_profile_dir",
]


class LiveProfileRefused(RuntimeError):
    """Raised when something tries to point a browser at the operator's real Chrome."""


def _live_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.environ.get("USERPROFILE", r"C:\Users\Admin"), "AppData", "Local"
    )
    return Path(base) / "Google" / "Chrome" / "User Data"


#: The one canonical live root. Derived from the environment, never hardcoded as a D:\ path.
LIVE_ROOT: Path = _live_root()


def resolve(path) -> Path:
    """Fully resolve a path, following Windows junctions and symlinks.

    Junctions are the whole reason this exists: `state\\live_link` looked innocent and was
    not. `os.path.islink()` returns False for a junction, so we resolve instead of testing.
    Never raises -- an unresolvable path is returned normalised so callers can still compare.
    """
    try:
        return Path(os.path.realpath(str(path)))
    except (OSError, ValueError):
        return Path(os.path.abspath(str(path)))


def verdict(path) -> tuple[bool, str]:
    """Return (refused, human_readable_reason) for a candidate user-data directory."""
    target = resolve(path)
    live = resolve(LIVE_ROOT)

    if target == live:
        return True, "it IS the operator's live Chrome user-data root"
    if live in target.parents:
        return True, "it is INSIDE the operator's live Chrome user-data root"
    if target in live.parents:
        return True, "it CONTAINS the operator's live Chrome user-data root"
    return False, "outside the live Chrome tree"


def is_live(path) -> bool:
    """True if this path must not be opened by automation."""
    return verdict(path)[0]


def assert_safe(path, who: str = "automation") -> Path:
    """Return the resolved path, or raise LiveProfileRefused with a full explanation."""
    refused, reason = verdict(path)
    if not refused:
        return resolve(path)

    raise LiveProfileRefused(
        "REFUSED: {who} tried to open the operator's LIVE Chrome profile.\n"
        "    requested   : {req}\n"
        "    resolves to : {res}\n"
        "    live root   : {live}\n"
        "    reason      : {reason}\n"
        "\n"
        "This is permanently disabled. It is what caused the 2026-08-22 incident:\n"
        "Google revokes a Chrome session when a foreign browser presents it, so every\n"
        "automation run silently logged the operator out of all four accounts.\n"
        "\n"
        "Do this instead:\n"
        "  * give automation its own profile directory (see safe_profile_dir()), and\n"
        "  * if that profile hits a login wall, REPORT the login wall. That is a valid\n"
        "    result, not a failure to route around.\n"
        "\n"
        "See AGENTS.md 5 and 14.1, MASTER_WORKLOG.md #1026.".format(
            who=who, req=path, res=resolve(path), live=resolve(LIVE_ROOT), reason=reason
        )
    )


def safe_profile_dir(tag: str = "automation") -> Path:
    """A dedicated, writable profile directory for automation. Created if absent.

    Lives under the project's own `state/` tree, never under the operator's Chrome.
    """
    project_root = Path(__file__).resolve().parents[2]
    safe = project_root / "state" / "automation_profiles" / tag
    safe.mkdir(parents=True, exist_ok=True)
    assert_safe(safe, who="safe_profile_dir")  # paranoia: catch a junction placed under state/
    return safe


# --------------------------------------------------------------------------------------
# Global enforcement: wrap Playwright so no call site can forget.
# --------------------------------------------------------------------------------------

_INSTALLED = False


def _scan_launch_args(args, who: str) -> None:
    """Refuse `--user-data-dir=<live>` smuggled through plain launch() args."""
    for raw in args or []:
        s = str(raw)
        if s.startswith("--user-data-dir"):
            _, _, value = s.partition("=")
            if value:
                assert_safe(value.strip().strip('"'), who=who)


_BROWSER_EXES = frozenset(
    ("chrome.exe", "msedge.exe", "chromium.exe", "brave.exe", "chrome", "chromium")
)

_SUBPROCESS_PATCHED = False


def _inspect_command(cmd, who: str) -> None:
    """Refuse a subprocess command line that would open or alias the live Chrome profile.

    Two vectors, both seen in this repository:
      1. `chrome.exe --user-data-dir=<live> --remote-debugging-port=9222` then drive it by CDP.
         Real Chrome, but automation-driven on the operator's own session -- the thing Google
         penalises. Also re-enables every downstream script that assumes port 9222 is theirs.
      2. `cmd /c mklink /J <alias> <live>` -- the original 2026-08-22 vector. Creating the
         alias is the dangerous step, because every later path check resolves through it.
    """
    if isinstance(cmd, (str, bytes)):
        parts = [cmd.decode() if isinstance(cmd, bytes) else cmd]
        joined = parts[0]
    else:
        try:
            parts = [str(x) for x in cmd]
        except TypeError:
            return
        joined = " ".join(parts)

    if not parts:
        return

    lowered = joined.lower()

    # Vector 1: an explicit --user-data-dir anywhere in the command.
    for token in parts:
        t = str(token)
        if "--user-data-dir" in t:
            _, _, value = t.partition("=")
            value = value.strip().strip('"')
            if value:
                assert_safe(value, who=f"{who} (browser --user-data-dir)")

    # Vector 1b: a browser executable invoked with the live root as a bare argument.
    exe = os.path.basename(str(parts[0])).lower()
    if exe in _BROWSER_EXES:
        for token in parts[1:]:
            t = str(token)
            if t.startswith("-"):
                continue
            if os.sep in t or (len(t) > 2 and t[1] == ":"):
                if is_live(t):
                    assert_safe(t, who=f"{who} (browser positional path)")

    # Vector 2: junction / symlink creation pointing at the live tree.
    if "mklink" in lowered or "new-item" in lowered and "junction" in lowered:
        for token in parts:
            t = str(token)
            if t.startswith("/") or t.startswith("-"):
                continue
            if (os.sep in t or (len(t) > 2 and t[1] == ":")) and is_live(t):
                raise LiveProfileRefused(
                    "REFUSED: {who} tried to create a filesystem alias (junction/symlink) "
                    "pointing at the operator's LIVE Chrome profile.\n"
                    "    argument    : {t}\n"
                    "    resolves to : {res}\n"
                    "\n"
                    "This is the exact 2026-08-22 vector. The alias is the dangerous step: "
                    "every later path check resolves through it and looks innocent.\n"
                    "Automation gets its own profile directory. See AGENTS.md 14.1.".format(
                        who=who, t=t, res=resolve(t)
                    )
                )


def install_subprocess_guard() -> bool:
    """Patch subprocess so a browser cannot be spawned against the live profile.

    Deliberately narrow: only inspects commands that name a browser executable, carry a
    `--user-data-dir`, or create a junction. Everything else passes through untouched.
    """
    global _SUBPROCESS_PATCHED
    if _SUBPROCESS_PATCHED:
        return True

    import subprocess

    for attr in ("Popen", "run", "call", "check_call", "check_output"):
        original = getattr(subprocess, attr, None)
        if original is None or getattr(original, "_live_guard", False):
            continue

        def make(orig, name=attr):
            if name == "Popen":

                class GuardedPopen(orig):  # type: ignore[misc,valid-type]
                    def __init__(self, args, *a, **kw):
                        _inspect_command(args, who="subprocess.Popen")
                        super().__init__(args, *a, **kw)

                GuardedPopen._live_guard = True
                GuardedPopen.__name__ = "Popen"
                return GuardedPopen

            def guarded(args, *a, **kw):
                _inspect_command(args, who=f"subprocess.{name}")
                return orig(args, *a, **kw)

            guarded._live_guard = True
            guarded.__name__ = name
            guarded.__doc__ = getattr(orig, "__doc__", None)
            return guarded

        setattr(subprocess, attr, make(original))

    _SUBPROCESS_PATCHED = True
    return True


def install(verbose: bool = False) -> bool:
    """Monkey-patch Playwright's launch entry points to enforce the guard repo-wide.

    Idempotent. Returns True if the guard is active, False if Playwright is not installed
    (in which case there is nothing to guard and no error is appropriate).
    """
    global _INSTALLED
    if _INSTALLED:
        return True

    patched_any = False
    install_subprocess_guard()  # covers chrome.exe / mklink spawned outside Playwright

    for module_name, label in (("playwright.sync_api", "sync"), ("playwright.async_api", "async")):
        try:
            module = __import__(module_name, fromlist=["BrowserType"])
            browser_type = getattr(module, "BrowserType")
        except Exception:
            continue

        original_persistent = getattr(browser_type, "launch_persistent_context", None)
        if original_persistent is not None and not getattr(
            original_persistent, "_live_guard", False
        ):

            def make_persistent(orig):
                def guarded(self, user_data_dir, *a, **kw):
                    assert_safe(user_data_dir, who="launch_persistent_context")
                    return orig(self, user_data_dir, *a, **kw)

                guarded._live_guard = True
                guarded.__doc__ = orig.__doc__
                guarded.__name__ = getattr(orig, "__name__", "launch_persistent_context")
                return guarded

            browser_type.launch_persistent_context = make_persistent(original_persistent)
            patched_any = True

        original_launch = getattr(browser_type, "launch", None)
        if original_launch is not None and not getattr(original_launch, "_live_guard", False):

            def make_launch(orig):
                def guarded(self, *a, **kw):
                    _scan_launch_args(kw.get("args"), who="launch(args=...)")
                    return orig(self, *a, **kw)

                guarded._live_guard = True
                guarded.__doc__ = orig.__doc__
                guarded.__name__ = getattr(orig, "__name__", "launch")
                return guarded

            browser_type.launch = make_launch(original_launch)
            patched_any = True

        if verbose and patched_any:
            print(f"[chrome_live_guard] armed on playwright {label} API")

    _INSTALLED = patched_any
    return patched_any


def install_import_hook() -> None:
    """Arm the guard lazily, on first Playwright import, for the whole interpreter.

    Used by the machine-wide `.pth` bootstrap so that a script which never heard of this
    module is still protected. Silent and non-fatal by design: a guard that breaks unrelated
    Python processes would be worse than the problem it prevents.
    """
    import sys

    if getattr(sys, "_chrome_live_guard_hooked", False):
        return
    sys._chrome_live_guard_hooked = True

    import importlib.abc
    import importlib.machinery

    class Arming(importlib.abc.MetaPathFinder):
        watched = frozenset(("playwright", "playwright.sync_api", "playwright.async_api"))

        def find_spec(self, fullname, path=None, target=None):
            if fullname in self.watched:
                # Remove ourselves first so the real finders resolve it, then arm after.
                try:
                    sys.meta_path.remove(self)
                except ValueError:
                    pass
                try:
                    spec = importlib.machinery.PathFinder.find_spec(fullname, path)
                finally:
                    sys.meta_path.insert(0, self)
                if spec is not None and spec.loader is not None:
                    original_exec = spec.loader.exec_module

                    def exec_module(module, _orig=original_exec):
                        _orig(module)
                        try:
                            install()
                        except Exception:
                            pass

                    try:
                        spec.loader.exec_module = exec_module
                    except Exception:
                        pass
                return spec
            return None

    sys.meta_path.insert(0, Arming())


if __name__ == "__main__":
    import sys

    print(f"live root        : {LIVE_ROOT}")
    print(f"resolves to      : {resolve(LIVE_ROOT)}")
    print(f"playwright guard : {'ARMED' if install(verbose=True) else 'playwright not installed'}")
    print(f"safe profile dir : {safe_profile_dir('selftest')}")
    print()

    checks = [
        (str(LIVE_ROOT), True),
        (str(LIVE_ROOT / "Default"), True),
        (str(LIVE_ROOT / "Profile 17" / "Network"), True),
        (str(LIVE_ROOT.parent), True),
        (r"D:\omniroute-monetizer\state\live_link", None),  # depends: junction or not
        (r"D:\omniroute-monetizer\state\browser_profile", False),
        (str(safe_profile_dir("selftest")), False),
    ]

    failures = 0
    for path, expected in checks:
        refused, reason = verdict(path)
        mark = "REFUSE" if refused else "  allow"
        note = ""
        if expected is not None and refused != expected:
            note = "  <-- WRONG, expected " + ("REFUSE" if expected else "allow")
            failures += 1
        print(f"{mark}  {path}\n        {reason}{note}")

    print()
    print("SELF-TEST FAILURES:", failures)
    sys.exit(1 if failures else 0)
