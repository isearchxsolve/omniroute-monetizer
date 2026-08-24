"""Derive rtst.ai's price law from free quotes. Spends nothing: GET /video/estimate-credits only.

Every (model, duration, quality) the catalogue advertises is quoted once, plus an audio A/B, and the
result is printed as credits and as the ratio credits / (credits_per_second * duration) so a
resolution multiplier -- if that is what it is -- falls out of the table by inspection.
"""
from __future__ import annotations

import pathlib
import sys
from fractions import Fraction

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "automation"))
import rtst_client as rt  # noqa: E402
import video_provider as vp  # noqa: E402
import video_provider_rtst as vpr  # noqa: E402

P = vp.get("rtst")
ACCT = vp.Account("rtst", 9222, "rtst-1")
P.probe(ACCT)
print(f"balance {ACCT.credits} credits, ready={ACCT.ready} ({ACCT.reason})", flush=True)
assert ACCT.ready, "need a live rtst tab to quote"

rows, spent_check = [], ACCT.credits

with rt.Rtst(ACCT.port) as c:
    print("\n-- audio A/B (vidu 3s @540) ---------------------------------", flush=True)
    for audio in (False, True):
        q = c.quote(model="vidu", duration=3, resolution="540", aspect="16:9", audio=audio)
        print(f"  audio={str(audio):<5} -> {q} ", flush=True)

    print("\n-- full grid, audio=False -----------------------------------", flush=True)
    print(f"{'model':<14} {'cps':>3} {'dur':>4} {'qual':>5} {'credits':>7} {'/(cps*dur)':>12}"
          f"  {'cps_in_reply':>12}", flush=True)
    for name, m in P.catalogue.items():
        cps = int(m.get("credits_per_second") or 0)
        durs, quals = P._allowed(name)
        for d in durs:
            for q in quals:
                try:
                    got = c.quote(model=name, duration=d, resolution=str(q),
                                  aspect="16:9", audio=False)
                    cr = got.get("credits_required")
                    reply_cps = got.get("credits_per_second")
                except Exception as e:                        # noqa: BLE001
                    print(f"{name:<14} {cps:>3} {d:>4} {q:>5} {'ERR':>7}  "
                          f"{type(e).__name__}: {str(e)[:60]}", flush=True)
                    continue
                base = cps * d
                ratio = Fraction(cr, base).limit_denominator(64) if base and isinstance(cr, int) \
                    else None
                rows.append((name, cps, d, q, cr, ratio))
                print(f"{name:<14} {cps:>3} {d:>4} {q:>5} {str(cr):>7} {str(ratio):>12}"
                      f"  {str(reply_cps):>12}", flush=True)

print("\n-- ratio by quality (does one multiplier explain every model?) --", flush=True)
by_q: dict[int, set] = {}
for _n, _c, _d, q, _cr, r in rows:
    by_q.setdefault(q, set()).add(r)
for q in sorted(by_q):
    rs = by_q[q]
    print(f"  {q:>5}p -> {sorted(str(x) for x in rs)}"
          f"{'   CONSISTENT' if len(rs) == 1 else '   *** VARIES ***'}", flush=True)

print("\nbalance before grid: %s, after: %s (quotes are free)"
      % (spent_check, ACCT.credits), flush=True)
