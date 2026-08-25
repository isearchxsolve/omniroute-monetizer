"""Read-only survey of the 11 target sites in the running (niloy-clone) Chrome on :9222.

Opens each target, waits for load, probes auth/wall/input state via injected JS,
then closes the tab. Prints a compact table. NEVER interacts with walls, never types,
never submits. Pure recon so we know which targets are harvest-ready vs login/wall-gated.
"""
import json, sys, time, pathlib, urllib.request
from urllib.parse import urlsplit

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

PORT = 9222
TARGETS_FILE = pathlib.Path(r"D:\omniroute-monetizer\target_sites.json")

PROBE = r"""(() => {
  const txt = (document.body ? document.body.innerText : '') || '';
  const low = txt.toLowerCase();
  const hasInput = !!document.querySelector('textarea,[contenteditable=true],input[type=text],input[type=search],[role=textbox]');
  const signin = /(^|\b)(sign in|log in|sign up|continue with google|get started free)\b/i.test(txt);
  const signed = /(sign out|log out|my account|dashboard|credits left|my profile|log ?out)/i.test(txt);
  const walls = ['captcha','verify you are human','are you a robot','enter your card',
    'payment method','add a card','credit card','out of credits','upgrade to','start free trial',
    'verification code','phone number','subscribe'].filter(w => low.includes(w));
  return JSON.stringify({url: location.href.slice(0,60), hasInput, signin, signed, walls});
})()"""


def load_targets():
    import re
    raw = TARGETS_FILE.read_bytes()
    text = None
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        raise SystemExit("could not decode target_sites.json")
    # tolerate unquoted / hand-edited list: pull URLs by regex
    urls = re.findall(r"https?://[^\s,\"'\]]+", text)
    seen, out = set(), []
    for u in urls:
        u = u.rstrip("/") or u
        if u not in seen:
            seen.add(u); out.append(u)
    if not out:
        raise SystemExit("no URLs found in target_sites.json")
    return out


def open_tab(url):
    for m in ("PUT", "GET"):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{url}", method=m)
            return json.loads(urllib.request.urlopen(req, timeout=15).read())["id"]
        except Exception:
            pass
    return None


def close_tab(tid):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{tid}", timeout=8)
    except Exception:
        pass


def main():
    targets = load_targets()
    print(f"surveying {len(targets)} targets\n")
    print(f"  {'HOST':<26}{'IN':<4}{'SIGNIN':<8}{'SIGNED':<8}{'WALLS'}")
    print("  " + "-" * 70)
    for url in targets:
        host = (urlsplit(url).hostname or url).replace("www.", "")
        tid = open_tab(url)
        if not tid:
            print(f"  {host:<26}open-failed")
            continue
        time.sleep(8)
        try:
            with Page(host.split(".")[0], port=PORT) as p:
                r = json.loads(p.evaluate(PROBE) or "{}")
            inp = "yes" if r.get("hasInput") else "-"
            si = "SIGNIN" if r.get("signin") else "-"
            sg = "SIGNED" if r.get("signed") else "-"
            walls = ",".join(r.get("walls", [])) or "-"
            print(f"  {host:<26}{inp:<4}{si:<8}{sg:<8}{walls[:34]}")
        except Exception as e:
            print(f"  {host:<26}probe-err {type(e).__name__}: {str(e)[:40]}")
        finally:
            close_tab(tid)
    print("\n  IN=has text input  SIGNIN=login CTA present  SIGNED=signed-in marker  WALLS=card/captcha/quota")


if __name__ == "__main__":
    main()
