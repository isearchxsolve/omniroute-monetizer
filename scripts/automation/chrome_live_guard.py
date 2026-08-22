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
import sys
from pathlib import Path

__all__ = [
    "LiveProfileRefused",
    "is_refusal",
    "LIVE_ROOT",
    "resolve",
    "verdict",
    "is_live",
    "assert_safe",
    "assert_cdp_safe",
    "live_devtools_ports",
    "install",
    "safe_profile_dir",
]


def _shared_registry() -> dict:
    """One dict per interpreter, shared across every copy of this module.

    This file legitimately gets loaded twice under two different module names:
      * `chrome_live_guard`  -- scripts that do `sys.path.insert(...); import chrome_live_guard`
      * `_chrome_live_guard` -- the machine-wide `.pth` bootstrap in site-packages

    Python treats those as two unrelated modules with two unrelated class objects. That
    silently broke `except LiveProfileRefused`: the refusal raised by the bootstrap-armed
    patch was a DIFFERENT class from the one the calling script imported, so the handler
    never matched and callers got a raw traceback instead of the explanation -- or worse,
    concluded the guard had not fired. Found 2026-08-22 while testing the guard itself.

    Attaching the registry to `sys` is the same trick already used for
    `sys._chrome_live_guard_hooked`, and `sys` is the one object both copies share.
    """
    registry = getattr(sys, "_chrome_live_guard_registry", None)
    if registry is None:
        registry = {}
        sys._chrome_live_guard_registry = registry
    return registry


def _canonical_refusal() -> type:
    """Return the ONE LiveProfileRefused class for this interpreter, creating it once."""
    registry = _shared_registry()
    existing = registry.get("LiveProfileRefused")
    if existing is not None:
        return existing

    class LiveProfileRefused(RuntimeError):
        """Raised when something tries to point a browser at the operator's real Chrome."""

    registry["LiveProfileRefused"] = LiveProfileRefused
    return LiveProfileRefused


LiveProfileRefused = _canonical_refusal()


def is_refusal(exc: BaseException) -> bool:
    """True if `exc` is a live-profile refusal, whichever module copy raised it.

    Belt and braces for the dual-identity problem described in `_shared_registry`. Prefer
    `except LiveProfileRefused` (now correct), and use this in defensive `except Exception`
    blocks that must not swallow a refusal and carry on.
    """
    return isinstance(exc, LiveProfileRefused) or type(exc).__name__ == "LiveProfileRefused"


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
# CDP attach: the OTHER way into the operator's browser.
# --------------------------------------------------------------------------------------
#
# `assert_safe` guards *launching*. It says nothing about ATTACHING over the DevTools
# protocol to a Chrome the operator started themselves -- `connect_over_cdp("http://
# 127.0.0.1:9222")`. That is a different door into the same room, and this repo already
# contains two files built for it (`get_chrome_ws.py`, `process_providers_with_existing_
# chrome.py`), so a future agent will find them and try.
#
# Honest note on severity, so nobody over- or under-reacts: attaching does NOT trigger the
# 2026-08-22 revocation. That needed a *foreign* browser presenting the session; here the
# browser is the operator's own Chrome, and Google sees nothing unusual. The reasons to
# refuse are different and still sufficient:
#   * an open DevTools port has NO authentication -- anything running locally can read every
#     cookie in every profile, which is precisely why Google clamped down (see below),
#   * automated clicking on a real signed-in account risks a flag on the ACCOUNT, which is
#     strictly worse than a logged-out session,
#   * it silently makes the operator's browser unusable while automation drives it.
#
# Chrome already blocks the common case. From Chrome 136 onward, `--remote-debugging-port`
# and `--remote-debugging-pipe` are IGNORED when they target the default user-data directory
# (developer.chrome.com/blog/remote-debugging-port). This machine runs Chrome 151, so the
# straightforward attack does not work at all. This guard exists for the variant that does:
# pointing Chrome at a junction that resolves back to the live tree, which defeats Chrome's
# own directory check because the path string looks non-default.
#
# Detection: Chrome writes `DevToolsActivePort` into its own user-data directory whenever a
# debugging port is active, with the port number on line 1. So if the live tree contains that
# file and its port matches the endpoint being attached to, the target IS the operator's
# browser. This resolves junctions, so the alias variant is caught too.


