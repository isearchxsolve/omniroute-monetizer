"""CHATX stateless 2-leg replay via curl_cffi (chrome-free, no Selenium/Chrome).

Leg 0: GET https://chatx.ai/gpt -> fresh cookies + CSRF from meta[name=csrf-token].
Leg 1: POST /sendchat (form: fresh _token + prompt) -> conversions_id + ass_conversions_id.
Leg 2: GET /chats_stream?... (SSE) -> accumulate deltas until sentinel/answer.

Uses the seat's recorded cookie_header as the starting jar (cf_clearance etc.),
lets curl_cffi's cookiejar absorb Set-Cookie from leg 0. Chrome TLS impersonation.
"""
import json, re, sys, time, urllib.parse
from pathlib import Path
from curl_cffi.requests import Session as CCSession

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEAT = Path(r"d:\omniroute-monetizer\state\secrets\session_chatx.json")
PROMPT = "Reply exactly one word: Omni."
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def main():
    d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
    rx = d["recorded_exchange"]
    base_cookie = d.get("cookie_header", "")
    rec_fields = dict(urllib.parse.parse_qsl(rx.get("request_body", "")))

    s = CCSession(impersonate="chrome")
    # seed the jar with the recorded cookies
    for part in base_cookie.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            s.cookies.set(k.strip(), v.strip(), domain="chatx.ai")

    hdr_common = {
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://chatx.ai/gpt",
    }

    # ---- LEG 0: page for fresh CSRF + cookie refresh ----
    print("--- LEG 0: GET /gpt ---")
    r0 = s.get("https://chatx.ai/gpt", headers=hdr_common, timeout=40)
    print("  status:", r0.status_code, "len:", len(r0.text))
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', r0.text) or \
        re.search(r'content="([^"]+)"\s+name="csrf-token"', r0.text)
    csrf = m.group(1) if m else None
    print("  fresh csrf:", (csrf[:24] + "...") if csrf else None)
    if not csrf:
        # maybe logged out / wall
        low = r0.text[:500].lower()
        print("  page head:", r0.text[:200].replace("\n", " "))
        print("  VERDICT: no csrf meta -> login wall or layout change")
        return

    # ---- LEG 1: POST /sendchat ----
    print("--- LEG 1: POST /sendchat ---")
    fields = {
        "_token": csrf,
        "user_id": rec_fields.get("user_id", ""),
        "chats_id": rec_fields.get("chats_id", ""),
        "prompt": PROMPT,
        "current_model": rec_fields.get("current_model", "gpt3"),
        "is_web": rec_fields.get("is_web", "0"),
        "is_youtube": rec_fields.get("is_youtube", "0"),
    }
    h1 = dict(hdr_common)
    h1.update({
        "X-CSRF-TOKEN": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://chatx.ai",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    r1 = s.post("https://chatx.ai/sendchat", data=fields, headers=h1, timeout=60)
    print("  status:", r1.status_code)
    print("  body:", r1.text[:400])
    if r1.status_code != 200:
        print("  VERDICT: leg1 HTTP", r1.status_code)
        return
    try:
        j1 = r1.json()
    except Exception:
        print("  leg1 not JSON")
        return
    if not j1.get("response"):
        print("  leg1 response=false:", j1.get("message") or j1.get("error"))
        print("  VERDICT: leg1 rejected")
        return
    conversions_id = j1.get("conversions_id")
    ass = j1.get("ass_conversions_id")
    print("  conversions_id:", conversions_id, "ass:", ass)

    # ---- LEG 2: GET /chats_stream (SSE) ----
    print("--- LEG 2: GET /chats_stream ---")
    q = urllib.parse.urlencode({
        "user_id": fields["user_id"], "chats_id": fields["chats_id"],
        "current_model": fields["current_model"],
        "conversions_id": conversions_id, "ass_conversions_id": ass,
        "g_recaptcha_response": "", "is_web": fields["is_web"],
        "is_youtube": fields["is_youtube"], "reasoning_effort": "", "verbosity": "",
    })
    h2 = dict(hdr_common)
    h2["Accept"] = "text/event-stream"
    answer = ""
    t0 = time.time()
    r2 = s.get("https://chatx.ai/chats_stream?" + q, headers=h2,
               stream=True, timeout=90)
    print("  status:", r2.status_code)
    try:
        for line in r2.iter_lines():
            if not line:
                continue
            line = line if isinstance(line, str) else line.decode("utf-8", "replace")
            if line.startswith("data:"):
                payload = line[5:].strip()
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                if obj.get("type") == "response.output_text.delta":
                    answer += obj.get("delta", "")
            if time.time() - t0 > 60:
                break
    finally:
        try:
            r2.close()
        except Exception:
            pass
    dt = time.time() - t0
    print(f"  answer ({dt:.1f}s): {answer[:200]!r}")
    if answer.strip():
        print("  VERDICT: LIVE (stateless, chrome-free)")
    else:
        print("  VERDICT: no answer extracted")


if __name__ == "__main__":
    main()
