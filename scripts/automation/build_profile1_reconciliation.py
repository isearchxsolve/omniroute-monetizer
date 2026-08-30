"""Build a complete, non-fabricating reconciliation view for profile 1.

The readiness audit is the inventory authority; the graduation ledger is the
evidence authority.  Missing graduation records are represented explicitly as
PENDING_EVIDENCE rather than inferred from cookies or URLs.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "state" / "seat_readiness.json"
GRADUATION = ROOT / "state" / "graduation_ledger.json"
OUT = ROOT / "state" / "profile1_reconciliation.json"
TAB_RECON = ROOT / "state" / "harvest" / "tab_recon.json"
HISTORICAL_DIRS = [ROOT / "state" / "secrets_old", ROOT / "state" / "secrets_stale_replayfail"]
ACTIVE_DIR = ROOT / "state" / "secrets"
VIDEO_ACCOUNTS = ROOT / "state" / "video_accounts.json"
HARVEST_LEDGER = ROOT / "state" / "harvest_ledger.json"
VIDEO_RUNTIME = ROOT / "state" / "profile1_video_runtime.json"


def main() -> int:
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    graduation = json.loads(GRADUATION.read_text(encoding="utf-8"))
    harvest = json.loads(HARVEST_LEDGER.read_text(encoding="utf-8")) if HARVEST_LEDGER.exists() else []
    video_runtime = json.loads(VIDEO_RUNTIME.read_text(encoding="utf-8")) if VIDEO_RUNTIME.exists() else {"models": []}
    seat = next(x for x in readiness["seats"] if x.get("profile") == "providers")
    evidence = graduation.get("seats", {})
    tab_rows = json.loads(TAB_RECON.read_text(encoding="utf-8")) if TAB_RECON.exists() else []
    tab_by_host = {str(x.get("host", "")).lower(): x for x in tab_rows if x.get("host")}
    historical = []
    for directory in HISTORICAL_DIRS:
        for path in directory.glob("session_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # Metadata only: never copy or expose cookie/token fields.
            historical.append({
                "file": path.name,
                "directory": directory.name,
                "host": str(data.get("host", "")).lower(),
                "modality": data.get("modality"),
                "status": data.get("status"),
                "updatedAt": data.get("updated_at") or data.get("created"),
            })
    active = []
    for path in ACTIVE_DIR.glob("session_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        active.append({
            "file": path.name,
            "host": str(data.get("host", "")).lower(),
            "site": data.get("site"),
            "modality": data.get("modality"),
            "status": data.get("status"),
        })
    video_accounts = json.loads(VIDEO_ACCOUNTS.read_text(encoding="utf-8")).get("accounts", []) if VIDEO_ACCOUNTS.exists() else []
    rows = []
    for name, item in seat["sites"].items():
        record = evidence.get(name)
        if record:
            status = record.get("verdict", "RECORDED_NO_VERDICT")
            source = "graduation_ledger.json"
            detail = record.get("detail", "")
        else:
            status = "PENDING_EVIDENCE"
            source = "seat_readiness.json"
            detail = "No graduation ledger record; readiness evidence is not a graduation proof."
        host = str(item.get("domain", "")).lower()
        live_tab = tab_by_host.get(host)
        if live_tab is None:
            # Readiness uses registrable domains while live tabs may use a
            # service subdomain (for example microsoft.com vs
            # copilot.microsoft.com). Attach evidence only on a strict
            # suffix boundary; never infer a match from a loose substring.
            live_tab = next(
                (v for k, v in tab_by_host.items()
                 if k.endswith("." + host) or host.endswith("." + k)),
                None,
            )
        historical_matches = [
            h for h in historical
            if h["host"] and (h["host"] == host or h["host"].endswith("." + host) or host.endswith("." + h["host"]))
        ]
        active_matches = [
            dict(a) for a in active
            if (a["site"] == name) or (a["host"] and (a["host"] == host or a["host"].endswith("." + host) or host.endswith("." + a["host"])))
        ]
        provider_alias = {"Google Flow (labs.google)": "flow", "rtst.ai": "rtst", "digen.ai": "digen"}.get(name)
        video_matches = [
            {k: a.get(k) for k in ("label", "provider", "port", "profile", "chrome_profile", "enabled", "url")}
            for a in video_accounts
            if provider_alias and a.get("provider") == provider_alias and a.get("profile") == seat.get("profile")
        ]
        runtime_matches = [
            m for m in video_runtime.get("models", []) if provider_alias and m.get("provider") == provider_alias
        ]
        harvest_matches = [
            {k: h.get(k) for k in ("host", "outcome", "url", "elapsed_s", "evidence")}
            for h in harvest
            if h.get("host") and (
                str(h.get("host")).lower() == host
                or str(h.get("host")).lower().endswith("." + host)
                or host.endswith("." + str(h.get("host")).lower())
            )
        ]
        for artifact in active_matches:
            ah = artifact.get("host", "")
            expected_host = str(item.get("domain", "")).lower()
            artifact["hostConsistency"] = (
                "MATCH" if ah == expected_host or ah.endswith("." + expected_host) or expected_host.endswith("." + ah)
                else "HOST_MISMATCH"
            )
            artifact["expectedHost"] = expected_host
        rows.append({
            "name": name,
            "domain": item.get("domain", ""),
            "category": item.get("category", ""),
            "readiness": item.get("verdict", ""),
            "status": status,
            "evidenceSource": source,
            "detail": detail,
            "liveTabEvidence": live_tab if live_tab else None,
            "historicalArtifactEvidence": historical_matches,
            "activeArtifactEvidence": active_matches,
            "videoAccountEvidence": video_matches,
            "videoRuntimeEvidence": {
                "source": video_runtime.get("source"),
                "totalProviderModels": len(runtime_matches),
                "provenModels": sum(bool(m.get("proven")) for m in runtime_matches),
            } if runtime_matches else None,
            "harvestEvidence": harvest_matches,
        })
    rows.sort(key=lambda x: x["name"].casefold())
    output = {
        "generatedFrom": [str(READINESS), str(GRADUATION), str(TAB_RECON), str(HARVEST_LEDGER), str(VIDEO_RUNTIME)],
        "profile": seat.get("profile"),
        "chromeProfile": seat.get("chrome_profile"),
        "accountLabels": seat.get("accountLabels", []),
        "total": len(rows),
        "counts": {
            "recorded": sum(x["status"] != "PENDING_EVIDENCE" for x in rows),
            "pendingEvidence": sum(x["status"] == "PENDING_EVIDENCE" for x in rows),
            "readinessSignedInProbable": sum(x["readiness"] == "signed_in_probable" for x in rows),
            "activeArtifactHostMismatches": sum(
                any(a.get("hostConsistency") == "HOST_MISMATCH" for a in x["activeArtifactEvidence"])
                for x in rows
            ),
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"total": output["total"], **output["counts"], "output": str(OUT)}, indent=2))
    assert output["total"] == 51
    assert output["counts"]["recorded"] + output["counts"]["pendingEvidence"] == 51
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
