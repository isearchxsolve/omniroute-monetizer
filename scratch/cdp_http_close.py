"""Close page targets via the HTTP /json/close endpoint (browser-process side,
doesn't block on hung renderers), then verify what remains. Stdlib only."""
import json
import os
import time
import urllib.request

HOST = "127.0.0.1:9222"
LOG = os.path.join(os.path.dirname(__file__), "attach_run.log")


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def get_json(path):
    with urllib.request.urlopen(f"http://{HOST}{path}", timeout=8) as r:
        return json.loads(r.read())


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    targets = get_json("/json")
    log(f"targets via /json: {len(targets)}")
    for t in targets:
        tid, ttype, url = t["id"], t.get("type"), t.get("url", "")
        log(f"  {ttype:12s} {url[:70]!r} ws={bool(t.get('webSocketDebuggerUrl'))}")
        if ttype == "page":
            try:
                with urllib.request.urlopen(f"http://{HOST}/json/close/{tid}", timeout=8) as r:
                    body = r.read().decode(errors="replace")
                log(f"    HTTP close -> {body!r}")
            except Exception as e:
                log(f"    HTTP close FAILED: {e}")
    time.sleep(1.5)
    # create a fresh page via HTTP endpoint
    try:
        with urllib.request.urlopen(f"http://{HOST}/json/new?about:blank", timeout=8) as r:
            new = json.loads(r.read())
        log(f"new target: {new.get('id')} {new.get('url')!r}")
    except Exception as e:
        log(f"HTTP new FAILED: {e}")
    time.sleep(1)
    targets = get_json("/json")
    log(f"targets after: {len(targets)}")
    for t in targets:
        log(f"  {t.get('type'):12s} {t.get('url', '')[:70]!r}")
    log("DONE")


if __name__ == "__main__":
    main()
