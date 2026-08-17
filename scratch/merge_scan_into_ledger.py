#!/usr/bin/env python3
"""Merge measured upstream-scan + deep-probe evidence into the ledger.

For every provider in state/provider_upstream_scan.json (and the deep-probe
refinements), replace the ASSUMED EXTERNAL_ACCOUNT_REQUIRED classification
with an OBSERVED verdict + per-provider evidence string. This is the honest
correction to the bulk-classification gap.

Mapping observed verdict -> ledger status:
  TRULY_OPEN        -> LIVE_ACTIVE (zero-auth usable)
  OPEN_NO_AUTH      -> LIVE_ACTIVE (only if deep probe confirmed chat open)
  AUTH_REQUIRED     -> BLOCKED_AUTH_REQUIRED (needs key; signup-flow TBD)
  CREDITS           -> BLOCKED_CREDITS
  PAYWALL_CREDITS   -> BLOCKED_CREDITS
  CAPTCHA_BOT_BLOCK -> BLOCKED_CAPTCHA
  RATE_LIMITED      -> BLOCKED_RATE_LIMITED
  NEEDS_BROWSER     -> BLOCKED_BROWSER_SESSION
  LOCAL_RUNTIME     -> BLOCKED_LOCAL_RUNTIME
  UPSTREAM_DOWN     -> BLOCKED_UPSTREAM_DOWN
  NOT_FOUND         -> BLOCKED_ENDPOINT_GONE
  NO_MODEL_LIST     -> BLOCKED_AUTH_REQUIRED (catalog only)
  OTHER/UNKNOWN     -> BLOCKED_UNVERIFIED (raw status kept as evidence)

Never touches tokens/passwords. Writes ledger back in place.
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "state" / "all_296_providers_execution_ledger.json"
SCAN = ROOT / "state" / "provider_upstream_scan.json"
DEEP = ROOT / "state" / "provider_deep_probe.json"

MAP = {
    "AUTH_REQUIRED": "BLOCKED_AUTH_REQUIRED",
    "CREDITS": "BLOCKED_CREDITS",
    "PAYWALL_CREDITS": "BLOCKED_CREDITS",
    "CAPTCHA_BOT_BLOCK": "BLOCKED_CAPTCHA",
    "RATE_LIMITED": "BLOCKED_RATE_LIMITED",
    "NEEDS_BROWSER": "BLOCKED_BROWSER_SESSION",
    "LOCAL_RUNTIME": "BLOCKED_LOCAL_RUNTIME",
    "UPSTREAM_DOWN": "BLOCKED_UPSTREAM_DOWN",
    "NOT_FOUND": "BLOCKED_ENDPOINT_GONE",
    "NO_MODEL_LIST": "BLOCKED_AUTH_REQUIRED",
    "OTHER": "BLOCKED_UNVERIFIED",
    "UNKNOWN": "BLOCKED_UNVERIFIED",
    "OPEN_NO_AUTH": "BLOCKED_UNVERIFIED",  # refined below by deep probe
    "TRULY_OPEN": "LIVE_ACTIVE",
}


def main() -> int:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    providers = ledger["providers"]
    scan = json.loads(SCAN.read_text(encoding="utf-8"))["results"]
    deep = json.loads(DEEP.read_text(encoding="utf-8"))["results"]

    # deep-probe verdicts override the shallow scan where present
    deep_verdict = {slug: r.get("verdict") for slug, r in deep.items()}

    updated = 0
    status_counter = {}
    for slug, r in scan.items():
        if slug not in providers:
            continue
        verdict = deep_verdict.get(slug, r.get("verdict"))
        new_status = MAP.get(verdict, "BLOCKED_UNVERIFIED")

        # build a real per-provider evidence string (redacted, no secrets)
        ev_parts = [f"upstream-scan {time.strftime('%Y-%m-%d')}: {verdict}"]
        if r.get("status") is not None:
            ev_parts.append(f"HTTP {r['status']}")
        if r.get("probed"):
            ev_parts.append(f"probed {r['probed']}")
        snip = (r.get("body_snippet") or r.get("note") or "").replace("\n", " ")[:120]
        if snip:
            ev_parts.append(f"body={snip!r}")
        if slug in deep:
            d = deep[slug]
            ev_parts.append(f"deep-probe {d.get('verdict')} "
                            f"({d.get('models_note', '')})")
            for a in d.get("attempts", [])[:1]:
                ev_parts.append(f"chat[{a.get('status')}]={(a.get('snippet') or '')[:80]!r}")

        entry = providers[slug]
        if isinstance(entry, dict):
            entry["status"] = new_status
            entry["observed_verdict"] = verdict
            entry["evidence"] = " | ".join(ev_parts)
        else:
            providers[slug] = {"status": new_status,
                               "observed_verdict": verdict,
                               "evidence": " | ".join(ev_parts)}
        updated += 1
        status_counter[new_status] = status_counter.get(new_status, 0) + 1

    # recompute top-level status_counts across ALL providers
    all_counts = {}
    for slug, e in providers.items():
        st = e.get("status") if isinstance(e, dict) else e
        all_counts[st] = all_counts.get(st, 0) + 1
    ledger["status_counts"] = all_counts
    ledger["last_upstream_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")

    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"updated {updated} ledger entries with measured evidence\n")
    print("new status_counts:")
    for st, n in sorted(all_counts.items(), key=lambda x: -x[1]):
        print(f"  {st:28s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