def live_devtools_ports() -> set[int]:
    """Ports advertised by any Chrome currently running on the operator's live profile.

    Empty set is the normal, healthy answer -- it means no live Chrome has a debugging port
    open. Never raises: a guard that crashes on an unreadable file is worse than useless.
    """
    ports: set[int] = set()
    live = resolve(LIVE_ROOT)
    candidates = [live / "DevToolsActivePort"]
    try:
        # Chrome writes it at the root, but check one level down too: a mis-scaffolded
        # profile or an alias pointed at `User Data\Default` puts it elsewhere.
        for child in live.iterdir():
            if child.is_dir():
                candidates.append(child / "DevToolsActivePort")
    except OSError:
        pass

    for candidate in candidates:
        try:
            first = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        except (OSError, ValueError):
            continue
        if first and first[0].strip().isdigit():
            ports.add(int(first[0].strip()))
    return ports


def _endpoint_port(endpoint: str) -> int | None:
    """Extract the TCP port from an http:// or ws:// DevTools endpoint. None if absent."""
    text = str(endpoint)
    try:
        from urllib.parse import urlparse

        parsed = urlparse(text if "://" in text else "http://" + text)
        if parsed.port:
            return parsed.port
    except (ValueError, ImportError):
        pass
    # Bare "9222" or a trailing ":9222" that urlparse choked on.
    tail = text.rsplit(":", 1)[-1].split("/")[0].strip()
    return int(tail) if tail.isdigit() else None


