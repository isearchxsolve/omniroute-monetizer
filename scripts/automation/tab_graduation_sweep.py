#!/usr/bin/env python3
"""Manifest-first, Chrome-safe graduation runner for dedicated OmniRoute seats.

This tool deliberately separates the two kinds of work that used to be conflated:

* ``--dry-run`` (the default) asks Chrome's public CDP *list* endpoint for page
  metadata only.  It never attaches to a tab, changes focus, types, submits, or
  reads a cookie.  The output is a sanitised manifest that says what each visible
  page is eligible for.
* ``--execute --site <name>`` is a single-site operation.  It delegates capture
  to ``capture_sessions_cdp.py`` and then delegates the independent proof to
  ``replay_check.py``.  It is deliberately serial: one seat / one provider / one
  request at a time.

Safety properties
-----------------
Before *either* mode opens a CDP endpoint, the listener's owning Chrome process
must advertise a ``--user-data-dir`` under ``state/automation_profiles``.  A
listener owned by the operator's live Chrome profile is rejected before a tab
list is requested.  This complements, rather than replaces, chrome_live_guard.

The manifest contains no titles, query strings, cookies, request bodies, or
headers.  Session files are inspected only for non-secret metadata needed to
avoid redundant work.

Examples
--------
    python scripts/automation/tab_graduation_sweep.py
    python scripts/automation/tab_graduation_sweep.py --port 9222 --json state/tab_graduation_manifest.json
    python scripts/automation/tab_graduation_sweep.py --execute --site "Aymo AI"

Graduation remains strict: capture is evidence only; ``REPLAY_OK`` from the
standalone replay probe is the gate.  CAPTCHA, payment, phone, plan, and quota
walls are reported by the underlying capture/replay tools and never solved here.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
SECRETS = STATE / "secrets"
AUTOMATION_ROOT = (STATE / "automation_profiles").resolve()
LIVE_CHROME_ROOT = pathlib.Path(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Admin\AppData\Local")
) / "Google" / "Chrome" / "User Data"
READINESS_PATH = STATE / "seat_readiness.json"
REPLAY_CHECK_PATH = STATE / "replay_check.json"
VIDEO_ACCOUNTS_PATH = STATE / "video_accounts.json"
DEFAULT_MANIFEST = STATE / "tab_graduation_manifest.json"

# Law 3: computed and non-echoable.  These are explicitly passed to replay_check
# rather than relying on whatever default that script happened to have at a given
# point in the project's history.
VERIFY_PROMPT = "Reply with only the number: 41 + 17"
VERIFY_EXPECT = "58"


class SafetyRefusal(RuntimeError):
    """The listening browser cannot be proven to be an automation-owned seat."""


@dataclass(frozen=True)
class PortOwner:
    port: int
    pid: int
    image: str
    command_line: str
    user_data_dir: pathlib.Path
    profile_directory: str


def reg(host: str) -> str:
    """Small, dependency-free registered-domain approximation used elsewhere here."""
    parts = (host or "").lstrip(".").lower().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def safe_url(url: str) -> str:
    """Keep enough diagnostic context for a manifest without retaining query secrets."""
    split = urllib.parse.urlsplit(url)
    if split.scheme not in ("http", "https") or not split.hostname:
        return f"{split.scheme}:" if split.scheme else "about:blank"
    path = split.path or "/"
    return urllib.parse.urlunsplit((split.scheme, split.netloc, path[:180], "", ""))


def _run(args: list[str], timeout: float = 20.0) -> str:
    """Run a read-only OS query.  No shell means no interpolation surprises."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyRefusal(f"could not run {' '.join(args[:2])!r}: {type(exc).__name__}") from exc
    return (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")


def listener_pid(port: int) -> int:
    """Return the unique TCP LISTENING PID for a loopback CDP port."""
    output = _run(["netstat", "-ano", "-p", "tcp"])
    pattern = re.compile(
        rf"^\s*TCP\s+127\.0\.0\.1:{re.escape(str(port))}\s+\S+\s+LISTENING\s+(\d+)\s*$",
        re.IGNORECASE,
    )
    pids = {int(match.group(1)) for line in output.splitlines() if (match := pattern.match(line))}
    if not pids:
        raise SafetyRefusal(f"127.0.0.1:{port} is not listening")
    if len(pids) != 1:
        raise SafetyRefusal(f"127.0.0.1:{port} has multiple listener PIDs: {sorted(pids)}")
    return next(iter(pids))


def process_command_line(pid: int) -> tuple[str, str]:
    """Get the Windows process image and command line without attaching to Chrome."""
    # WMIC is present on this Windows 10 image and avoids PowerShell profile hooks.
    output = _run([
        "wmic", "process", "where", f"ProcessId={pid}", "get", "ProcessId,Name,CommandLine", "/format:list"
    ])
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip().strip('"')
    image = values.get("name", "")
    command = values.get("commandline", "")
    if not command:
        raise SafetyRefusal(f"could not read command line for listener PID {pid}")
    return image, command


def command_flag(command: str, name: str) -> str | None:
    """Read --flag=value or --flag value without reconstructing a shell command."""
    # The supported profile path has no quotes in ordinary launches, but accepting
    # quoted values makes the gate fail closed on future launcher clean-ups.
    quoted = re.search(rf"(?:^|\s){re.escape(name)}=(?:\"([^\"]+)\"|'([^']+)'|(\S+))", command,
                       flags=re.IGNORECASE)
    if quoted:
        return next((part for part in quoted.groups() if part is not None), None)
    spaced = re.search(rf"(?:^|\s){re.escape(name)}\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", command,
                       flags=re.IGNORECASE)
    if spaced:
        return next((part for part in spaced.groups() if part is not None), None)
    return None


def is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def configured_chrome_seat(port: int) -> tuple[str, str]:
    """Return the enabled, explicitly pinned automation profile for this port.

    `video_accounts.json` is the current launcher registry.  A row without a
    chrome_profile (for example an API/stateless provider sharing a port) cannot
    authorise a generic browser attachment, so only explicit pins participate.
    """
    registry = read_json(VIDEO_ACCOUNTS_PATH, {})
    accounts = registry.get("accounts", []) if isinstance(registry, dict) else []
    enabled = [
        row for row in accounts
        if isinstance(row, dict) and row.get("enabled") is True and row.get("port") == port
    ]
    pinned = [row for row in enabled if row.get("profile") and row.get("chrome_profile")]
    if not pinned:
        raise SafetyRefusal(f"no enabled, explicitly profile-pinned Chrome seat is configured for :{port}")
    roots = {str(row["profile"]) for row in pinned}
    profiles = {str(row["chrome_profile"]) for row in pinned}
    if len(roots) != 1 or len(profiles) != 1:
        raise SafetyRefusal(f"configured Chrome ownership for :{port} is ambiguous")
    return next(iter(roots)), next(iter(profiles))


def assert_automation_seat(port: int) -> PortOwner:
    """Fail closed unless this exact CDP listener belongs to a dedicated seat."""
    # This consults the live Chrome tree's DevToolsActivePort files only; it does
    # not attach to a browser.  A failure to import/enforce the repository guard
    # is itself a refusal, never a warning.
    try:
        from chrome_live_guard import assert_cdp_safe, assert_safe
    except Exception as exc:
        raise SafetyRefusal(f"chrome_live_guard is unavailable: {type(exc).__name__}") from exc
    try:
        assert_cdp_safe(f"http://127.0.0.1:{port}")
    except Exception as exc:
        raise SafetyRefusal(f"chrome_live_guard refused CDP port :{port}: {type(exc).__name__}") from exc

    profile_tag, expected_subprofile = configured_chrome_seat(port)
    expected_udd = (AUTOMATION_ROOT / profile_tag).resolve()
    try:
        assert_safe(expected_udd, who="tab-graduation-manifest")
    except Exception as exc:
        raise SafetyRefusal(f"configured automation profile is unsafe: {type(exc).__name__}") from exc
    if not (expected_udd / "Local State").is_file() or not (expected_udd / expected_subprofile / "Preferences").is_file():
        raise SafetyRefusal(f"configured seat :{port} lacks Local State or pinned-profile Preferences")

    pid = listener_pid(port)
    image, command = process_command_line(pid)
    if image.lower() != "chrome.exe":
        raise SafetyRefusal(f"port {port} listener PID {pid} is {image or 'unknown'}, not chrome.exe")

    value = command_flag(command, "--user-data-dir")
    if not value:
        raise SafetyRefusal(f"Chrome PID {pid} lacks --user-data-dir; refusing CDP enumeration")
    user_data_dir = pathlib.Path(value)
    if is_relative_to(user_data_dir, LIVE_CHROME_ROOT) or user_data_dir.resolve() != expected_udd:
        raise SafetyRefusal(
            f"Chrome PID {pid} does not use the configured dedicated profile; refusing CDP enumeration"
        )

    declared_port = command_flag(command, "--remote-debugging-port")
    if declared_port != str(port):
        raise SafetyRefusal(
            f"Chrome PID {pid} does not declare --remote-debugging-port={port}; refusing CDP enumeration"
        )
    actual_subprofile = command_flag(command, "--profile-directory")
    if actual_subprofile != expected_subprofile:
        raise SafetyRefusal(
            f"Chrome PID {pid} profile-directory does not match configured seat; refusing CDP enumeration"
        )
    return PortOwner(port, pid, image, command, user_data_dir.resolve(), actual_subprofile)


def _browser_ws_url(owner: PortOwner) -> str:
    """Read the dedicated profile's browser-target path without opening a page target."""
    active_port = owner.user_data_dir / "DevToolsActivePort"
    try:
        lines = active_port.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise SafetyRefusal(f"dedicated seat :{owner.port} has no readable DevToolsActivePort") from exc
    if len(lines) < 2 or lines[0].strip() != str(owner.port) or not lines[1].startswith("/devtools/browser/"):
        raise SafetyRefusal(f"dedicated seat :{owner.port} has an invalid DevToolsActivePort shape")
    return f"ws://127.0.0.1:{owner.port}{lines[1].strip()}"


def _browser_target_list(owner: PortOwner) -> list[dict[str, Any]]:
    """Use read-only Target.getTargets when the legacy HTTP list endpoint is slow.

    This is a connection to Chrome's *browser* target, not an attachment to any
    page.  It sends exactly one official CDP read command, Target.getTargets, and
    never enables domains, activates a tab, evaluates JavaScript, or requests a
    page websocket.
    """
    try:
        import websocket  # websocket-client, already used by capture_sessions_cdp.py
        ws = websocket.create_connection(_browser_ws_url(owner), timeout=15, suppress_origin=True)
    except Exception as exc:
        raise SafetyRefusal(f"browser-target CDP connection failed on :{owner.port}: {type(exc).__name__}") from exc
    try:
        ws.send(json.dumps({"id": 1, "method": "Target.getTargets", "params": {}}))
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            ws.settimeout(max(0.4, deadline - time.monotonic()))
            raw = ws.recv()
            message = json.loads(raw)
            if message.get("id") != 1:
                continue
            infos = (message.get("result") or {}).get("targetInfos")
            if not isinstance(infos, list):
                raise SafetyRefusal(f"Target.getTargets on :{owner.port} returned no targetInfos")
            return [
                {"id": info.get("targetId"), "type": info.get("type"), "url": info.get("url")}
                for info in infos
                if isinstance(info, dict) and info.get("type") == "page"
            ]
    except SafetyRefusal:
        raise
    except Exception as exc:
        raise SafetyRefusal(f"Target.getTargets failed on :{owner.port}: {type(exc).__name__}") from exc
    finally:
        try:
            ws.close()
        except Exception:
            pass
    raise SafetyRefusal(f"Target.getTargets timed out on :{owner.port}")


def tab_targets(owner: PortOwner) -> list[dict[str, Any]]:
    """Read only page metadata, preferring the browser target over legacy HTTP list."""
    try:
        return _browser_target_list(owner)
    except SafetyRefusal as browser_error:
        # `/json/list` is Chrome's documented legacy discovery endpoint.  It is
        # kept as a bounded fallback for older DevTools builds, but an unresponsive
        # browser target + an unresponsive list endpoint is a reportable CDP issue,
        # never a reason to relaunch or touch a profile.
        url = f"http://127.0.0.1:{owner.port}/json/list"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except (OSError, ValueError) as http_error:
            raise SafetyRefusal(
                f"CDP discovery unavailable on :{owner.port}: browser Target.getTargets "
                f"({browser_error}); HTTP /json/list ({type(http_error).__name__})"
            ) from http_error
        if not isinstance(payload, list):
            raise SafetyRefusal(f"CDP list on :{owner.port} did not return a target array")
        return [target for target in payload if isinstance(target, dict) and target.get("type") == "page"]


def read_json(path: pathlib.Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def readiness_for_port(port: int) -> dict[str, dict[str, str]]:
    """Map registered host to non-secret site/readiness metadata for this seat."""
    readiness = read_json(READINESS_PATH, {})
    entries: dict[str, dict[str, str]] = {}
    for seat in readiness.get("seats", []) if isinstance(readiness, dict) else []:
        if port not in (seat.get("ports") or []):
            continue
        for name, site in (seat.get("sites") or {}).items():
            domain = str((site or {}).get("domain") or "")
            if not domain:
                continue
            key = reg(domain)
            # Prefer a genuinely authenticated declaration over a visited copy of
            # the same host that appeared elsewhere in the old readiness report.
            candidate = {"site": str(name), "readiness": str((site or {}).get("verdict") or "unknown")}
            existing = entries.get(key)
            if existing is None or existing["readiness"] in {"visited", "expired", "unknown"}:
                entries[key] = candidate
    return entries


def artifact_index() -> dict[str, dict[str, Any]]:
    """Read only metadata from secrets; never emit credential material to the manifest."""
    indexed: dict[str, dict[str, Any]] = {}
    if not SECRETS.is_dir():
        return indexed
    for path in sorted(SECRETS.glob("session_*.json")):
        data = read_json(path, {})
        if not isinstance(data, dict):
            continue
        host = str(data.get("host") or "")
        if not host:
            exchange = data.get("recorded_exchange") or {}
            host = host_of(str(exchange.get("url") or "")) if isinstance(exchange, dict) else ""
        if not host:
            continue
        index = reg(host)
        previous = indexed.get(index)
        candidate = {
            "file": path.name,
            "host": host,
            "hasRecordedExchange": bool((data.get("recorded_exchange") or {}).get("request_body")),
            "hasRecordedWebSocket": bool(data.get("recorded_ws")),
            "runtime": str(data.get("runtime") or ""),
        }
        # A replayable HTTP artifact is more useful than a Chrome-only one when
        # multiple session files share a registered domain.
        if previous is None or (candidate["hasRecordedExchange"] and not previous["hasRecordedExchange"]):
            indexed[index] = candidate
    return indexed


def replay_index() -> dict[str, str]:
    report = read_json(REPLAY_CHECK_PATH, {})
    results = report.get("results", []) if isinstance(report, dict) else []
    indexed: dict[str, str] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        host = str(row.get("host") or "")
        verdict = str(row.get("verdict") or "")
        if host and verdict:
            indexed[reg(host)] = verdict
    return indexed


def classify_tab(
    target: dict[str, Any],
    readiness: dict[str, dict[str, str]],
    artifacts: dict[str, dict[str, Any]],
    replays: dict[str, str],
) -> dict[str, Any]:
    url = str(target.get("url") or "")
    host = host_of(url)
    registered = reg(host)
    base: dict[str, Any] = {
        "targetId": str(target.get("id") or "")[:80],
        "url": safe_url(url),
        "host": host,
        "registeredHost": registered,
    }
    if not host:
        base.update(classification="SKIP_INTERNAL_OR_BLANK", nextAction="none")
        return base

    known = readiness.get(registered)
    artifact = artifacts.get(registered)
    replay = replays.get(registered)
    if known:
        base.update(knownSite=known["site"], readiness=known["readiness"])
    if artifact:
        base["artifact"] = {
            "file": artifact["file"],
            "hasRecordedExchange": artifact["hasRecordedExchange"],
            "hasRecordedWebSocket": artifact["hasRecordedWebSocket"],
            "runtime": artifact["runtime"],
        }
    if replay:
        base["latestReplayVerdict"] = replay

    if not known:
        base.update(classification="UNMANAGED_TAB", nextAction="manual_review_before_capture")
    elif known["readiness"] not in {"signed_in_probable", "session_only"}:
        base.update(classification="SKIP_NOT_AUTHENTICATED", nextAction="none")
    elif replay == "REPLAY_OK":
        base.update(classification="ALREADY_GRADUATED", nextAction="none")
    elif artifact and artifact["hasRecordedWebSocket"] and not artifact["hasRecordedExchange"]:
        base.update(classification="TRANSPORT_WEBSOCKET", nextAction="build_or_use_websocket_adapter")
    elif artifact and artifact["hasRecordedExchange"]:
        base.update(classification="EXISTING_ARTIFACT_NEEDS_REPLAY", nextAction="replay_before_recapture")
    else:
        base.update(classification="ELIGIBLE_CAPTURE", nextAction="capture_then_independent_replay")
    return base


def build_manifest(port: int) -> dict[str, Any]:
    owner = assert_automation_seat(port)
    readiness = readiness_for_port(port)
    artifacts = artifact_index()
    replays = replay_index()
    rows = [classify_tab(tab, readiness, artifacts, replays) for tab in tab_targets(owner)]
    rows.sort(key=lambda row: (row["classification"], row["url"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    return {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "read_only_manifest",
        "port": port,
        "seatSafety": {
            "verified": True,
            "listenerPid": owner.pid,
            "userDataDir": str(owner.user_data_dir.relative_to(ROOT)),
            "profileDirectory": owner.profile_directory,
            "reason": "listener is chrome.exe with a dedicated state/automation_profiles user-data-dir",
        },
        "verification": {"prompt": VERIFY_PROMPT, "expect": VERIFY_EXPECT},
        "summary": {"pageTabs": len(rows), "byClassification": counts},
        "tabs": rows,
    }


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def printable_summary(manifest: dict[str, Any]) -> None:
    summary = manifest["summary"]
    print(f"safe dedicated seat :{manifest['port']}  {manifest['seatSafety']['userDataDir']}")
    print(f"page tabs           : {summary['pageTabs']}")
    for classification, count in sorted(summary["byClassification"].items()):
        print(f"  {classification:31s} {count}")
    print("\nNo tab was attached, focused, typed into, or submitted in manifest mode.")


def known_site(manifest: dict[str, Any], site: str) -> dict[str, Any]:
    wanted = site.casefold()
    rows = [row for row in manifest["tabs"] if str(row.get("knownSite") or "").casefold() == wanted]
    if not rows:
        raise SystemExit(f"site {site!r} is not an authenticated known tab on :{manifest['port']}")
    return rows[0]


def execute_one(port: int, site: str, wait: float) -> int:
    """One intentionally small live unit: capture, then pure-Python replay."""
    manifest = build_manifest(port)
    row = known_site(manifest, site)
    if row["classification"] not in {"ELIGIBLE_CAPTURE", "EXISTING_ARTIFACT_NEEDS_REPLAY"}:
        raise SystemExit(
            f"{site}: manifest class {row['classification']}; no capture will be sent by this command"
        )

    python = sys.executable
    if row["classification"] == "ELIGIBLE_CAPTURE":
        capture = [
            python, str(ROOT / "scripts" / "automation" / "capture_sessions_cdp.py"),
            "--port", str(port), "--sites", site, "--wait", str(wait),
        ]
        completed = subprocess.run(capture, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode

    # `--only` scopes both traffic and state/reporting to this one host/site.
    replay = [
        python, str(ROOT / "scripts" / "automation" / "replay_check.py"),
        "--only", site.lower().replace(" ", "_"),
        "--prompt", VERIFY_PROMPT, "--expect", VERIFY_EXPECT,
    ]
    return subprocess.run(replay, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--port", type=int, default=9222, help="dedicated seat CDP port (default: 9222)")
    parser.add_argument("--json", type=pathlib.Path, default=DEFAULT_MANIFEST,
                        help="sanitised manifest output path")
    parser.add_argument("--execute", action="store_true",
                        help="perform exactly one explicitly named capture/replay unit")
    parser.add_argument("--site", default="", help="exact readiness site name; required with --execute")
    parser.add_argument("--wait", type=float, default=25.0, help="capture wait seconds when --execute is set")
    args = parser.parse_args()

    if args.execute and not args.site.strip():
        parser.error("--execute requires exactly one --site; run the manifest first and keep live work serial")
    if not args.execute:
        manifest = build_manifest(args.port)
        write_json(args.json, manifest)
        printable_summary(manifest)
        print(f"manifest             : {args.json}")
        return 0
    return execute_one(args.port, args.site.strip(), args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
