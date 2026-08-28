"""Diagnose the 3 CDP-hang video seats (heygen/magichour/giz).

Hypothesis: the tabs are FROZEN/DISCARDED by Chrome memory-saver, so Runtime.evaluate
never answers regardless of timeout. Test: bringToFront + trivial evaluate.
Read-only w.r.t. provider state (no clicks, no submits).
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

lines = []
for match in ("heygen.com", "magichour.ai", "giz.ai"):
    port = None
    tgt = None
    for p in (9222, 9223, 9224, 9225):
        try:
            for t in list_targets(port=p):
                if t.get("type") == "page" and match in (t.get("url") or ""):
                    port, tgt = p, t
                    break
        except Exception:
            continue
        if tgt:
            break
    if not tgt:
        lines.append(f"{match:14s} NO_TAB")
        continue
    lines.append(f"{match:14s} :{port} url={tgt.get('url','')[:70]} title={str(tgt.get('title',''))[:40]!r}")
    try:
        with Page(match=match, timeout=15, port=port) as pg:
            # 1) trivial evaluate BEFORE waking — does it hang?
            t0 = time.time()
            try:
                v = pg.evaluate("1+1", timeout=8)
                lines.append(f"   pre-wake evaluate 1+1 -> {v} in {time.time()-t0:.1f}s  (NOT frozen)")
                frozen = False
            except TimeoutError:
                lines.append(f"   pre-wake evaluate 1+1 HUNG >8s  (frozen/discarded suspected)")
                frozen = True
            # 2) wake it
            try:
                pg.send("Page.bringToFront", timeout=10)
                lines.append("   bringToFront -> ok")
            except Exception as e:
                lines.append(f"   bringToFront -> {type(e).__name__}: {str(e)[:60]}")
            time.sleep(1.5)
            # 3) trivial evaluate AFTER waking
            t0 = time.time()
            try:
                v = pg.evaluate("1+1", timeout=10)
                lines.append(f"   post-wake evaluate 1+1 -> {v} in {time.time()-t0:.1f}s")
            except TimeoutError:
                lines.append(f"   post-wake evaluate 1+1 STILL HUNG >10s")
            except Exception as e:
                lines.append(f"   post-wake evaluate -> {type(e).__name__}: {str(e)[:60]}")
    except Exception as e:
        lines.append(f"   ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_cdp_freeze_diag.txt").write_text(
    report, encoding="utf-8")
