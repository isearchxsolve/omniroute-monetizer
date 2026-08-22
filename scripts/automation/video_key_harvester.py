#!/usr/bin/env python3
"""
Video-provider API key harvester for OmniRoute Monetizer.

WHY THIS EXISTS
---------------
`provider_key_adapters.py` covers exactly three providers (GitHub, Anthropic, OpenRouter)
and has no `main()` block, so `run_automation.py --tier2` shells out to it, gets rc=0, and
harvests nothing. `provider_browser_engine.PROVIDER_URLS` likewise has no video provider.
Result: zero video-provider key coverage. This module closes that gap.

The lever is the live Google session already in state/browser_profile (accounts.google.com,
google.com cookies present). Nearly every video provider offers "Continue with Google", so
that one session unlocks account access without handling any provider password.

HARD RULES (AGENTS.md)
----------------------
- Anti-pattern #7: a key is NEVER reported as harvested until it returns an authenticated
  200 OK against the provider's OWN upstream endpoint. `verify()` does that; unverified keys
  are recorded as CANDIDATE, never as harvested.
- Secrets rule: keys are masked in all console output and all committed artifacts. Raw values
  go only to state/generated_keys.json, which is gitignored.
- Never bypass MFA/CAPTCHA/consent. Those produce HUMAN_REQUIRED and stop, per the existing
  engine's documented boundary.
- Never restarts or stops the OmniRoute service.

PROFILE LOCKING
---------------
Chromium's launch_persistent_context takes an exclusive lock on user_data_dir, so targets are
driven SEQUENTIALLY in one browser session. Do not try to parallelize this across processes on
the same profile — it will fail on the lock, not speed anything up.

Usage:
    python scripts/automation/video_key_harvester.py --probe
    python scripts/automation/video_key_harvester.py --probe --only aistudio,kie
    python scripts/automation/video_key_harvester.py --harvest aistudio
    python scripts/automation/video_key_harvester.py --harvest all
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from omniroute_api import STATE_DIR, log, redact  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = PROJECT_ROOT / "state" / "browser_profile"
ARTIFACT_DIR = PROJECT_ROOT / "state" / "harvest"
KEYS_FILE = STATE_DIR / "generated_keys.json"

# Signals that we are looking at a login wall rather than a signed-in dashboard.
AUTH_WALL_MARKERS = (
    "sign in", "log in", "login", "sign up", "get started free",
    "continue with google", "create an account",
)
# Signals that a Google SSO button is available (the master key for this profile).
GOOGLE_SSO_MARKERS = ("continue with google", "sign in with google", "log in with google", "google")
# "Sign out" / account controls only render once authenticated; they persist even while an SPA
# dashboard's main pane still says "Loading. Please wait", so they are the most reliable signed-in tell.
SIGNED_IN_MARKERS = ("sign out", "log out", "logout", "signout")

# Per-site authenticated tells. Several dashboards render an app shell (nav, credit balance,
# avatar menu) whose visible text contains none of the generic markers above, so _classify
# would misread a live signed-in session as NOT_SIGNED_IN. These substrings only appear in
# the authenticated UI of each site. Checked case-insensitively against the body text.
SITE_SIGNED_IN_MARKERS = {
    "aistudio": ("api keys", "create api key", "google ai studio"),
    "kie": ("api key", "credits", "dashboard"),
    "segmind": ("api keys", "credits", "api-key"),
    "novita": ("api key", "credits"),
    "leonardo": ("api access", "personal access token", "tokens"),
    "haiper": ("api key",),
    "runwayml": ("api key", "api keys"),
    "deepinfra": ("api keys", "api key"),
}

KEY_PATTERNS = {
    "gemini": re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    "generic_sk": re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    "segmind": re.compile(r"\bSG_[A-Za-z0-9]{12,}\b"),
    "hex32": re.compile(r"\b[0-9a-f]{32}\b"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    "jwtish": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    # Last-resort: a long opaque token sitting in an input/code element after a create click.
    "broad_token": re.compile(r"\b[A-Za-z0-9_\-]{24,}\b"),
}


def mask(secret: str) -> str:
    """Mask a secret for display. Never print a raw key."""
    s = str(secret or "")
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]} (len={len(s)})"


# ---------------------------------------------------------------- target table
# omniroute_provider: the EXACT provider id in OmniRoute's VIDEO_PROVIDERS registry.
#   Provider ids must match exactly (xai-oauth does not satisfy xai), so this is the
#   value a harvested key must be wired against.
# verify: (method, url, header_style) used to prove the key works upstream.
TARGETS: List[Dict[str, Any]] = [
    {
        "name": "aistudio",
        "omniroute_provider": "vertex",
        "models": 3,
        "why": "Google AI Studio issues a Gemini API key to a logged-in Google account in ~2 clicks. "
               "Highest value/effort ratio on this box because the Google session already exists. "
               "May satisfy the vertex-veo handler and unlock Veo.",
        "key_url": "https://aistudio.google.com/apikey",
        "key_pattern": "gemini",
        "verify": {
            "method": "GET",
            "url": "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            "auth": "query",
        },
    },
    {
        "name": "kie",
        "omniroute_provider": "kie",
        "models": 16,
        "why": "Largest catalogue of any blocked provider: Veo 3.1, Kling 3, Sora 2.",
        "key_url": "https://kie.ai/api-key",
        "key_pattern": "generic_sk",
        "verify": {"method": "GET", "url": "https://api.kie.ai/api/v1/chat/credit", "auth": "bearer"},
    },
    {
        "name": "segmind",
        "omniroute_provider": "segmind",
        "models": 5,
        "why": "5 video models, free tier, Google SSO available.",
        "key_url": "https://cloud.segmind.com/console/api-keys",
        "key_pattern": "segmind",
        "verify": {"method": "GET", "url": "https://api.segmind.com/v1/credits", "auth": "x-api-key"},
    },
    {
        "name": "novita",
        "omniroute_provider": "novita",
        "models": 2,
        "why": "Free credits on signup, Google SSO.",
        "key_url": "https://novita.ai/settings/key-management",
        "key_pattern": "generic_sk",
        "verify": {"method": "GET", "url": "https://api.novita.ai/v3/user", "auth": "bearer"},
    },
    {
        "name": "leonardo",
        "omniroute_provider": "leonardo",
        "models": 1,
        "why": "Free daily token allowance, Google SSO.",
        "key_url": "https://app.leonardo.ai/api-access",
        "key_pattern": "uuid",
        "verify": {"method": "GET", "url": "https://cloud.leonardo.ai/api/rest/v1/me", "auth": "bearer"},
    },
    {
        "name": "haiper",
        "omniroute_provider": "haiper",
        "models": 1,
        "why": "Free tier video generation, Google SSO.",
        "key_url": "https://haiper.ai/settings/api-key",
        "key_pattern": "generic_sk",
        "verify": {"method": "GET", "url": "https://api.haiper.ai/v1/me", "auth": "bearer"},
    },
    {
        "name": "runwayml",
        "omniroute_provider": "runwayml",
        "models": 0,
        "why": "Registry lists 0 resolved models but the handler exists; a key may populate it.",
        "key_url": "https://app.runwayml.com/settings/api-keys",
        "key_pattern": "generic_sk",
        "verify": {"method": "GET", "url": "https://api.dev.runwayml.com/v1/organization", "auth": "bearer"},
    },
    {
        "name": "deepinfra",
        "omniroute_provider": "deepinfra",
        "models": 4,
        "why": "Existing key 6964962e is valid but credits_exhausted (402). A NEW account gets fresh "
               "free credits, which would revive 4 models with zero code change.",
        "key_url": "https://deepinfra.com/dash/api_keys",
        "key_pattern": "generic_sk",
        "verify": {"method": "GET", "url": "https://api.deepinfra.com/v1/me", "auth": "bearer"},
    },
]

BY_NAME = {t["name"]: t for t in TARGETS}


# ---------------------------------------------------------------------- browser
REAL_USER_DATA = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
# Dedicated copy so we NEVER touch the live profile and NEVER need to close the user's Chrome.
HARVEST_UDD = PROJECT_ROOT / "state" / "harvest_profile"

# Subtrees safe to skip when copying a profile: pure caches, rebuilt on demand. Skipping them
# turns a multi-GB copy into a few-hundred-MB one and avoids files Chrome holds open.
_SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "GraphiteDawnCache",
    "ShaderCache", "GrShaderCache", "Service Worker", "Application Cache", "File System",
    "IndexedDB", "blob_storage", "component_crx_cache", "extensions_crx_cache",
    "BrowserMetrics", "Crashpad", "Safe Browsing", "optimization_guide_model_store",
    "segmentation_platform",
}


def prep_profile_copy(profile_directory: str) -> Path:
    """
    Copy a real Chrome profile into a dedicated user-data-dir so we can drive it with the
    installed Chrome WITHOUT locking or mutating the user's live session. Cookie encryption on
    Windows (DPAPI + App-Bound) is user-scoped and unwrapped from Local State, so the copied
    session decrypts only when launched by the SAME installed chrome.exe as the same user —
    which is exactly what --channel chrome does. Playwright's bundled Chromium cannot.
    """
    import shutil

    src_profile = REAL_USER_DATA / profile_directory
    if not src_profile.exists():
        raise RuntimeError(f"profile not found: {src_profile}")

    if HARVEST_UDD.exists():
        shutil.rmtree(HARVEST_UDD, ignore_errors=True)
    dst_profile = HARVEST_UDD / "Default"  # normalize to Default in the new dir
    dst_profile.mkdir(parents=True, exist_ok=True)

    # Global Local State carries the os_crypt app-bound key wrapper — required for cookie decrypt.
    ls = REAL_USER_DATA / "Local State"
    if ls.exists():
        shutil.copy2(ls, HARVEST_UDD / "Local State")

    copied = skipped = 0
    for item in src_profile.iterdir():
        if item.name in _SKIP_DIRS:
            skipped += 1
            continue
        try:
            if item.is_dir():
                shutil.copytree(item, dst_profile / item.name,
                                ignore=shutil.ignore_patterns(*_SKIP_DIRS), dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst_profile / item.name)
            copied += 1
        except (PermissionError, OSError):
            skipped += 1  # locked-open file (e.g. active LOG); non-fatal for session cookies
    log(f"prepared profile copy: {profile_directory} -> {HARVEST_UDD} ({copied} items, {skipped} skipped)")
    return HARVEST_UDD


def list_real_profiles() -> List[Dict[str, str]]:
    """Enumerate the real Chrome profiles from ``User Data\\Local State`` -> profile.info_cache."""
    ls = REAL_USER_DATA / "Local State"
    try:
        cache = json.loads(ls.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
    except Exception:
        return []
    rows = [{"dir": d, "name": (i or {}).get("name", ""), "user_name": (i or {}).get("user_name", "")}
            for d, i in cache.items()]
    return sorted(rows, key=lambda r: r["dir"])


def ensure_junction(alias: Path) -> bool:
    """
    Create a directory junction aliasing the real Chrome User Data root.

    Chrome blocks remote debugging on the LITERAL default User Data path, but accepts the
    aliased path while still reading/writing the real profile bytes (Google DBSC sessions
    intact — the thing a profile copy loses). Returns True if THIS call created the junction
    (caller must unlink it later). rmdir on a junction removes only the alias, never the
    real files — never rm -rf it.
    """
    import subprocess

    if alias.exists() or alias.is_symlink():
        if not alias.is_symlink():
            # A REAL directory here is a trap: Chrome would treat it as a brand-new user
            # data dir and scaffold empty profiles inside it, so every probe would see a
            # logged-out wall while appearing to "work". Refuse loudly instead.
            raise RuntimeError(
                f"user-data-root {alias} exists and is NOT a junction. Chrome would use it "
                f"as a fresh empty profile dir. Move it aside (e.g. rename) and re-run so a "
                f"real junction to {REAL_USER_DATA} can be created.")
        return False
    alias.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(REAL_USER_DATA)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not (alias.exists() or alias.is_symlink()):
        raise RuntimeError(f"mklink /J failed: {(proc.stderr or proc.stdout).strip()[:200]}")
    log(f"junction created: {alias} -> {REAL_USER_DATA}")
    return True


def remove_junction(alias: Path) -> None:
    """Unlink the alias only. NEVER delete through it."""
    import subprocess

    subprocess.run(["cmd", "/c", "rmdir", str(alias)], capture_output=True, text=True)
    log(f"junction removed: {alias}")


def _launch(pw, headless: bool, user_data_dir: Optional[Path] = None, channel: Optional[str] = None):
    """
    Launch a persistent context. When channel='chrome' and user_data_dir points at a copied
    real profile, the installed Chrome decrypts the carried Google/provider session.
    """
    udd = Path(user_data_dir) if user_data_dir else PROFILE_DIR
    udd.mkdir(parents=True, exist_ok=True)
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-default-browser-check",
        "--no-first-run",
        "--disable-sync",
        "--restore-last-session=false",
    ]
    # Live-profile mode: select a specific real profile under the User Data root. Chrome must be
    # closed first (ProcessSingleton lock), but the logged-in Google/DBSC session stays valid here
    # because it is the actual on-device profile, not a copy.
    live_profile = os.environ.get("_HARVEST_PROFILE_DIRECTORY")
    if live_profile:
        launch_args.append(f"--profile-directory={live_profile}")
    kwargs: Dict[str, Any] = dict(
        user_data_dir=str(udd),
        headless=headless,
        slow_mo=50,
        timeout=60000,  # fail fast if Chrome refuses the CDP connection (e.g. default-dir block)
        args=launch_args,
    )
    if channel:
        kwargs["channel"] = channel
    return pw.chromium.launch_persistent_context(**kwargs)


class _PageManager:
    """
    One page, reused across targets.

    Against a LIVE profile (junction mode) Chrome already has tabs open, and
    Target.createTarget intermittently fails with "Failed to open a new tab" — the
    handoff's segmind crash. Driving a single page (navigate per target, never close
    until the very end) sidesteps tab-creation entirely and keeps concurrency at 1,
    which is what a live user profile needs anyway.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self._page = None

    def page(self):
        if self._page is not None and not getattr(self._page, "is_closed", lambda: True)():
            return self._page
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                pages = list(self.ctx.pages)
                if pages:
                    self._page = pages[0]  # reuse the tab Chrome already opened
                else:
                    self._page = self.ctx.new_page()
                return self._page
            except Exception as e:  # Target.createTarget flake — back off and retry
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"could not obtain a browser page: {last_err}")


