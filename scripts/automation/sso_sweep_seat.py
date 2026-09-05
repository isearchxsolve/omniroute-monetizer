"""Cross-seat LOGIN_WALL re-SSO sweep (operator directive 2026-09-02: fully via
automation; the bounded cdp_drive sso playbook is the proven instrument - one
click each, never types, stops at every wall).

Reads each seat's surface-audit ledger, takes every LOGIN_WALL row whose tab is
reachable on the seat, runs the bounded SSO playbook, writes the result back
into the ledger row. Walls stay walls (SSO_INITIATED on a chooser we cannot
pass is still a report, not a solve).
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CDP = ROOT / "scripts" / "automation" / "cdp_drive.py"

JOBS = {
    9222: (ROOT / "state" / "surface_audit_9222_full_v2.json",
           ROOT / "state" / "sso_sweep_9222.json"),
    9223: (ROOT / "state" / "surface_audit_9223_full_v2.json",
           ROOT / "state" / "sso_sweep_9223.json"),
    9224: (ROOT / "state" / "surface_audit_9224_full.json",
           ROOT / "state" / "sso_sweep_9224.json"),
    9225: (ROOT / "state" / "surface_audit_9225_full.json",
           ROOT / "state" / "sso_sweep_9225.json"),
}

# hosts where SSO is hopeless by prior evidence (region ban / hard 403 / gone)
SKIP_HOSTS = {"www.doubao.com", "www.coze.com", "www.phind.com", "www.giz.ai"}


def host(u):
    return (urllib.parse.urlsplit(u or "").hostname or "").lower()


def targets(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=15) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return []


def run_sso(port, tid, url, budget=300):
    try:
        r = subprocess.run(
            [str(PY), str(CDP), "sso", "--port", str(port), "--tid", tid,
             "--url", url, "--budget", str(budget)],
            capture_output=True, text=True, timeout=budget + 90,
            encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        # playbook prints a single JSON doc
        start = out.find("{")
        if start >= 0:
            return json.loads(out[start:])
        return {"state": "ERROR", "detail": (r.stderr or out)[-160:]}
    except Exception as e:
        return {"state": "ERROR", "detail": type(e).__name__}


def main():
    port = int(sys.argv[1])
    ledger_path, out_path = JOBS[port]
    led = json.loads(ledger_path.read_text(encoding="utf-8"))
    queue = [r for r in led["rows"] if r.get("verdict") == "LOGIN_WALL"
             and host(r.get("url")) not in SKIP_HOSTS]
    print(f"[{port}] queue {len(queue)} LOGIN_WALL rows", flush=True)

    tabs = [t for t in targets(port) if t.get("type") == "page"]
    by_host = {}
    for t in tabs:
        h = host(t.get("url"))
        if h and h not in by_host:
            by_host[h] = t

    results = []
    done = 0
    for lr in queue:
        h = host(lr.get("url"))
        t = by_host.get(h)
        if not t:
            res = {"state": "TAB_GONE"}
        else:
            # wake via nav to the row's canonical URL first
            subprocess.run([str(PY), str(CDP), "nav", "--port", str(port),
                            "--tid", t["id"], "--url", lr.get("url")],
                           capture_output=True, text=True, timeout=90)
            time.sleep(4)
            res = run_sso(port, t["id"], lr.get("url"))
        res["url"] = lr.get("url")
        res["host"] = h
        results.append(res)
        done += 1
        # checkpoint
        pathlib.Path(out_path).write_text(
            json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{done}/{len(queue)}]", h.ljust(28), res.get("state"), flush=True)
        time.sleep(4.0)

    # merge states back into the ledger
    from collections import Counter
    merged = 0
    for res in results:
        pref = (res.get("url") or "").split("?")[0].rstrip("/")
        for lr2 in led["rows"]:
            if (lr2.get("url") or "").split("?")[0].rstrip("/") == pref:
                st = res.get("state")
                if st in ("SSO_PROVIDER_SESSION_OBSERVED", "EXISTING_ACCOUNT",
                          "ALREADY_SIGNED_IN"):
                    lr2["verdict"] = "APP_SURFACE"
                    lr2["detail"] = f"re-SSO sweep: {st}"
                elif st in ("SSO_INITIATED",):
                    lr2["detail"] = "SSO_INITIATED at chooser; chooser click exhausted (re-SSO sweep)"
                elif st in ("WALL",):
                    lr2["verdict"] = "WALL"
                    lr2["detail"] = "sso sweep: " + str(res.get("steps", [])[-2:])[:140]
                elif st in ("ALREADY_SIGNED_IN",):
                    lr2["verdict"] = "APP_SURFACE"
                lr2["ssoSweepAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                merged += 1
                break
    led["ssoSweepAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ledger_path.write_text(json.dumps(led, indent=1, ensure_ascii=False), encoding="utf-8")
    print(Counter(r.get("state") for r in results))
    print(f"wrote {out_path}; merged {merged} ledger rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
