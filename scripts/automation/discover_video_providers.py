"""discover_video_providers.py — find the BREADTH: free AI video generators reachable by Google SSO.

The pool is thin because it points at ~19 hand-listed providers. Thickening is not squeezing more
credits out of rtst.ai; it is raising provider COUNT, because every provider multiplies by every
Google-SSO seat we own:

    providers x google_seats x free_clips_per_account = clips available

3 seats x 50 providers x ~4 clips = ~600 clips, which covers a 30-minute film (360 clips at 5s).

WHY GOOGLE SSO IS THE WHOLE TRICK. A provider that offers "Continue with Google" needs no email, no
OTP, no password and shows no captcha to an aged signed-in profile -- so signup is one click and is
automatable. A provider that only takes email+password+verification is NOT worth the effort and is
skipped. So the single most useful thing this script does is detect the Google SSO button.

STRICTLY READ-ONLY. It performs unauthenticated GETs of public pages (the same bytes a browser would
fetch), extracts candidates from search results and from the listicle pages those results point at,
then scores each candidate. It creates no account, signs nothing in, spends nothing, and sends no
credential. One request at a time per host.

    python discover_video_providers.py                       # search + mine + score, write JSON
    python discover_video_providers.py --no-search            # re-score the known list only
    python discover_video_providers.py --min-score 3          # only report strong candidates
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import html
import json
import pathlib
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Set, Tuple

STATE = pathlib.Path(r"D:\omniroute-monetizer\state")
OUT = STATE / "video_providers_discovered.json"
SEED = pathlib.Path(__file__).with_name("target_sites.json")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9"}

QUERIES = [
    "free AI video generator sign in with Google free credits text to video",
    "AI video generator free credits no credit card 2026 list",
    "best free text to video AI tools free daily credits signup Google",
    "free AI video generator free tier no watermark alternatives Kling Pika",
    "image to video AI free credits sign up with Google account",
    "AI video generator free trial credits without credit card 2026",
    "free AI animation video generator online free credits google login",
    "text to video AI free plan monthly credits list of tools",
]

# Hosts that are never a provider: search/social/news/reviews/repos/marketplaces.
BLOCK = ("google.", "duckduckgo.", "bing.", "youtube.", "youtu.be", "reddit.", "medium.",
         "wikipedia.", "github.", "gitlab.", "twitter.", "x.com", "facebook.", "instagram.",
         "linkedin.", "tiktok.", "pinterest.", "quora.", "g2.com", "capterra.", "trustpilot.",
         "producthunt.", "zapier.", "toolify.", "futurepedia.", "theresanaiforthat.", "aitools.",
         "techcrunch.", "forbes.", "zdnet.", "cnet.", "pcmag.", "tomsguide.", "hostinger.",
         "wordpress.", "shopify.", "wix.", "godaddy.", "namecheap.", "cloudflare.", "vercel.",
         "netlify.", "apple.com", "microsoft.com", "adobe.com", "canva.com", "amazon.",
         "sciencedirect.", "researchgate.", "arxiv.", "substack.", "blogspot.", "notion.",
         "discord.", "telegram.", "whatsapp.", "paypal.", "stripe.", "gumroad.", "patreon.")

# Signals scored on each candidate's own pages.
SSO_PAT = re.compile(
    r"accounts\.google\.com|gsi/client|apis\.google\.com/js/platform|googleusercontent|"
    r"continue\s+with\s+google|sign\s*(?:in|up)\s+with\s+google|log\s*in\s+with\s+google|"
    r"oauth[^\"']{0,20}google|google[^\"']{0,12}oauth|provider=[\"']?google|"
    r"g_id_signin|data-client_id|firebase[^\"']{0,30}auth", re.I)
FREE_PAT = re.compile(
    r"free\s+credits?|no\s+credit\s+card|credit\s*card\s+not\s+required|free\s+trial|"
    r"daily\s+credits?|free\s+plan|free\s+tier|start\s+for\s+free|try\s+(?:it\s+)?free|"
    r"\d+\s+free\s+(?:credits?|generations?|videos?)", re.I)
VIDEO_PAT = re.compile(
    r"text[\s\-]*to[\s\-]*video|image[\s\-]*to[\s\-]*video|ai\s+video\s+generator|"
    r"video\s+generat|generate\s+videos?|ai\s+animation", re.I)
# Anything below is a reason to DEPRIORITISE (walls we refuse to touch).
WALL_PAT = re.compile(
    r"enter\s+your\s+card|billing\s+address|add\s+payment\s+method|phone\s+verification|"
    r"verify\s+your\s+phone|sms\s+code|enterprise\s+only|contact\s+sales\s+to\s+start", re.I)

PROBE_PATHS = ("", "/login", "/signin", "/sign-in", "/pricing")
_host_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _host_lock(host: str) -> threading.Lock:
    with _locks_guard:
        if host not in _host_locks:
            _host_locks[host] = threading.Lock()
        return _host_locks[host]


def fetch(url: str, timeout: int = 20) -> Tuple[int, str]:
    """One unauthenticated GET. Never sends a cookie or credential."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(600_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return r.status, raw.decode(enc, "ignore")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(200_000).decode("utf-8", "ignore")
        except Exception:
            return e.code, ""
    except Exception:
        return 0, ""