def _classify(page, target: Dict[str, Any]) -> Dict[str, Any]:
    """Determine whether we are signed in, at a login wall, or blocked by a human gate."""
    body = ""
    try:
        body = page.locator("body").inner_text(timeout=8000).lower()
    except Exception:
        pass

    has_wall = any(m in body for m in AUTH_WALL_MARKERS)
    has_google = any(m in body for m in GOOGLE_SSO_MARKERS)
    signed_marker = any(m in body for m in SIGNED_IN_MARKERS)
    captcha = ("captcha" in body) or ("verify you are human" in body) or ("recaptcha" in body)

    # Per-site authenticated tells, guarded by the URL: a redirect to an identity provider
    # (accounts.google.com etc.) is decisive — whatever the body text says, we are NOT in.
    site_markers = SITE_SIGNED_IN_MARKERS.get(target.get("name", ""), ())
    site_signed = any(m in body for m in site_markers)
    idp_redirect = any(h in page.url for h in (
        "accounts.google.com", "/signin", "/sign-in", "/login", "auth0", "/auth",
    ))

    # A key-creation control on the page is strong evidence we are already inside the account.
    create_ctrl = None
    for label in ("create api key", "create key", "new api key", "new key", "generate key",
                  "create new api key", "get api key", "add key", "+ create"):
        try:
            loc = page.get_by_role("button", name=re.compile(label, re.I)).first
            if loc.count():
                create_ctrl = label
                break
        except Exception:
            continue
    if not create_ctrl:
        for label in ("create api key", "create key", "new api key", "get api key"):
            try:
                loc = page.get_by_role("link", name=re.compile(label, re.I)).first
                if loc.count():
                    create_ctrl = f"link:{label}"
                    break
            except Exception:
                continue

    # Any key already visible on the page?
    pat = KEY_PATTERNS.get(target.get("key_pattern") or "", None)
    found_existing = bool(pat and pat.search(body)) if pat else False

    if captcha:
        state = "HUMAN_REQUIRED_CAPTCHA"
    elif idp_redirect:
        # On an identity-provider page: whatever the body says, the session is not live here.
        state = "WALL_GOOGLE_SSO_AVAILABLE" if has_google else "WALL_NO_GOOGLE_SSO"
    elif create_ctrl or found_existing:
        state = "SIGNED_IN"
    elif signed_marker and not has_wall:
        # authenticated shell rendered (Sign Out present) but the key UI is still loading
        state = "SIGNED_IN"
    elif site_signed and not has_wall:
        # dashboard-specific authenticated chrome (nav/credits/api-key table) is visible
        state = "SIGNED_IN"
    elif has_wall and has_google:
        state = "WALL_GOOGLE_SSO_AVAILABLE"
    elif has_wall:
        state = "WALL_NO_GOOGLE_SSO"
    else:
        state = "UNKNOWN"

    return {
        "state": state,
        "create_control": create_ctrl,
        "key_visible_on_page": found_existing,
        "google_sso_present": has_google,
        "site_signed_marker": site_signed,
        "idp_redirect": idp_redirect,
        "captcha": captcha,
        "final_url": page.url,
        "title": (page.title() or "")[:120],
    }


