"""sweep_sites.py -- close out the remaining AI-video tabs: is each one actually usable?

For every site named on the command line this answers the same three questions, all read-only:

  1. Is this browser really signed in?  Decided by what the site's OWN API says, not by page text.
     Page text lied about two of three sites already (rtst.ai rendered 412 credits against a real 30;
     topmediai rendered 3,000 while its API answered "Unlogin").
  2. What is the real balance?  Found by discovering the site's balance endpoint from its JS bundle
     and calling it.
  3. Is there a submit contract worth wiring?  Reported as the generate/poll endpoints found.

Nothing is submitted and no credit is spent. Bearer tokens are read and used inside the page; only
their length and JWT-ness ever cross back. Cookie names only.

    python sweep_sites.py flux-ai.io akool.com teamily.ai
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402
from site_probe import DISCOVER_JS, GET_JS, scrub  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "probes"

# Endpoints that answer "who am I / what do I have left". Ordered: the most likely first.
BALANCE_RE = re.compile(r"(credit|balance|quota|remain|point|/user/info|/user/me|/me$|"
                        r"user/profile|subscription|benefit|wallet)", re.I)
# Endpoints that would be the actual route.
SUBMIT_RE = re.compile(r"(generat|/create|submit|/task|/job|/queue|render|txt2|t2v|i2v)", re.I)

# "Signed out" is stated in prose by almost every API that bothers to answer at all. Note that many
# of these answer HTTP 200 and put the failure in a body `code` field, so status alone proves nothing:
# akool returns 200 with {"code":1002,"msg":"authorization cannot be empty"}.
SIGNED_OUT_RE = re.compile(r"(unlogin|not.?log(ged|in)|login expired|unauthori[sz]ed|please log in|"
                           r"no.?session|session can'?t be nil|token.{0,12}(invalid|expired|missing)|"
                           r"authorization.{0,24}(empty|missing|required|invalid)|"
                           r"auth.{0,16}(required|missing|empty)|no.{0,6}permission|"
                           r"forbidden|need.{0,10}login|tourist|guest|登录)", re.I)


# Which discovered path to try first. A bundle mentions hundreds; the ones that answer with a balance
# are API routes, not page routes. teamily.ai's /credit-usage is a Next.js page that 500s on a JSON
# request, while its real endpoint lives under /userCenter/api/v1/ -- so score API shape ahead of a
# merely credit-sounding name.
def rank(p: str) -> tuple:
    return (0 if re.search(r"/(api|interface|v\d+)(/|$)", p) else 1,
            0 if re.search(r"(credit|balance|quota|point|wallet)", p, re.I) else 1,
            len(p))


# A balance endpoint answers with JSON. An HTML page is a marketing route that merely happens to be
# named /pricing or /subscription-terms, and treating one as proof of login is how you get a false
# AUTHENTICATED verdict.
def is_json_body(b: str) -> bool:
    s = (b or "").lstrip()
    return bool(s) and s[0] in "{["


# The browser's own record of what the page already called. These beat bundle-extracted guesses: they
# are real, live endpoints on whatever host the site actually uses, including third-party ones.
OBSERVED_JS = r"""
(() => {
  const out = [];
  for (const r of (performance.getEntriesByType('resource') || [])) {
    if (r.initiatorType !== 'xmlhttprequest' && r.initiatorType !== 'fetch') continue;
    let u; try { u = new URL(r.name); } catch (e) { continue; }
    if (/\.(js|css|png|jpe?g|svg|woff2?|webp|gif|mp4)$/i.test(u.pathname)) continue;
    out.push(u.origin + u.pathname + (u.search || ''));
  }
  return JSON.stringify([...new Set(out)].slice(0, 60));
})()
"""


def sweep(match: str, api: str, port: int = 9222, do_reload: bool = False) -> dict:
    row: dict = {"site": match, "api": api}
    with Page(match, port=port) as pg:
        if do_reload:
            # Some of these tabs have been open for hours, so their performance buffer no longer holds
            # the XHRs the app fired at startup -- and those are the only reliable record of endpoints
            # the bundle builds from template strings. A reload replays exactly the requests the app
            # makes on its own. It is navigation only: nothing is clicked, no form is submitted, no
            # generate button is touched, so it cannot spend a credit.
            try:
                pg.send("Page.reload", {"ignoreCache": False}, timeout=60)
            except BaseException as e:
                print(f"  (reload refused: {type(e).__name__}; continuing with the live page)")
            for _ in range(30):
                time.sleep(1)
                try:
                    if pg.evaluate("document.readyState", timeout=10) in ("interactive", "complete"):
                        break
                except BaseException:
                    continue
            time.sleep(12)                              # let the load-time XHRs actually fire

        d = json.loads(pg.evaluate(DISCOVER_JS % (json.dumps(api), json.dumps([])), timeout=240))
        keys = d.get("authKeys") or []
        row["authKey"] = (f"{keys[0]['key'][:34]} ({keys[0]['len']} chars"
                          f"{', jwt' if keys[0]['jwt'] else ''})") if keys else None
        row["hosts"] = d.get("hosts") or []
        paths = d.get("paths") or []
        row["scanned"] = (f"{d.get('scripts')}/{d.get('scriptsSeen')} script(s) read, "
                          f"{d.get('bytes', 0):,} bytes, {len(paths)} paths")
        row["fetchErrors"] = (d.get("errors") or [])[:3]
        row["submitEndpoints"] = [p for p in paths if SUBMIT_RE.search(p)][:8]

        observed = json.loads(pg.evaluate(OBSERVED_JS, timeout=60))
        row["observedAll"] = observed[:40]              # the app's real endpoint list: worth keeping
        row["observed"] = [o for o in observed if BALANCE_RE.search(o)][:6]

        # Absolute observed URLs first (known-real), then bundle-extracted paths worth trying.
        # DISCOVER_JS also records http-client call sites as "GET /foo"; those are stronger evidence
        # than a bare quoted string, since something in the code actually calls them.
        called = [c.split(" ", 1)[1] for c in (d.get("calls") or [])
                  if c.startswith("GET /") and "${" not in c]
        pool = {p for p in paths + called if BALANCE_RE.search(p) and "${" not in p}
        ranked = sorted(pool, key=rank)
        # A path found in the bundle does not have to live on the page's host. teamily.ai serves a
        # Next.js frontend that answers every JSON request with 500 "Only HTML requests are supported
        # here" -- the same paths on open.teamily.ai are the real API. So try the hosts the bundle
        # itself named, skipping docs/help/staging copies.
        #
        # The page's OWN origin goes first, and matters more than it looks: a request there is
        # same-origin, so CORS cannot refuse it. Using the CLI name instead ("heygen.com" for a tab on
        # app.heygen.com) turns every call cross-origin and every result into "Failed to fetch",
        # which reads like a dead site when it is really a self-inflicted wound.
        origin = (d.get("origin") or f"https://{api}").rstrip("/")
        row["origin"] = origin
        bases = [origin] + [f"https://{h}" for h in ([api] + row["hosts"])
                            if f"https://{h}" != origin
                            and not re.search(r"(docs|help|blog|test|staging|cdn|assets?|i18n)", h)][:2]
        cands = row["observed"] + [f"{b}{p}" for p in ranked[:5] for b in bases]
        row["balanceTried"] = []
        for path in cands:
            url = path if path.startswith("http") else f"https://{api}{path}"
            hit = False
            for creds in ("include", "omit"):
                js = GET_JS % (json.dumps(""), json.dumps(url),
                               json.dumps(keys[0]["key"] if keys else None))
                # GET_JS always sends credentials:'include'; a wildcard-CORS API rejects that, so
                # retry without. Patch the literal rather than duplicating the whole snippet.
                if creds == "omit":
                    js = js.replace("credentials: 'include'", "credentials: 'omit'")
                # One endpoint that never answers must not cost the whole site its verdict.
                try:
                    r = json.loads(pg.evaluate(js, timeout=90))
                except BaseException as e:
                    r = {"status": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
                body = (r.get("body") or r.get("error") or "")[:400]
                row["balanceTried"].append({"path": url, "creds": creds,
                                            "status": r.get("status"), "body": scrub(body),
                                            "json": is_json_body(body)})
                if r.get("status") == 200 and is_json_body(body):
                    hit = True
                    break
            # A JSON 200 is decisive either way: it either names a balance or says we are signed out.
            if hit or len(row["balanceTried"]) >= 14:
                break
    # Verdict from the evidence, not from the page.
    ok = [t for t in row["balanceTried"] if t["status"] == 200 and t["json"]]
    # Two independent signals for "not signed in": the structural one (an API answering 401/403 has
    # said so definitively) and the prose one (many APIs answer HTTP 200 and bury the failure in a
    # body code -- akool returns 200 {"code":1002,"msg":"authorization cannot be empty"}).
    said_out = [t for t in row["balanceTried"]
                if t["status"] in (401, 403) or SIGNED_OUT_RE.search(t["body"] or "")]
    live = [t for t in ok if not SIGNED_OUT_RE.search(t["body"] or "")]
    if live:
        row["verdict"] = "AUTHENTICATED"
        row["evidence"] = f"{live[0]['path']} -> {live[0]['body'][:220]}"
    elif said_out:
        row["verdict"] = "SIGNED OUT"
        row["evidence"] = f"{said_out[0]['path']} -> HTTP {said_out[0]['status']} {said_out[0]['body'][:160]}"
    elif not row["balanceTried"]:
        row["verdict"] = "NO BALANCE ENDPOINT FOUND"
        row["evidence"] = (f"{row['scanned']}; {len(row['submitEndpoints'])} submit-shaped path(s)"
                           + (f"; fetch errors: {row['fetchErrors']}" if row["fetchErrors"] else ""))
    else:
        row["verdict"] = "UNDETERMINED"
        s = row["balanceTried"][0]
        row["evidence"] = f"{s['path']} -> HTTP {s['status']} {s['body'][:140]}"
    return row


def main() -> int:
    argv = sys.argv[1:]
    do_reload = "--reload" in argv
    targets = [a for a in argv if not a.startswith("--")]
    if not targets:
        print(__doc__)
        return 2
    rows = []
    for t in targets:
        match, _, api = t.partition("=")
        try:
            rows.append(sweep(match, api or match, do_reload=do_reload))
        except BaseException as e:                      # SystemExit from pick_page included
            rows.append({"site": match, "verdict": "PROBE FAILED",
                         "evidence": f"{type(e).__name__}: {str(e)[:110]}"})
        r = rows[-1]
        print(f"\n{'=' * 92}\n{r['site']}   ->   {r['verdict']}")
        if r.get("authKey"):
            print(f"  auth material : {r['authKey']}")
        if r.get("hosts"):
            print(f"  api hosts     : {', '.join(r['hosts'][:5])}")
        if r.get("observedAll"):
            print(f"  live xhr      : {len(r['observedAll'])} seen, e.g. "
                  f"{', '.join(u[:64] for u in r['observedAll'][:3])}")
        if r.get("submitEndpoints"):
            print(f"  submit-shaped : {', '.join(r['submitEndpoints'][:6])}")
        print(f"  evidence      : {r.get('evidence', '')[:400]}")

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "sweep.json"
    prev = []
    if dest.exists():
        try:
            prev = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:
            prev = []
    keep = [p for p in prev if p.get("site") not in {r["site"] for r in rows}]
    dest.write_text(json.dumps(keep + rows, indent=1), encoding="utf-8")
    print(f"\nsaved -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
