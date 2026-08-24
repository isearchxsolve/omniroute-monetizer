"""rtst_client.py -- rtst.ai video route: quote, submit, poll, download.

WHY rtst.ai FIRST: of the twelve logged-in AI-video tabs in the automation profile, this is the only
one that is simultaneously (a) genuinely authenticated, (b) a plain REST API with a bearer token
rather than a request-signing scheme, and (c) willing to tell you the price BEFORE you commit.
That last property is the important one. `GET /video/estimate-credits` returns

    {credits_required, credits_per_second, current_balance, can_afford, allowed_durations}

so every cost question can be settled for free. Compare Google Flow, where the only way to learn a
price was to spend 20 credits and diff the balance.

MONEY DISCIPLINE. `submit` is the only command that can spend a credit, and it refuses to run unless
BOTH hold:
  * --confirm-spend is passed explicitly, and
  * a fresh quote says can_afford is true and credits_required <= --max-spend.
Everything else here is read-only. A submit is not idempotent and the API has no idempotency key, so
submit never retries on its own -- a retry is a second charge, and that decision is the operator's.

SECRETS. The bearer JWT lives in the browser's localStorage under `auth_token`. It is read INSIDE the
page and used there; it is never returned across the CDP boundary, never printed, never written to
disk. Responses are scrubbed before display. Cookie values are never touched at all.

    python rtst_client.py doctor
    python rtst_client.py models
    python rtst_client.py quote --model vidu --duration 3 --resolution 540
    python rtst_client.py submit --prompt "a lighthouse in a storm" --model vidu \
                                --duration 3 --resolution 540 --confirm-spend --max-spend 6
    python rtst_client.py wait <video_id>
    python rtst_client.py download <video_id>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp import Page  # noqa: E402

API = "https://api.rtst.ai"
TAB = "rtst.ai"                                     # substring identifying the logged-in tab
DEFAULT_PORT = 9222
OUT_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "rtst"

SECRET_RE = re.compile(r"(ya29\.[\w\-.]+|AIza[\w\-]{10,}|1//[\w\-]{10,}|eyJ[\w\-]{18,}"
                       r"|Bearer\s+[\w\-.]{20,})")

# Terminal states seen from /video/{id}. Anything else is treated as still running.
DONE = {"completed", "complete", "success", "succeeded", "finished", "done"}
FAILED = {"failed", "error", "cancelled", "canceled", "rejected"}

# One in-page fetch, used for every call. Keeping this single-sourced matters: it is the only place
# the token is handled, so there is exactly one thing to audit.
FETCH_JS = r"""
(async (base, path, method, body) => {
  const h = {'Accept': 'application/json'};
  let t = '';
  try { t = localStorage.getItem('auth_token') || ''; } catch (e) {}
  t = t.replace(/^"|"$/g, '');
  if (t) h['Authorization'] = t.startsWith('Bearer ') ? t : 'Bearer ' + t;
  const opt = {method: method, credentials: 'include', headers: h};
  if (body !== null) { h['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  try {
    const r = await fetch(base + path, opt);
    const txt = await r.text();
    return JSON.stringify({status: r.status, tokenPresent: !!t, body: txt.slice(0, 200000)});
  } catch (e) {
    return JSON.stringify({status: 0, tokenPresent: !!t, error: String(e).slice(0, 160)});
  }
})(%s, %s, %s, %s)
"""


def scrub(s: str) -> str:
    return SECRET_RE.sub("[REDACTED]", s)


class Rtst:
    """Thin wrapper around one CDP page. Open once, make many calls."""

    def __init__(self, port: int = DEFAULT_PORT, tab: str = TAB):
        self.port, self.tab = port, tab
        self._pg = None

    def __enter__(self):
        self._pg = Page(self.tab, port=self.port).__enter__()
        return self

    def __exit__(self, *exc):
        return self._pg.__exit__(*exc) if self._pg else None

    def call(self, path: str, method: str = "GET", body=None, timeout: int = 90) -> dict:
        raw = self._pg.evaluate(FETCH_JS % (json.dumps(API), json.dumps(path),
                                            json.dumps(method), json.dumps(body)),
                                timeout=timeout)
        r = json.loads(raw)
        if not r.get("tokenPresent"):
            raise RuntimeError("no auth_token in the rtst.ai tab -- the profile is signed out; "
                              "sign in manually, this tool will not type a password")
        if r.get("status") == 0:
            raise RuntimeError(f"network error calling {path}: {r.get('error')}")
        try:
            r["json"] = json.loads(r["body"])
        except Exception:
            r["json"] = None
        return r

    # ---- read-only ---------------------------------------------------------------------------
    def credits(self) -> int:
        r = self.call("/user/credits")
        j = r.get("json") or {}
        if not j.get("success"):
            raise RuntimeError(f"/user/credits failed: HTTP {r['status']} {scrub(r['body'])[:160]}")
        return int(j.get("credits") or 0)

    def models(self) -> list:
        r = self.call("/videomodel")
        j = r.get("json") or {}
        if not j.get("success"):
            raise RuntimeError(f"/videomodel failed: HTTP {r['status']} {scrub(r['body'])[:160]}")
        return j.get("data") or []

    def quote(self, *, model: str, duration: int, resolution: int, aspect: str = "16:9",
              audio: bool = False) -> dict:
        # Note the "p" suffix: the site's own client appends it, and the API rejects a bare number.
        q = (f"/video/estimate-credits?model={model}&duration={duration}"
             f"&resolution={resolution}p&audio={'true' if audio else 'false'}"
             f"&aspect_ratio={aspect}")
        r = self.call(q)
        j = r.get("json") or {}
        if not j.get("success"):
            raise RuntimeError(f"quote refused: HTTP {r['status']} {scrub(r['body'])[:200]}")
        return j["data"]

    def status(self, vid: str) -> dict:
        r = self.call(f"/video/{vid}")
        j = r.get("json") or {}
        if not j.get("success"):
            raise RuntimeError(f"/video/{vid}: HTTP {r['status']} {scrub(r['body'])[:200]}")
        d = j.get("data")
        return d if isinstance(d, dict) else j

    # ---- the one command that spends ---------------------------------------------------------
    def submit(self, *, prompt: str, model: str, duration: int, resolution: int,
               aspect: str = "16:9", audio: bool = False) -> dict:
        body = {"prompt": prompt, "model": model, "duration": duration,
                "resolution": f"{resolution}p", "aspect_ratio": aspect, "audio": audio}
        r = self.call("/video/create", method="POST", body=body, timeout=180)
        j = r.get("json") or {}
        if r["status"] >= 400 or not j.get("success"):
            raise RuntimeError(f"submit refused: HTTP {r['status']} {scrub(r['body'])[:400]}")
        return j.get("data") or j


def pick_url(d: dict) -> str | None:
    """The result URL's field name is not documented; take the first plausible one."""
    for k in ("video_url", "url", "output_url", "download_url", "result_url", "video", "output"):
        v = d.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    for v in d.values():                                    # one level down, e.g. {"output": {...}}
        if isinstance(v, dict):
            got = pick_url(v)
            if got:
                return got
    return None


def cmd_doctor(a) -> int:
    with Rtst(a.port) as c:
        bal = c.credits()
        ms = c.models()
        print(f"auth        ok (bearer present in tab, value never left the browser)")
        print(f"balance     {bal} credits  (authoritative -- page text said 412 and was wrong)")
        print(f"models      {len(ms)} video model(s)")
        cheapest = None
        for m in ms:
            durs = m.get("duration") or []
            quals = [int(str(q)) for q in (m.get("video_quality") or []) if str(q).isdigit()]
            if not durs or not quals:
                continue
            try:
                q = c.quote(model=m["name"], duration=min(durs), resolution=min(quals))
            except Exception as e:
                print(f"  {m['name']:<16} quote failed: {str(e)[:70]}")
                continue
            tag = "affordable" if q.get("can_afford") else "TOO EXPENSIVE"
            print(f"  {m['name']:<16} {min(durs)}s @{min(quals)}p = "
                  f"{q['credits_required']} credits   {tag}")
            if q.get("can_afford") and (cheapest is None
                                        or q["credits_required"] < cheapest[1]):
                cheapest = (m["name"], q["credits_required"], min(durs), min(quals))
        if cheapest:
            print(f"\ncheapest affordable proof run: {cheapest[0]} {cheapest[2]}s @{cheapest[3]}p "
                  f"= {cheapest[1]} credits ({bal // cheapest[1]} run(s) available)")
        else:
            print("\nNOTHING is affordable at this balance -- top up before submitting.")
    return 0


def cmd_models(a) -> int:
    with Rtst(a.port) as c:
        ms = c.models()
    print(f"{'name':<16}{'title':<24}{'c/s':>4}  {'durations':<26}quality")
    print("-" * 92)
    for m in ms:
        print(f"{m['name'][:15]:<16}{m['title'][:23]:<24}{m.get('credits_per_second', 0):>4}  "
              f"{str(m.get('duration'))[:25]:<26}{str(m.get('video_quality'))[:24]}")
    return 0


def cmd_credits(a) -> int:
    with Rtst(a.port) as c:
        print(f"{c.credits()} credits")
    return 0


def cmd_quote(a) -> int:
    with Rtst(a.port) as c:
        q = c.quote(model=a.model, duration=a.duration, resolution=a.resolution,
                    aspect=a.aspect, audio=a.audio)
    print(json.dumps(q, indent=1))
    return 0 if q.get("can_afford") else 1


def cmd_contract(a) -> int:
    """Learn the exact validation contract of POST /video/create WITHOUT any risk of a charge.

    The trick: send a well-formed request for something we demonstrably cannot afford. The server
    must reject it, so no video can be created, yet the rejection reveals field-level validation.
    Any missing-field or bad-value errors surface before the balance check."""
    with Rtst(a.port) as c:
        bal = c.credits()
        ms = {m["name"]: m for m in c.models()}
        # Most expensive thing on the menu, so "insufficient credits" is guaranteed.
        pick, cost = None, -1
        for m in ms.values():
            durs = [int(d) for d in (m.get("duration") or [])]
            quals = [int(str(q)) for q in (m.get("video_quality") or []) if str(q).isdigit()]
            if not durs or not quals:
                continue
            est = max(durs) * (m.get("credits_per_second") or 0)
            if est > cost:
                pick, cost = (m["name"], max(durs), max(quals)), est
        if pick is None:
            print("no model has usable duration/quality metadata")
            return 1
        q = c.quote(model=pick[0], duration=pick[1], resolution=pick[2], audio=True)
        print(f"balance {bal}; probing with {pick[0]} {pick[1]}s @{pick[2]}p = "
              f"{q['credits_required']} credits, can_afford={q.get('can_afford')}")
        if q.get("can_afford"):
            print("REFUSING to probe: this request is affordable, so it might actually succeed "
                  "and charge. Contract probing is only safe when the request cannot be paid for.")
            return 1
        try:
            # >= 10 words: the API enforces a minimum prompt length BEFORE it checks the balance,
            # so a short prompt would stop the probe early and hide the rest of the contract.
            got = c.submit(prompt="a contract probe request that must be rejected for having "
                                  "insufficient credits available on this account",
                           model=pick[0], duration=pick[1], resolution=pick[2], audio=True)
            print("!! UNEXPECTED SUCCESS -- the server accepted an unaffordable request:")
            print(scrub(json.dumps(got))[:600])
            return 1
        except RuntimeError as e:
            print("\nrejection (this is the contract):")
            print(scrub(str(e))[:900])
    return 0


def cmd_submit(a) -> int:
    with Rtst(a.port) as c:
        q = c.quote(model=a.model, duration=a.duration, resolution=a.resolution,
                    aspect=a.aspect, audio=a.audio)
        need = int(q["credits_required"])
        print(f"quote: {need} credits, balance {q.get('current_balance')}, "
              f"can_afford={q.get('can_afford')}")
        if not q.get("can_afford"):
            print("refusing: cannot afford this request")
            return 1
        if need > a.max_spend:
            print(f"refusing: quote {need} exceeds --max-spend {a.max_spend}")
            return 1
        if not a.confirm_spend:
            print(f"DRY RUN -- would charge {need} credits. Re-run with --confirm-spend to submit.")
            return 0

        before = c.credits()
        got = c.submit(prompt=a.prompt, model=a.model, duration=a.duration,
                       resolution=a.resolution, aspect=a.aspect, audio=a.audio)
        vid = str(got.get("id") or got.get("video_id") or got.get("uuid") or "")
        print(f"submitted: id={vid or '(none in response)'}")
        if not vid:
            print("response was:", scrub(json.dumps(got))[:500])

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"id": vid, "model": a.model, "prompt": a.prompt, "duration": a.duration,
               "resolution": a.resolution, "quoted": need, "credits_before": before,
               "submitted_at": int(time.time()), "raw": got}
        with (OUT_DIR / "jobs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(scrub(json.dumps(rec)) + "\n")

        if not vid:
            return 1
        final = wait_loop(c, vid, a.budget)
        after = c.credits()
        print(f"credits {before} -> {after} (charged {before - after}, quoted {need})")
        url = pick_url(final)
        print("result url:", (url or "(none yet)")[:120])
        return 0 if url else 1


def wait_loop(c: Rtst, vid: str, budget: int) -> dict:
    deadline, last = time.time() + budget, None
    while time.time() < deadline:
        d = c.status(vid)
        st = str(d.get("status") or d.get("state") or "").lower()
        if st != last:
            print(f"  [{int(time.time() - (deadline - budget)):>4}s] {st or '(no status field)'}")
            last = st
        if st in DONE or pick_url(d):
            return d
        if st in FAILED:
            raise RuntimeError(f"generation failed: {scrub(json.dumps(d))[:300]}")
        time.sleep(6)
    raise RuntimeError(f"still not finished after {budget}s; the credits are already spent -- "
                       f"poll again with: rtst_client.py wait {vid}")


def cmd_wait(a) -> int:
    with Rtst(a.port) as c:
        d = wait_loop(c, a.id, a.budget)
    print("result url:", (pick_url(d) or "(none)")[:140])
    return 0


def cmd_download(a) -> int:
    with Rtst(a.port) as c:
        d = c.status(a.id)
    url = pick_url(d)
    if not url:
        print(f"no downloadable url yet; status={d.get('status')}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = pathlib.Path(a.out) if a.out else OUT_DIR / f"{a.id}.mp4"
    with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as fh:
        fh.write(r.read())
    head = dest.open("rb").read(64)
    print(f"{dest}  {dest.stat().st_size:,} bytes  "
          f"{'looks like MP4' if b'ftyp' in head else 'UNRECOGNISED container'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="read-only end-to-end check, incl. cheapest affordable run")
    sub.add_parser("models", help="list video models and per-second pricing")
    sub.add_parser("credits", help="authoritative balance from /user/credits")
    sub.add_parser("contract", help="learn POST /video/create validation with zero charge risk")

    def gen_args(p, with_prompt=False):
        if with_prompt:
            p.add_argument("--prompt", required=True)
        p.add_argument("--model", required=True)
        p.add_argument("--duration", type=int, required=True)
        p.add_argument("--resolution", type=int, required=True)
        p.add_argument("--aspect", default="16:9")
        p.add_argument("--audio", action="store_true")

    gen_args(sub.add_parser("quote", help="free price check"))
    s = sub.add_parser("submit", help="SPENDS CREDITS -- requires --confirm-spend")
    gen_args(s, with_prompt=True)
    s.add_argument("--confirm-spend", action="store_true",
                   help="without this the command only prints the quote")
    s.add_argument("--max-spend", type=int, default=10,
                   help="hard ceiling; a quote above this aborts (default 10)")
    s.add_argument("--budget", type=int, default=600)

    w = sub.add_parser("wait", help="poll an existing job")
    w.add_argument("id")
    w.add_argument("--budget", type=int, default=600)

    dl = sub.add_parser("download", help="fetch a finished video")
    dl.add_argument("id")
    dl.add_argument("--out")

    a = ap.parse_args()
    fn = {"doctor": cmd_doctor, "models": cmd_models, "credits": cmd_credits, "quote": cmd_quote,
          "contract": cmd_contract, "submit": cmd_submit, "wait": cmd_wait,
          "download": cmd_download}[a.cmd]
    try:
        return fn(a)
    except RuntimeError as e:
        print(f"error: {scrub(str(e))[:600]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