def probe(names: List[str], headless: bool = False, timeout_ms: int = 30000,
          user_data_dir: Optional[Path] = None, channel: Optional[str] = None,
          profile_tag: str = "") -> List[Dict[str, Any]]:
    """Fast recon: for each target, report whether the session already gets us in."""
    from playwright.sync_api import sync_playwright

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []

    with sync_playwright() as pw:
        ctx = _launch(pw, headless, user_data_dir=user_data_dir, channel=channel)
        pm = _PageManager(ctx)

        for name in names:
            t = BY_NAME[name]
            started = time.monotonic()
            rec: Dict[str, Any] = {
                "name": name,
                "profile": profile_tag,
                "omniroute_provider": t["omniroute_provider"],
                "models": t["models"],
                "key_url": t["key_url"],
            }
            # One reused page per run: live profiles already have tabs open and
            # Target.createTarget can fail; navigating the same tab is reliable.
            page = None
            try:
                page = pm.page()
                page.set_default_timeout(timeout_ms)
                page.goto(t["key_url"], wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                rec.update(_classify(page, t))
                shot = ARTIFACT_DIR / f"{(profile_tag or 'default').replace(' ', '_')}_{name}_probe.png"
                try:
                    page.screenshot(path=str(shot), full_page=False)
                    rec["screenshot"] = str(shot)
                except Exception:
                    pass
            except Exception as e:
                rec.update({"state": "ERROR", "error": f"{type(e).__name__}: {redact(str(e))[:200]}"})

            rec["elapsed"] = round(time.monotonic() - started, 1)
            out.append(rec)
            log(f"{profile_tag or '-':14} {name:12} {rec.get('state','?'):28} "
                f"{rec['elapsed']:>5}s  {rec.get('title','')[:50]}")

        try:
            ctx.close()
        except Exception:
            pass

    (ARTIFACT_DIR / "probe_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _extract_key(page, pattern_name: str, before_text: str) -> Optional[str]:
    """Find a key that appeared AFTER the create click. Prefer input values / code blocks."""
    pats = [KEY_PATTERNS[pattern_name]] if pattern_name in KEY_PATTERNS else []
    pats.append(KEY_PATTERNS["broad_token"])  # always allow the opaque-token fallback

    # 1) Revealed in an input/textarea value (most create dialogs show the key this way).
    try:
        vals = page.eval_on_selector_all(
            "input, textarea, code, pre",
            "els => els.map(e => (e.value || e.textContent || '').trim()).filter(Boolean)",
        )
    except Exception:
        vals = []
    for v in vals:
        for pat in pats:
            m = pat.search(v)
            if m and m.group(0) not in before_text:
                return m.group(0)

    # 2) Anywhere in the page body that wasn't there before the click.
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""
    for pat in pats:
        for m in pat.finditer(body):
            if m.group(0) not in before_text:
                return m.group(0)
    return None


def harvest_one(pm: "_PageManager", target: Dict[str, Any], timeout_ms: int = 40000) -> Dict[str, Any]:
    """
    Drive an already-authenticated dashboard to mint an API key, then verify it upstream.
    Assumes the persistent context already carries the provider's session (copied profile).
    Uses the shared single page (live profiles reject new-tab creation).
    """
    name = target["name"]
    rec: Dict[str, Any] = {"name": name, "omniroute_provider": target["omniroute_provider"]}
    page = pm.page()
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(target["key_url"], wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # SPA dashboards (DeepInfra etc.) paint a "Loading. Please wait" shell first and only
        # render the key table / create button seconds later. Judging auth on the first frame
        # caused false NOT_SIGNED_IN bails, so poll (~20s) until an authenticated signal or a
        # real wall appears.
        cls = _classify(page, target)
        for _ in range(8):
            if cls["state"] == "SIGNED_IN" or cls.get("create_control") or cls.get("key_visible_on_page"):
                break
            if cls["state"] in ("WALL_GOOGLE_SSO_AVAILABLE", "WALL_NO_GOOGLE_SSO", "HUMAN_REQUIRED_CAPTCHA"):
                break
            page.wait_for_timeout(2500)
            cls = _classify(page, target)
        rec["entry_state"] = cls["state"]

        if cls["state"] != "SIGNED_IN" and not cls.get("create_control") and not cls.get("key_visible_on_page"):
            rec["status"] = "NOT_SIGNED_IN"
            rec["detail"] = f"landed on {cls['state']} ({cls.get('title','')[:60]})"
            page.screenshot(path=str(ARTIFACT_DIR / f"{name}_harvest_blocked.png"))
            return rec

        before = ""
        try:
            before = page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass

        # Click the most likely "create key" control.
        clicked = None
        for label in ("create api key", "create new api key", "create key", "new api key",
                      "new key", "generate key", "generate", "create token", "new token",
                      "deploy a token", "add key", "create", "+ new", "+ create"):
            for role in ("button", "link"):
                try:
                    loc = page.get_by_role(role, name=re.compile(label, re.I)).first
                    if loc.count():
                        loc.click(timeout=6000)
                        clicked = f"{role}:{label}"
                        break
                except Exception:
                    continue
            if clicked:
                break
        rec["create_clicked"] = clicked
        if not clicked:
            rec["status"] = "NO_CREATE_CONTROL"
            page.screenshot(path=str(ARTIFACT_DIR / f"{name}_harvest_nocontrol.png"))
            return rec

        page.wait_for_timeout(1500)

        # A dialog may ask for a token name.
        try:
            dlg = page.locator('[role="dialog"], .modal, [class*="dialog" i]').first
            if dlg.count():
                inp = dlg.locator('input[type="text"], input:not([type]), input[name*="name" i]').first
                if inp.count():
                    inp.fill(f"omniroute-auto-{time.strftime('%Y%m%d%H%M%S')}", timeout=4000)
                    page.wait_for_timeout(400)
                for confirm in ("create", "generate", "add", "confirm", "submit", "save"):
                    b = dlg.get_by_role("button", name=re.compile(confirm, re.I)).first
                    if b.count() and not b.is_disabled():
                        b.click(timeout=5000)
                        break
        except Exception:
            pass

        page.wait_for_timeout(2500)
        key = _extract_key(page, target.get("key_pattern", "broad_token"), before)
        page.screenshot(path=str(ARTIFACT_DIR / f"{name}_harvest_result.png"))

        if not key:
            rec["status"] = "KEY_NOT_REVEALED"
            rec["detail"] = "create flow ran but no new key matched on the page"
            return rec

        rec["status"] = "KEY_CAPTURED"
        rec["masked"] = mask(key)
        ver = verify(target, key)
        rec["verification"] = ver
        rec["verified"] = bool(ver.get("verified"))
        save_key(name, target["omniroute_provider"], key, ver)
        return rec
    except Exception as e:
        rec["status"] = "ERROR"
        rec["error"] = f"{type(e).__name__}: {redact(str(e))[:200]}"
        try:
            page.screenshot(path=str(ARTIFACT_DIR / f"{name}_harvest_error.png"))
        except Exception:
            pass
        return rec
    # NOTE: the shared page is deliberately NOT closed here — live profiles reject
    # new-tab creation, so the same tab carries every target. _PageManager owns it.


# ----------------------------------------------------------------- verification

def verify(target: Dict[str, Any], key: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Prove the key works against the provider's OWN upstream endpoint.
    AGENTS.md anti-pattern #7: without a 200 here, the key is a CANDIDATE, not harvested.
    """
    import requests

    v = target.get("verify") or {}
    url = str(v.get("url") or "")
    if not url:
        return {"verified": False, "reason": "no verify endpoint defined"}

    headers: Dict[str, str] = {}
    style = v.get("auth")
    if style == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    elif style == "x-api-key":
        headers["x-api-key"] = key
    elif style == "query":
        url = url.replace("{key}", key)
    url = url.replace("{key}", key)

    try:
        r = requests.request(v.get("method", "GET"), url, headers=headers, timeout=timeout)
        body = ""
        try:
            body = json.dumps(r.json())[:300]
        except Exception:
            body = (r.text or "")[:300]
        return {
            "verified": r.status_code == 200,
            "status": r.status_code,
            # redact() strips anything secret-shaped; the key itself is never echoed
            "body": redact(body),
            "endpoint": url.split("?")[0],
        }
    except Exception as e:
        return {"verified": False, "error": f"{type(e).__name__}: {redact(str(e))[:200]}"}


def save_key(name: str, provider: str, key: str, verification: Dict[str, Any]) -> None:
    """Persist to state/generated_keys.json (gitignored). Raw value never printed."""
    data: Dict[str, Any] = {}
    if KEYS_FILE.exists():
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[name] = {
        "omniroute_provider": provider,
        "apiKey": key,
        "masked": mask(key),
        "verified": bool(verification.get("verified")),
        "verification": verification,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"stored {name} -> {KEYS_FILE.name} [{mask(key)}] verified={verification.get('verified')}",
        "ok" if verification.get("verified") else "warn")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="recon auth state for each target")
    ap.add_argument("--harvest", default="", help="target name, or 'all'")
    ap.add_argument("--only", default="", help="comma list to restrict targets")
    ap.add_argument("--prep-from", default="",
                    help="real Chrome profile dir to copy into a dedicated harvest profile "
                         "(e.g. 'Profile 14'); implies --channel chrome against the copy")
    ap.add_argument("--channel", default="", help="browser channel, e.g. 'chrome' for installed Google Chrome")
    ap.add_argument("--headless", action="store_true",
                    help="not recommended: Google SSO commonly blocks headless")
    ap.add_argument("--timeout", type=int, default=30000)
    ap.add_argument("--profile-dir", default="",
                    help="LIVE mode: launch this real profile (e.g. 'Profile 14') against the real "
                         "Chrome User Data root; requires Chrome closed. Implies --channel chrome.")
    ap.add_argument("--profiles", default="",
                    help="comma list of real profiles to sweep sequentially in LIVE mode "
                         "(e.g. 'Default,Profile 14,Profile 16,Profile 17'); probe results are "
                         "tagged per profile. Requires Chrome closed.")
    ap.add_argument("--list-profiles", action="store_true",
                    help="print the real Chrome profiles from Local State and exit")
    ap.add_argument("--user-data-root", default="",
                    help="override the User Data root (e.g. a junction that points at the real dir). "
                         "Chrome blocks remote debugging on the literal default path, so pass an "
                         "aliased path here to keep the live session while allowing automation. "
                         "If omitted in live mode, a junction at state/live_link is created "
                         "automatically and removed on exit.")
    args = ap.parse_args()

    if args.list_profiles:
        for row in list_real_profiles():
            print(f"{row['dir']:14} {row['user_name']:36} {row['name']}")
        return 0

    names = [n.strip() for n in args.only.split(",") if n.strip()] or [t["name"] for t in TARGETS]
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        print(f"unknown target(s): {unknown}\nknown: {list(BY_NAME)}")
        return 2

    user_data_dir: Optional[Path] = None
    channel: Optional[str] = args.channel or None
    live_profiles: List[str] = []
    junction_alias: Optional[Path] = None
    junction_created = False
    if args.profiles:
        # Multi-profile LIVE sweep: one junction, one launch per profile, sequential.
        live_profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
        junction_alias = Path(args.user_data_root) if args.user_data_root else PROJECT_ROOT / "state" / "live_link"
        user_data_dir = junction_alias
        channel = channel or "chrome"
    elif args.profile_dir:
        # Attach to the live logged-in profile (Google DBSC sessions survive here, unlike a copy).
        # Chrome refuses remote debugging on the literal default path, so --user-data-root can point
        # at a junction that aliases the real dir: non-default path to Chrome, real bytes on disk.
        if args.user_data_root:
            user_data_dir = Path(args.user_data_root)
        else:
            junction_alias = PROJECT_ROOT / "state" / "live_link"
            user_data_dir = junction_alias
        live_profiles = [args.profile_dir]
        channel = channel or "chrome"
    elif args.prep_from:
        user_data_dir = prep_profile_copy(args.prep_from)
        channel = channel or "chrome"  # a copied real profile only decrypts under real Chrome

    if junction_alias is not None:
        junction_created = ensure_junction(junction_alias)

    try:
        return _run(args, names, user_data_dir, channel, live_profiles)
    finally:
        if junction_created and junction_alias is not None:
            remove_junction(junction_alias)


def _run(args, names: List[str], user_data_dir: Optional[Path], channel: Optional[str],
         live_profiles: List[str]) -> int:
    if args.probe:
        all_rows: List[Dict[str, Any]] = []
        profiles = live_profiles or [""]
        for prof in profiles:
            os.environ["_HARVEST_PROFILE_DIRECTORY"] = prof if prof else ""
            if not prof:
                os.environ.pop("_HARVEST_PROFILE_DIRECTORY", None)
            log(f"probing {len(names)} video-provider key pages "
                f"(profile={prof or 'default'}, udd={user_data_dir or PROFILE_DIR}, "
                f"channel={channel or 'bundled'})")
            rows = probe(names, headless=args.headless, timeout_ms=args.timeout,
                         user_data_dir=user_data_dir, channel=channel, profile_tag=prof)
            all_rows.extend(rows)
        print()
        print(f"{'profile':14} {'target':12} {'omniroute':14} {'models':>6}  state")
        print("-" * 88)
        for r in all_rows:
            print(f"{r.get('profile',''):14} {r['name']:12} {r['omniroute_provider']:14} "
                  f"{r['models']:>6}  {r.get('state','?')}")
        signed = [r for r in all_rows if r.get("state") == "SIGNED_IN"]
        sso = [r for r in all_rows if r.get("state") == "WALL_GOOGLE_SSO_AVAILABLE"]
        print()
        log(f"already signed in: {len(signed)}  |  Google SSO available: {len(sso)}  |  total: {len(all_rows)}")
        if signed:
            log("signed-in hits: " + ", ".join(
                f"{r.get('profile','')}/{r['name']}" for r in signed), "ok")
        print(f"[*] report -> {ARTIFACT_DIR / 'probe_report.json'}")
        return 0

    if not args.harvest:
        print("nothing to do: pass --probe or --harvest <name|all|csv>")
        return 2

    # Harvest mode: drive the already-authenticated dashboards (copied profile) to mint keys.
    from playwright.sync_api import sync_playwright

    harvest_names = [t["name"] for t in TARGETS] if args.harvest == "all" else \
        [n.strip() for n in args.harvest.split(",") if n.strip()]
    bad = [n for n in harvest_names if n not in BY_NAME]
    if bad:
        print(f"unknown harvest target(s): {bad}")
        return 2

    # Live mode: harvest runs against the first (or only) profile of the sweep. Use the
    # probe sweep first to learn WHICH profile holds each login, then harvest per profile.
    if live_profiles:
        os.environ["_HARVEST_PROFILE_DIRECTORY"] = live_profiles[0]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"harvesting {harvest_names} (udd={'copy of '+args.prep_from if args.prep_from else user_data_dir or 'existing'}, "
        f"channel={channel or 'bundled'}, profile={live_profiles[0] if live_profiles else '-'})")
    results: List[Dict[str, Any]] = []
    with sync_playwright() as pw:
        ctx = _launch(pw, args.headless, user_data_dir=(user_data_dir or HARVEST_UDD), channel=channel)
        pm = _PageManager(ctx)
        for hn in harvest_names:
            r = harvest_one(pm, BY_NAME[hn], timeout_ms=args.timeout)
            r["profile"] = live_profiles[0] if live_profiles else ""
            results.append(r)
            log(f"{hn:12} {r.get('status','?'):18} verified={r.get('verified')} {r.get('masked','')}")
        try:
            ctx.close()
        except Exception:
            pass

    (ARTIFACT_DIR / "harvest_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print()
    print(f"{'target':12} {'status':18} verified  masked")
    print("-" * 60)
    for r in results:
        print(f"{r['name']:12} {r.get('status','?'):18} {str(r.get('verified')):8} {r.get('masked','')}")
    captured = [r for r in results if r.get("status") == "KEY_CAPTURED"]
    verified = [r for r in results if r.get("verified")]
    print()
    log(f"captured: {len(captured)}  |  upstream-verified: {len(verified)}  |  total: {len(results)}")
    print(f"[*] report -> {ARTIFACT_DIR / 'harvest_report.json'}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
