#!/usr/bin/env python3
"""Prove the configured video browser boundary without opening or attaching Chrome.

This intentionally does *not* call a CDP endpoint, start Chrome, read cookies, quote a job, or
submit a generation.  It only verifies that each enabled video account resolves to a dedicated
profile under ``state/automation_profiles`` and that none of the configured CDP ports is advertised
by the operator's live Chrome tree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
ACCOUNTS_FILE = ROOT / "state" / "video_accounts.json"
OUTPUT_FILE = ROOT / "state" / "video_dedicated_profile_preflight.json"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import LiveProfileRefused, assert_cdp_safe, assert_safe, safe_profile_dir  # noqa: E402


def load_enabled_accounts(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read only fields needed for the safety boundary; never return account labels or URLs."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    accounts = raw.get("accounts") if isinstance(raw, dict) else raw
    if not isinstance(accounts, list):
        raise ValueError("video accounts file does not contain an accounts list")
    result: list[dict[str, Any]] = []
    for account in accounts:
        if not isinstance(account, dict) or not account.get("enabled"):
            continue
        provider = str(account.get("provider") or "").strip()
        profile = str(account.get("profile") or "providers").strip()
        try:
            port = int(account.get("port"))
        except (TypeError, ValueError):
            port = 0
        if not provider or not profile or not (1 <= port <= 65535):
            raise ValueError("enabled video account has an invalid provider/profile/port boundary")
        result.append({"provider": provider, "profile": profile, "port": port})
    return result


def audit_boundary(
    accounts: list[dict[str, Any]],
    profile_dir: Callable[[str], pathlib.Path] = safe_profile_dir,
    safe_check: Callable[[pathlib.Path, str], pathlib.Path] = assert_safe,
    cdp_check: Callable[[str, str], str] = assert_cdp_safe,
) -> dict[str, Any]:
    """Return a redacted boundary decision with no browser interaction."""
    profiles: dict[str, str] = {}
    ports: dict[int, set[str]] = defaultdict(set)
    providers: set[str] = set()

    for account in accounts:
        profile = account["profile"]
        resolved = safe_check(profile_dir(profile), "video_dedicated_profile_preflight")
        profiles[profile] = str(resolved)
        ports[account["port"]].add(profile)
        providers.add(account["provider"])

    bad_shared_ports = sorted(port for port, tags in ports.items() if len(tags) != 1)
    if bad_shared_ports:
        raise ValueError(f"configured video CDP port maps to multiple profiles: {bad_shared_ports}")

    approved_ports: list[int] = []
    refused_ports: list[int] = []
    for port in sorted(ports):
        try:
            cdp_check(f"http://127.0.0.1:{port}", "video_dedicated_profile_preflight")
        except LiveProfileRefused:
            refused_ports.append(port)
        else:
            approved_ports.append(port)

    return {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "readOnly": True,
        "openedChrome": False,
        "attachedToCdp": False,
        "quotedVideo": False,
        "submittedVideo": False,
        "providers": sorted(providers),
        "enabledAccountCount": len(accounts),
        "dedicatedProfileTags": sorted(profiles),
        "dedicatedProfilePaths": [profiles[tag] for tag in sorted(profiles)],
        "approvedCdpPorts": approved_ports,
        "refusedCdpPorts": refused_ports,
        "boundary": "SAFE_DEDICATED" if not refused_ports else "REFUSED_LIVE_CHROME_PORT",
        "executionState": "BLOCKED_PENDING_PROVIDER_SESSION_VERIFICATION",
        "nextStep": "Open only the approved dedicated profile, sign in manually if required, then run a no-spend provider-session check.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=pathlib.Path, default=ACCOUNTS_FILE)
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    try:
        report = audit_boundary(load_enabled_accounts(args.accounts))
    except (OSError, ValueError, json.JSONDecodeError, LiveProfileRefused) as exc:
        print(f"preflight failed: {type(exc).__name__}: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "boundary", "enabledAccountCount", "dedicatedProfileTags", "approvedCdpPorts", "executionState"
    )}))
    return 0 if report["boundary"] == "SAFE_DEDICATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
