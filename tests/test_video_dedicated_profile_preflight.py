from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

import video_dedicated_profile_preflight as preflight


def test_audit_boundary_reports_dedicated_profiles_without_browser_activity(tmp_path):
    calls = []

    def profile(tag):
        return tmp_path / tag

    def safe(path, who):
        calls.append(("safe", str(path), who))
        return path.resolve()

    def cdp(endpoint, who):
        calls.append(("cdp", endpoint, who))
        return endpoint

    report = preflight.audit_boundary(
        [
            {"provider": "flow", "profile": "providers", "port": 9222},
            {"provider": "rtst", "profile": "providers", "port": 9222},
            {"provider": "digen", "profile": "seat2", "port": 9224},
        ],
        profile_dir=profile,
        safe_check=safe,
        cdp_check=cdp,
    )

    assert report["boundary"] == "SAFE_DEDICATED"
    assert report["openedChrome"] is False
    assert report["attachedToCdp"] is False
    assert report["quotedVideo"] is False
    assert report["submittedVideo"] is False
    assert report["approvedCdpPorts"] == [9222, 9224]
    assert report["dedicatedProfileTags"] == ["providers", "seat2"]
    assert len([call for call in calls if call[0] == "cdp"]) == 2


def test_audit_boundary_rejects_a_cdp_port_shared_by_multiple_profiles(tmp_path):
    def profile(tag):
        return tmp_path / tag

    try:
        preflight.audit_boundary(
            [
                {"provider": "flow", "profile": "providers", "port": 9222},
                {"provider": "rtst", "profile": "seat2", "port": 9222},
            ],
            profile_dir=profile,
            safe_check=lambda path, who: path,
            cdp_check=lambda endpoint, who: endpoint,
        )
    except ValueError as exc:
        assert "multiple profiles" in str(exc)
    else:
        raise AssertionError("a cross-profile CDP port must be refused")
