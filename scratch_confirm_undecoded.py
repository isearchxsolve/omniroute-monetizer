"""CONFIRM: response arrives but decoder can't read it.

For every captured session, replay once and report:
  - HTTP status + body byte count   (did a response arrive?)
  - keyword '58' present in RAW body?  (is the answer physically in the bytes?)
  - what the structural parser extracted (did our decoder read it?)

If raw has '58' but parser extracted nothing/wrong -> CONFIRMED: response received,
decoder blind. That is exactly the case the keyword-search unlock fixes.
"""
import json, pathlib, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "scripts/automation")

ROOT = pathlib.Path(__file__).resolve().parent
SECRETS = ROOT / "state" / "secrets"
EXPECT = "58"

def keyword_in_body(body, token):
    """Standalone-token match: token not embedded in a longer alphanumeric run."""
    return bool(re.search(r"(?<![0-9A-Za-z])" + re.escape(token) + r"(?![0-9A-Za-z])", body or ""))

from universal_replay import UniversalSessionClient

files = sorted(SECRETS.glob("session_*.json"))
print(f"{'host':30s} {'st':>4s} {'bytes':>7s} {'58raw':>6s} {'parser_got':>10s}  verdict")
print("-" * 100)

for f in files:
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    host = payload.get("host") or "?"
    raw, status, parsed, err = "", None, "", None
    try:
        client = UniversalSessionClient(f)
        res = client.chat([{"role": "user", "content": "Reply with only the number: 41 + 17"}])
        parsed = str((res or {}).get("text") or "")
        status = (res or {}).get("status")
        raw = str((res or {}).get("raw") or "")
    except Exception as e:
        err = str(e)
        raw = getattr(e, "raw", "") or ""
        status = getattr(e, "status", None)

    has58 = keyword_in_body(raw, EXPECT)
    parser_ok = EXPECT in parsed
    if has58 and parser_ok:
        verdict = "DECODED_OK"
    elif has58 and not parser_ok:
        verdict = ">>> RESPONSE_RECEIVED_BUT_UNDECODED <<<"
    elif not raw and err:
        verdict = f"NO_RESPONSE ({err[:40]})"
    else:
        verdict = "no_58_in_body"

    print(f"{host[:30]:30s} {str(status or '-'):>4s} {len(raw):>7d} {('YES' if has58 else 'no'):>6s} "
          f"{('YES' if parser_ok else 'no'):>10s}  {verdict}")
    if has58 and not parser_ok:
        # show the context around the keyword so we SEE the answer in the raw bytes
        i = raw.find(EXPECT)
        print(f"      raw context: ...{raw[max(0,i-60):i+60]}...")
        print(f"      parser returned: {parsed[:80]!r}")