def assert_cdp_safe(endpoint, who: str = "connect_over_cdp") -> str:
    """Return the endpoint unchanged, or refuse if it points at the operator's Chrome."""
    port = _endpoint_port(endpoint)
    live_ports = live_devtools_ports()

    if port is not None and port in live_ports:
        raise LiveProfileRefused(
            "REFUSED: {who} tried to ATTACH to the browser running on the operator's LIVE\n"
            "Chrome profile.\n"
            "    endpoint          : {ep}\n"
            "    port              : {port}\n"
            "    live Chrome ports : {live}\n"
            "    live root         : {root}\n"
            "\n"
            "Matched by `DevToolsActivePort` inside the live user-data tree, so this is the\n"
            "operator's own browser -- not automation's.\n"
            "\n"
            "Attaching does not revoke the session the way the 2026-08-22 launch bug did, but\n"
            "it is still refused: an open DevTools port has no authentication and exposes every\n"
            "cookie in every profile, automated activity on a real account risks a flag on the\n"
            "ACCOUNT rather than just the session, and it takes over a browser the operator is\n"
            "using.\n"
            "\n"
            "Do this instead: launch automation's OWN Chrome with its own profile and its own\n"
            "debugging port, and attach to that.\n"
            "    udd = safe_profile_dir('providers')\n"
            "Sign that profile in ONCE, by hand, and it stays signed in.\n"
            "\n"
            "See CHROME_RULES_FOR_AGENTS.md and MASTER_WORKLOG.md #1032.".format(
                who=who,
                ep=endpoint,
                port=port,
                live=sorted(live_ports) or "none",
                root=resolve(LIVE_ROOT),
            )
        )

    return str(endpoint)


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
    """Monkey-patch Playwright's launch/attach entry points to enforce the guard repo-wide.

    Idempotent. Returns True if the guard is active on Playwright -- INCLUDING the case where
    another copy of this module already patched it. Returns False only when Playwright genuinely
    cannot be imported, so there is nothing to guard.

    That distinction matters and was wrong until 2026-08-22. This file loads twice under two
    names (see `_shared_registry`), and the second copy found everything already patched, so
    `patched_any` stayed False and it reported "playwright not installed" -- while the guard was
    in fact fully armed. A caller doing `if not install(): panic()` would have drawn exactly the
    wrong conclusion, and an agent reading that output might have "fixed" a guard that was working.
    """
    global _INSTALLED
    if _INSTALLED:
        return True

    install_subprocess_guard()  # covers chrome.exe / mklink spawned outside Playwright

    playwright_present = False
    newly_patched = False
    already_patched = False

    for module_name, label in (("playwright.sync_api", "sync"), ("playwright.async_api", "async")):
        try:
            module = __import__(module_name, fromlist=["BrowserType"])
            browser_type = getattr(module, "BrowserType")
        except Exception:
            continue

        playwright_present = True

        # (attribute name, wrapper factory)
        for attr, factory in (
            ("launch_persistent_context", "persistent"),
            ("launch", "launch"),
            ("connect_over_cdp", "cdp"),
        ):
            original = getattr(browser_type, attr, None)
            if original is None:
                continue
            if getattr(original, "_live_guard", False):
                already_patched = True
                continue

            if factory == "persistent":

                def make(orig):
                    def guarded(self, user_data_dir, *a, **kw):
                        assert_safe(user_data_dir, who="launch_persistent_context")
                        return orig(self, user_data_dir, *a, **kw)

                    return guarded

            elif factory == "launch":

                def make(orig):
                    def guarded(self, *a, **kw):
                        _scan_launch_args(kw.get("args"), who="launch(args=...)")
                        return orig(self, *a, **kw)

                    return guarded

            else:  # cdp -- the attach vector. Safe for the async API: the check runs
                # before `orig`, and whatever it returns (coroutine included) passes through.

                def make(orig):
                    def guarded(self, endpoint_url=None, *a, **kw):
                        target = (
                            endpoint_url if endpoint_url is not None else kw.get("endpoint_url")
                        )
                        if target is not None:
                            assert_cdp_safe(target, who="connect_over_cdp")
                        if endpoint_url is None:
                            return orig(self, *a, **kw)
                        return orig(self, endpoint_url, *a, **kw)

                    return guarded

            wrapper = make(original)
            wrapper._live_guard = True
            wrapper.__doc__ = getattr(original, "__doc__", None)
            wrapper.__name__ = getattr(original, "__name__", attr)
            setattr(browser_type, attr, wrapper)
            newly_patched = True

        if verbose:
            print(f"[chrome_live_guard] playwright {label} API: armed")

    active = playwright_present and (newly_patched or already_patched)
    _INSTALLED = active

    if verbose and not playwright_present:
        print("[chrome_live_guard] playwright not importable -- nothing to patch")

    return active


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
    _armed = install(verbose=True)
    print(f"interpreter      : {sys.executable}")
    print(f"auto-armed at startup : {getattr(sys, '_chrome_live_guard_hooked', False)}")
    print(
        "playwright guard : "
        + ("ARMED" if _armed else "playwright not importable here -- nothing to patch")
    )
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
    live_ports = live_devtools_ports()
    print(f"live Chrome debug ports : {sorted(live_ports) or 'none (healthy)'}")

    # A port the live tree is NOT advertising must be allowed -- that is automation's own
    # browser, and refusing it would push the next agent toward the operator's profile.
    unused = next(p for p in (9222, 9333, 9444, 9555) if p not in live_ports)
    try:
        assert_cdp_safe(f"http://127.0.0.1:{unused}", who="selftest")
        print(f"  allow  cdp http://127.0.0.1:{unused}  (not a live Chrome port)")
    except LiveProfileRefused:
        print(f"  <-- WRONG: refused a non-live port {unused}")
        failures += 1

    for port in sorted(live_ports):
        try:
            assert_cdp_safe(f"http://127.0.0.1:{port}", who="selftest")
            print(f"  <-- WRONG: allowed attach to live Chrome port {port}")
            failures += 1
        except LiveProfileRefused:
            print(f"REFUSE  cdp http://127.0.0.1:{port}  (operator's live Chrome)")

    print()
    print("SELF-TEST FAILURES:", failures)
    sys.exit(1 if failures else 0)