def registrable(host: str) -> str:
    host = (host or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def blocked(host: str) -> bool:
    return any(b in host for b in BLOCK)


def search(query: str) -> List[str]:
    """DuckDuckGo's no-JS HTML endpoint. Returns result URLs (ads unwrapped and dropped)."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    st, body = fetch(url, timeout=25)
    if st != 200:
        return []
    urls: List[str] = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"', body):
        href = m.group(1)
        if "uddg=" in href:                                  # DDG redirect wrapper
            got = re.search(r"uddg=([^&]+)", href)
            if got:
                href = urllib.parse.unquote(got.group(1))
        if href.startswith("//duckduckgo.com/y.js") or "ad_provider=" in href:
            continue                                         # sponsored slot, not an organic result
        if href.startswith("http"):
            urls.append(href)
    return urls


def mine_links(url: str) -> List[str]:
    """A 'best free AI video generators' listicle names 10-30 tools. Mining its outbound links is
    the cheapest breadth we can buy -- one fetch yields dozens of candidates."""
    st, body = fetch(url)
    if st != 200 or not body:
        return []
    out: List[str] = []
    for m in re.finditer(r'href="(https?://[^"]+)"', body):
        out.append(m.group(1))
    return out


def score_candidate(host: str) -> dict:
    """Fetch a few public pages and score. No auth, no account, nothing created."""
    rec = {"host": host, "url": f"https://{host}", "alive": False, "status": 0,
           "google_sso": False, "free_signal": False, "is_video": False, "wall_signal": False,
           "sso_evidence": "", "free_evidence": "", "pages": 0, "score": 0}
    with _host_lock(host):                                   # one request at a time per host
        for path in PROBE_PATHS:
            st, body = fetch(f"https://{host}{path}")
            if st == 0:
                continue
            rec["alive"] = True
            rec["status"] = rec["status"] or st
            rec["pages"] += 1
            if not body:
                continue
            if not rec["google_sso"]:
                m = SSO_PAT.search(body)
                if m:
                    rec["google_sso"] = True
                    rec["sso_evidence"] = re.sub(r"\s+", " ", m.group(0))[:60]
            if not rec["free_signal"]:
                m = FREE_PAT.search(body)
                if m:
                    rec["free_signal"] = True
                    rec["free_evidence"] = re.sub(r"\s+", " ", m.group(0))[:60]
            if not rec["is_video"] and VIDEO_PAT.search(body):
                rec["is_video"] = True
            if WALL_PAT.search(body):
                rec["wall_signal"] = True
            if rec["google_sso"] and rec["free_signal"] and rec["is_video"]:
                break                                        # enough; stop poking this host
            time.sleep(0.4)
    rec["score"] = (2 * rec["google_sso"]) + (2 * rec["free_signal"]) + rec["is_video"] \
        - (1 if rec["wall_signal"] else 0)
    return rec


def seed_hosts() -> Set[str]:
    hosts: Set[str] = set()
    try:
        d = json.loads(SEED.read_text(encoding="utf-8-sig"))
        for u in d.get("video_targets", []):
            h = registrable(urllib.parse.urlsplit(u).hostname or "")
            if h and not blocked(h):
                hosts.add(h)
    except Exception:
        pass
    return hosts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-search", action="store_true", help="skip the web sweep; re-score seeds only")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-score", type=int, default=0, help="only print candidates at/above this")
    ap.add_argument("--max-candidates", type=int, default=140)
    a = ap.parse_args()

    candidates: Set[str] = seed_hosts()
    print(f"[seed] {len(candidates)} host(s) from target_sites.json video_targets")

    if not a.no_search:
        listicles: List[str] = []
        for q in QUERIES:
            res = search(q)
            new = 0
            for u in res:
                h = registrable(urllib.parse.urlsplit(u).hostname or "")
                if not h or blocked(h):
                    continue
                if h not in candidates:
                    candidates.add(h)
                    new += 1
                # a long path with listicle words = a roundup page worth mining for outbound tools
                if re.search(r"blog|best|top|free|list|guide|alternativ", u, re.I):
                    listicles.append(u)
            print(f"[search] {new:2d} new  <- {q[:62]}")
            time.sleep(0.8)                                  # polite to the search endpoint

        print(f"[mine] mining {len(listicles[:14])} roundup page(s) for outbound tool links...")
        for u in listicles[:14]:
            got = mine_links(u)
            new = 0
            for link in got:
                h = registrable(urllib.parse.urlsplit(link).hostname or "")
                if not h or blocked(h) or h in candidates:
                    continue
                candidates.add(h)
                new += 1
            if new:
                print(f"[mine] +{new:3d} from {urllib.parse.urlsplit(u).hostname}")
            time.sleep(0.3)

    cands = sorted(candidates)[: a.max_candidates]
    print(f"\n[score] scoring {len(cands)} candidate host(s) — unauthenticated GETs only...\n")
    results: List[dict] = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rec in ex.map(score_candidate, cands):
            results.append(rec)

    results.sort(key=lambda r: (-r["score"], r["host"]))
    keep = [r for r in results if r["alive"] and r["is_video"] and r["score"] >= a.min_score]

    print(f"{'host':34s} {'score':>5s}  sso  free  video  wall")
    for r in keep:
        print(f"{r['host']:34s} {r['score']:5d}  "
              f"{'YES' if r['google_sso'] else ' - ':3s}  "
              f"{'YES' if r['free_signal'] else ' - ':4s}  "
              f"{'YES' if r['is_video'] else ' - ':5s}  "
              f"{'wall' if r['wall_signal'] else ' - '}")

    sso_free = [r for r in keep if r["google_sso"] and r["free_signal"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": int(time.time()),
        "method": "unauthenticated public-page scoring; no account created, nothing spent",
        "counts": {"candidates": len(cands), "alive_video": len(keep), "sso_and_free": len(sso_free)},
        "providers": results,
    }, indent=2), encoding="utf-8")

    print(f"\n  {len(cands)} scanned -> {len(keep)} live video tools -> "
          f"{len(sso_free)} with BOTH Google SSO and a free-tier signal")
    print(f"  wrote {OUT}")
    print("\n  Next: SSO-sweep the sso_and_free set across the Google-live profiles, then one\n"
          "  sentinel capture per provider (record_video_job.py). No adapters -- "
          "video_universal_replay handles the shape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
