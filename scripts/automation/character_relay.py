#!/usr/bin/env python3
"""Upload a film's character reference images once, relay them into every generator's image slots.

The problem this solves
-----------------------
A film kit has characters -- "Alice", "Bob" -- and each is a reference image the operator uploads
once. Every generator that renders a clip (Google Flow, digen, rtst, veoaifree) needs those same
faces pushed into ITS own image inputs: a first-frame slot, a reference-image slot, a character slot.
Doing that by hand, per character, per generator, per clip, across a 2,160-clip film is not a thing a
human does twice. So: upload each character once per generator, remember the asset handle the
generator hands back, and reuse that handle in every generate request for that character.

The "omni way" applies unchanged
--------------------------------
This is the same universal-replay discipline the chat pool uses, with one substitution changed:

  * chat replay   -- a recorded genuine POST whose body carries a text SENTINEL; on a live call the
                     sentinel is string-replaced with the real prompt. (see universal_replay.py)
  * upload relay  -- a recorded genuine multipart POST whose body carries a FILE PART; on a live call
                     that one part's bytes + filename are swapped for the character image, and nothing
                     else in the recorded envelope is touched.

Both replay a real browser exchange server-side with the seat's cookie jar. Neither reconstructs a
request. Reconstruction gets gated; replay does not. A per-generator "which field takes the handle"
table is a response/payload-shape contract, not a request adapter -- the same category as
veoaifree_chat_client's MODELS map or the digen submit/poll/result contract.

What exists now and what is captured later
------------------------------------------
This file is the whole engine: the contract table, the film-kit loader, the idempotent
upload-once cache, the faithful multipart file-part swap, and the generate-payload slot binder. Its
one external input is a **recorded upload exchange per generator**, saved next to the chat sessions as
`state/secrets/upload_<generator>.json`. Capturing that means the operator uploads one image by hand
in a signed-in tab while the harness records the multipart POST -- the same capture step every chat
session went through. Until that file exists for a generator, `relay()` returns PENDING_CAPTURE and
names exactly what to record. It never fabricates an upload.

    python character_relay.py --selftest                         # prove the logic, no network
    python character_relay.py --kit D:\film\alice --film alice --plan
    python character_relay.py --kit D:\film\alice --film alice --generator digen --relay

`--plan` (default) shows what would happen and touches nothing. `--relay` performs uploads for
generators that have a recorded upload session. Card / captcha / quota walls in a response STOP the
relay for that generator and are reported -- never solved, never hammered.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import sys
import time
from typing import Any, Callable, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
SECRETS = STATE / "secrets"
RELAY_MAP = STATE / "character_relay_map.json"

# An upload we will not attempt. A character reference is a small still image; anything larger is a
# mistake upstream, and shipping tens of MB into a form is how an account gets flagged.
MAX_IMAGE_BYTES = 12 * 1024 * 1024
IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",          # RIFF....WEBP; the WEBP check is refined below
    b"BM": "image/bmp",
}

# Any of these in a response body means a wall, not a result. Same list the pool uses to decide a
# fallback. A wall is a STOP-and-report, never a retry or a payment.
WALL_HINTS = (
    "credit", "quota", "insufficient", "billing", "payment", "upgrade", "subscribe",
    "exhausted", "balance", "captcha", "verify you are human", "rate limit",
    "too many requests", "unauthorized", "forbidden", "sign in", "log in", "expired",
)


# ==================================================================================================
# per-generator contract
# ==================================================================================================

class Generator:
    """One video generator's image contract.

    `upload_session` is the recorded multipart POST replayed to push an image (its url/headers/body
    all come from that file -- this table never invents an endpoint). `file_part` is the multipart
    field name the file rides in. `asset_paths` are the response keys, tried in order, that carry the
    handle the generator gives back. `slots` say which fields in a *generate* request receive that
    handle and in what form. Slots marked confidence="assumed" are best-known names to be confirmed
    when the upload session is captured; confidence="confirmed" have been seen on the wire.
    """

    def __init__(self, key: str, host: str, seat_profile: str, upload_session: str,
                 file_part: str, asset_paths: list, slots: list, notes: str = ""):
        self.key = key
        self.host = host
        self.seat_profile = seat_profile          # which seat's jar signs the upload (see seat map)
        self.upload_session = upload_session       # filename under state/secrets/
        self.file_part = file_part
        self.asset_paths = asset_paths
        self.slots = slots
        self.notes = notes

    def session_path(self) -> pathlib.Path:
        return SECRETS / self.upload_session


def _slot(path: str, form: str, confidence: str) -> dict:
    # form: "id" (raw handle) | "url" (full asset URL) | "array_append" (push handle onto a list)
    return {"path": path, "form": form, "confidence": confidence}


# The four video generators from state/seat_readiness.json (category "Video generators"). Endpoints
# are intentionally NOT hard-coded -- they arrive with the recorded upload session. Slot names are the
# best-known shapes; each is confirmed when its upload session is captured.
GENERATORS: dict[str, Generator] = {
    "flow": Generator(
        key="flow", host="labs.google", seat_profile="providers",
        upload_session="upload_flow.json", file_part="file",
        asset_paths=["asset.name", "asset.id", "name", "id", "mediaId"],
        slots=[_slot("request.imageInput.assetId", "id", "assumed"),
               _slot("request.referenceImages", "array_append", "assumed")],
        notes="Google Flow / labs.google. Flow PRO lives in the 'providers' seat.",
    ),
    "digen": Generator(
        key="digen", host="digen.ai", seat_profile="providers",
        upload_session="upload_digen.json", file_part="file",
        asset_paths=["data.url", "data.image_url", "data.id", "url", "id"],
        # Real slots from the recorded digen t2v contract are nested under scene_params (image_url,
        # last_image_url, middle_image_url, image_url_v1, refer_video_url). The primary character frame
        # is scene_params.image_url; last_image_url conditions the closing frame. Which slot maps to
        # which character role is confirmed only once an image-to-video gen is recorded (t2v leaves
        # them empty), hence confidence="assumed".
        slots=[_slot("scene_params.image_url", "url", "assumed"),
               _slot("scene_params.last_image_url", "url", "assumed")],
        notes="digen t2v contract is submit/poll/result with custom-header auth (see memory). Image "
              "slots live under scene_params; t2v recordings leave them empty, so an image-to-video "
              "capture is the confirming step.",
    ),
    "rtst": Generator(
        key="rtst", host="rtst.ai", seat_profile="providers",
        upload_session="upload_rtst.json", file_part="file",
        asset_paths=["data.url", "url", "data.id", "id"],
        slots=[_slot("image", "url", "assumed"),
               _slot("init_image", "url", "assumed")],
        notes="rtst.ai. token + crisp-client cookies are the auth (see seat map).",
    ),
    "veoaifree": Generator(
        key="veoaifree", host="veoaifree.com", seat_profile="providers",
        upload_session="upload_veoaifree.json", file_part="file",
        asset_paths=["url", "data.url", "id", "attachment_id"],
        slots=[_slot("image_url", "url", "assumed"),
               _slot("attachments", "array_append", "assumed")],
        notes="veoaifree video. wordpress_logged_in cookie is the auth; a WP media upload returns a "
              "URL, hence the url-form slots.",
    ),
}


# ==================================================================================================
# film kit
# ==================================================================================================

def _sniff_image(head: bytes) -> Optional[str]:
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    for magic, mime in IMAGE_MAGIC.items():
        if magic == b"RIFF":
            continue
        if head.startswith(magic):
            return mime
    return None


class Character:
    """One reference image. Identified by content hash, not filename, so the same face uploaded under
    two names is uploaded once, and a renamed-but-identical file is not re-uploaded."""

    def __init__(self, name: str, path: pathlib.Path, data: bytes, mime: str):
        self.name = name
        self.path = path
        self.size = len(data)
        self.mime = mime
        self.sha256 = hashlib.sha256(data).hexdigest()
        self._data = data

    def bytes(self) -> bytes:
        return self._data

    def summary(self) -> dict:
        # No bytes here -- shapes and hashes only.
        return {"name": self.name, "file": self.path.name, "bytes": self.size,
                "mime": self.mime, "sha256": self.sha256[:16]}


def load_kit(kit_dir: pathlib.Path) -> list:
    """Read a film-kit directory into characters. The character name is the file stem, so `alice.png`
    is the character "alice". Non-images and oversized files are refused with a reason, not skipped
    silently -- a missing character is a wrong film, worth stopping for."""
    if not kit_dir.is_dir():
        raise FileNotFoundError(f"kit directory not found: {kit_dir}")
    chars: list = []
    problems: list = []
    for f in sorted(kit_dir.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            data = f.read_bytes()
        except OSError as e:
            problems.append(f"{f.name}: unreadable ({e})")
            continue
        if len(data) > MAX_IMAGE_BYTES:
            problems.append(f"{f.name}: {len(data)} bytes exceeds cap {MAX_IMAGE_BYTES}")
            continue
        mime = _sniff_image(data[:16])
        if not mime:
            problems.append(f"{f.name}: not a recognised image (png/jpeg/gif/webp/bmp)")
            continue
        chars.append(Character(f.stem, f, data, mime))
    if problems:
        raise ValueError("kit has unusable files:\n  " + "\n  ".join(problems))
    if not chars:
        raise ValueError(f"no character images in {kit_dir}")
    return chars


# ==================================================================================================
# faithful multipart file-part swap
# ==================================================================================================

def swap_file_part(body: bytes, boundary: bytes, part_name: str,
                   new_bytes: bytes, new_filename: str) -> bytes:
    """Return `body` with exactly one multipart part's file swapped, everything else byte-identical.

    This is the whole point of replay-not-reconstruct: the recorded body -- every field, every
    ordering quirk the server might check -- is preserved, and only the image the operator is
    substituting changes. We locate the part by its `name="<part_name>"` disposition, replace the
    filename in its header, and replace the payload between that part's header terminator and the next
    boundary. Raises if the part is not found, because a silent no-op upload is worse than a stop.
    """
    delim = b"--" + boundary
    marker = b'name="' + part_name.encode() + b'"'
    segments = body.split(delim)
    hit = False
    for i, seg in enumerate(segments):
        # A part segment looks like: \r\n<headers>\r\n\r\n<payload>\r\n
        if marker not in seg:
            continue
        hdr_end = seg.find(b"\r\n\r\n")
        if hdr_end == -1:
            continue
        headers = seg[:hdr_end]
        # swap filename in the disposition header
        fn = b'filename="'
        fs = headers.find(fn)
        if fs != -1:
            fe = headers.find(b'"', fs + len(fn))
            if fe != -1:
                headers = headers[:fs + len(fn)] + new_filename.encode() + headers[fe:]
        # payload runs to the trailing CRLF that precedes the next boundary
        tail = seg[hdr_end + 4:]
        trailing = b"\r\n" if tail.endswith(b"\r\n") else b""
        segments[i] = headers + b"\r\n\r\n" + new_bytes + trailing
        hit = True
        break
    if not hit:
        raise ValueError(f"multipart part name={part_name!r} not found in recorded body")
    return delim.join(segments)


def _boundary_from_headers(headers: dict) -> Optional[bytes]:
    ct = ""
    for k, v in (headers or {}).items():
        if k.lower() == "content-type":
            ct = str(v)
            break
    if "boundary=" not in ct:
        return None
    b = ct.split("boundary=", 1)[1].strip().strip('"')
    return b.encode()


# ==================================================================================================
# response-shape helpers  (allowed: reading a reply, not building a request)
# ==================================================================================================

def dig(obj: Any, dotted: str) -> Any:
    """Fetch a dotted path out of a decoded JSON reply, or None."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def extract_asset(reply: Any, paths: list) -> Optional[str]:
    for p in paths:
        v = dig(reply, p)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v)
    return None


def looks_like_wall(text: str) -> Optional[str]:
    low = (text or "").lower()
    for h in WALL_HINTS:
        if h in low:
            return h
    return None


# ==================================================================================================
# generate-payload slot binding  (pure -- the part that runs on every clip)
# ==================================================================================================

def _set_path(root: dict, dotted: str, value: Any, form: str) -> None:
    parts = dotted.split(".")
    cur = root
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    leaf = parts[-1]
    if form == "array_append":
        arr = cur.get(leaf)
        if not isinstance(arr, list):
            arr = []
            cur[leaf] = arr
        arr.append(value)
    else:
        cur[leaf] = value


def bind_slots(payload: dict, generator: str, handle: str) -> dict:
    """Inject one character's asset handle into a generate payload per the generator contract.

    Pure and side-effect-free on its input (returns a new dict). This is the hot path -- it runs once
    per character per clip -- so it does no I/O and never fails on a network condition; a missing
    generator is a programming error and raised as one.
    """
    gen = GENERATORS.get(generator)
    if not gen:
        raise KeyError(f"unknown generator {generator!r}")
    out = json.loads(json.dumps(payload))     # cheap deep copy; payloads are small JSON
    for s in gen.slots:
        _set_path(out, s["path"], handle, s["form"])
    return out


# ==================================================================================================
# idempotent upload-once cache
# ==================================================================================================

def _load_map() -> dict:
    if RELAY_MAP.exists():
        try:
            return json.loads(RELAY_MAP.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"version": 1, "entries": {}}


def _map_key(film: str, sha256: str, generator: str) -> str:
    return f"{film}::{generator}::{sha256}"


def _save_map(m: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = RELAY_MAP.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, indent=2), encoding="utf-8")
    tmp.replace(RELAY_MAP)


# ==================================================================================================
# upload transport  (faithful replay of the recorded multipart POST)
# ==================================================================================================

class UploadResult:
    def __init__(self, status: str, handle: Optional[str] = None, detail: str = "",
                 wall: Optional[str] = None, cached: bool = False):
        self.status = status              # UPLOADED | CACHED | PENDING_CAPTURE | WALL | ERROR
        self.handle = handle
        self.detail = detail
        self.wall = wall
        self.cached = cached

    def row(self, char: "Character", gen: str) -> dict:
        d = {"generator": gen, "character": char.name, "sha256": char.sha256[:16],
             "status": self.status}
        if self.handle:
            d["handle"] = self.handle
        if self.wall:
            d["wall"] = self.wall
        if self.detail:
            d["detail"] = self.detail
        return d


def _load_upload_session(gen: Generator) -> Optional[dict]:
    p = gen.session_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _decode_recorded_body(rec: dict) -> bytes:
    """A recorded multipart body is stored base64 (binary-safe) under body_b64; older text captures
    may carry request_body as a string. Prefer body_b64."""
    if rec.get("body_b64"):
        return base64.b64decode(rec["body_b64"])
    if isinstance(rec.get("request_body"), str):
        return rec["request_body"].encode("utf-8", "surrogatepass")
    return b""


# The live HTTP call is isolated behind this signature so --selftest can inject a fake and the engine
# is provably correct without touching a provider. Returns (status_code, response_text, set_cookie).
Transport = Callable[[str, dict, bytes, str], tuple]


def _requests_transport(url: str, headers: dict, body: bytes, cookie: str) -> tuple:
    import requests                                   # imported lazily so --selftest needs no network
    h = {k: v for k, v in (headers or {}).items() if k.lower() != "cookie"}
    if cookie:
        h["Cookie"] = cookie
    r = requests.post(url, headers=h, data=body, timeout=120)
    return r.status_code, r.text, r.headers.get("Set-Cookie", "")


def relay_one(char: "Character", gen: Generator, do_upload: bool,
              transport: Optional[Transport] = None) -> UploadResult:
    """Ensure one character is uploaded to one generator, reusing a cached handle if we have one."""
    m = _load_map()
    key = _map_key(char._film if hasattr(char, "_film") else "", char.sha256, gen.key)
    ent = m["entries"].get(key)
    if ent and ent.get("handle"):
        return UploadResult("CACHED", handle=ent["handle"],
                            detail=f"uploaded {ent.get('uploadedAt')}", cached=True)

    sess = _load_upload_session(gen)
    if not sess:
        return UploadResult(
            "PENDING_CAPTURE",
            detail=(f"no {gen.upload_session} yet. Capture it once: in the '{gen.seat_profile}' seat "
                    f"tab signed in to {gen.host}, upload any image by hand and record the multipart "
                    f"POST as state/secrets/{gen.upload_session} (fields: recorded_exchange.url, "
                    f".method, .request_headers, .body_b64, file_part={gen.file_part!r}; plus "
                    f"cookie_header). Then --relay will replay it with the character bytes."))

    if not do_upload:
        return UploadResult("PENDING_CAPTURE" if not sess else "READY",
                            detail="plan mode: recorded session present, would upload on --relay")

    rec = sess.get("recorded_exchange") or {}
    url = rec.get("url")
    headers = dict(rec.get("request_headers") or {})
    cookie = sess.get("cookie_header") or rec.get("cookie_header") or ""
    boundary = _boundary_from_headers(headers)
    body = _decode_recorded_body(rec)
    if not (url and boundary and body):
        return UploadResult("ERROR",
                            detail="recorded upload session is missing url / multipart boundary / body")

    try:
        swapped = swap_file_part(body, boundary, gen.file_part, char.bytes(),
                                 f"{char.name}{_ext_for(char.mime)}")
    except ValueError as e:
        return UploadResult("ERROR", detail=str(e))
    # Content-Length, if the capture pinned it, must reflect the swapped body.
    headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
    headers["Content-Length"] = str(len(swapped))

    tp = transport or _requests_transport
    try:
        code, text, set_cookie = tp(url, headers, swapped, cookie)
    except Exception as e:                              # transport/network failure is reportable, not fatal
        return UploadResult("ERROR", detail=f"{type(e).__name__}: {e}")

    wall = looks_like_wall(text) if (code >= 400 or looks_like_wall(text)) else None
    if wall:
        return UploadResult("WALL", wall=wall,
                            detail=f"HTTP {code}; response hit a '{wall}' wall -- stopped, not retried")
    if code >= 400:
        return UploadResult("ERROR", detail=f"HTTP {code}")

    try:
        reply = json.loads(text)
    except ValueError:
        reply = {"raw": text[:200]}
    handle = extract_asset(reply, gen.asset_paths)
    if not handle:
        return UploadResult("ERROR",
                            detail=f"upload returned HTTP {code} but no asset handle at any of "
                                   f"{gen.asset_paths}")

    # rotation write-back: a fresh Set-Cookie keeps this seat's jar alive, same as the chat pool.
    if set_cookie:
        _absorb_cookie(gen, set_cookie)

    m["entries"][key] = {"handle": handle, "generator": gen.key, "character": char.name,
                         "sha256": char.sha256, "uploadedAt": _now_iso()}
    _save_map(m)
    return UploadResult("UPLOADED", handle=handle)


def _absorb_cookie(gen: Generator, set_cookie: str) -> None:
    """Merge a rotated Set-Cookie back into the upload session file. Best-effort and silent on the
    contents -- never logs a cookie value."""
    p = gen.session_path()
    try:
        sess = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return
    jar: dict = {}
    for piece in (sess.get("cookie_header") or "").split(";"):
        if "=" in piece:
            k, _, v = piece.strip().partition("=")
            jar[k] = v
    for cookie_line in set_cookie.split("\n"):
        first = cookie_line.split(";", 1)[0].strip()
        if "=" in first:
            k, _, v = first.partition("=")
            jar[k] = v
    sess["cookie_header"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    sess["cookieRotatedAt"] = _now_iso()
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(sess), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def _ext_for(mime: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
            "image/webp": ".webp", "image/bmp": ".bmp"}.get(mime, ".img")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ==================================================================================================
# orchestration
# ==================================================================================================

def relay_film(kit_dir: pathlib.Path, film: str, generators: list, do_upload: bool) -> dict:
    chars = load_kit(kit_dir)
    for c in chars:
        c._film = film                                # stamp so the cache key is per-film
    rows: list = []
    for gkey in generators:
        gen = GENERATORS[gkey]
        for c in chars:
            res = relay_one(c, gen, do_upload=do_upload)
            rows.append(res.row(c, gkey))
    summary = {
        "film": film, "kit": str(kit_dir), "generators": generators,
        "characters": [c.summary() for c in chars],
        "generatedAt": _now_iso(), "mode": "relay" if do_upload else "plan",
        "results": rows,
        "counts": _tally(rows),
    }
    return summary


def _tally(rows: list) -> dict:
    t: dict = {}
    for r in rows:
        t[r["status"]] = t.get(r["status"], 0) + 1
    return t


# ==================================================================================================
# selftest -- proves the engine without a network
# ==================================================================================================

def selftest() -> int:
    ok = 0
    fail = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ok    {name}")
        else:
            fail += 1
            print(f"  FAIL  {name}  {extra}")

    # 1. multipart file-part swap keeps the envelope, replaces only the file
    boundary = b"----relayBOUND"
    orig_img = b"\x89PNG\r\n\x1a\nORIGINALPIXELS"
    body = (b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="meta"\r\n\r\n'
            b"keepme\r\n"
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="orig.png"\r\n'
            b"Content-Type: image/png\r\n\r\n" + orig_img + b"\r\n"
            b"--" + boundary + b"--\r\n")
    new_img = b"\x89PNG\r\n\x1a\nNEWALICEPIXELS-longer-than-before"
    swapped = swap_file_part(body, boundary, "file", new_img, "alice.png")
    check("swap injects new bytes", new_img in swapped)
    check("swap drops old bytes", orig_img not in swapped)
    check("swap keeps other parts", b"keepme" in swapped)
    check("swap rewrites filename", b'filename="alice.png"' in swapped and b"orig.png" not in swapped)
    check("swap preserves boundary count", swapped.count(b"--" + boundary) == body.count(b"--" + boundary))

    # 2. image sniff
    check("sniff png", _sniff_image(b"\x89PNG\r\n\x1a\n....") == "image/png")
    check("sniff jpeg", _sniff_image(b"\xff\xd8\xff\xe0....") == "image/jpeg")
    check("sniff webp", _sniff_image(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp")
    check("sniff rejects text", _sniff_image(b"hello there!!!!!") is None)

    # 3. slot binding forms
    p = bind_slots({}, "digen", "HANDLE123")
    check("bind id/url slot", dig(p, "scene_params.image_url") == "HANDLE123"
          and dig(p, "scene_params.last_image_url") == "HANDLE123")
    p2 = bind_slots({}, "flow", "ASSET/9")
    check("bind array_append slot", isinstance(dig(p2, "request.referenceImages"), list)
          and dig(p2, "request.referenceImages") == ["ASSET/9"])
    check("bind nested id slot", dig(p2, "request.imageInput.assetId") == "ASSET/9")
    src = {"keep": 1}
    _ = bind_slots(src, "digen", "X")
    check("bind does not mutate input", src == {"keep": 1})

    # 4. asset extraction from a reply shape
    check("extract nested", extract_asset({"data": {"url": "u1"}}, ["data.url", "id"]) == "u1")
    check("extract falls through", extract_asset({"id": 7}, ["data.url", "id"]) == "7")
    check("extract none", extract_asset({"nope": 1}, ["data.url", "id"]) is None)

    # 5. wall detection
    check("wall on quota", looks_like_wall("You are out of credits") == "credit")
    check("wall on captcha", looks_like_wall("Please complete the CAPTCHA") == "captcha")
    check("no wall on ok", looks_like_wall('{"data":{"url":"ok"}}') is None)

    # 6. end-to-end relay_one against a FAKE transport + a synthetic recorded session (no network)
    tmp_sess = SECRETS / "upload_digen.json"
    had = tmp_sess.exists()
    backup = tmp_sess.read_bytes() if had else None
    try:
        SECRETS.mkdir(parents=True, exist_ok=True)
        synthetic = {
            "host": "digen.ai", "modality": "upload", "site": "digen",
            "cookie_header": "digen_token=abc; intercom-session-wgkan4nt=def",
            "recorded_exchange": {
                "url": "https://api.digen.ai/upload", "method": "POST",
                "request_headers": {"Content-Type": "multipart/form-data; boundary=----relayBOUND"},
                "body_b64": base64.b64encode(body).decode(),
                "host": "digen.ai",
            },
            "status": {"alive": True, "harvested_at": _now_iso(), "reason": "selftest"},
        }
        tmp_sess.write_text(json.dumps(synthetic), encoding="utf-8")

        captured = {}

        def fake_tp(url, headers, sent_body, cookie):
            captured["url"] = url
            captured["has_new_img"] = new_img in sent_body
            captured["content_length"] = headers.get("Content-Length")
            captured["cookie_present"] = bool(cookie)
            return 200, json.dumps({"data": {"url": "https://cdn.digen.ai/asset/xyz"}}), ""

        c = Character("alice", pathlib.Path("alice.png"), new_img, "image/png")
        c._film = "__selftest__"
        # ensure a clean cache slot
        mm = _load_map()
        mm["entries"].pop(_map_key("__selftest__", c.sha256, "digen"), None)
        _save_map(mm)

        res = relay_one(c, GENERATORS["digen"], do_upload=True, transport=fake_tp)
        check("relay_one uploads via transport", res.status == "UPLOADED", res.detail)
        check("relay_one returns handle", res.handle == "https://cdn.digen.ai/asset/xyz")
        check("transport got swapped bytes", captured.get("has_new_img") is True)
        check("transport got recomputed length",
              captured.get("content_length") == str(len(swap_file_part(body, b"----relayBOUND", "file", new_img, "alice.png"))))
        check("transport got the jar", captured.get("cookie_present") is True)

        res2 = relay_one(c, GENERATORS["digen"], do_upload=True, transport=fake_tp)
        check("second call is CACHED (upload-once)", res2.status == "CACHED" and res2.handle == res.handle)

        # clean the selftest cache entry so we don't leave test state behind
        mm = _load_map()
        mm["entries"].pop(_map_key("__selftest__", c.sha256, "digen"), None)
        _save_map(mm)
    finally:
        if backup is not None:
            tmp_sess.write_bytes(backup)
        elif tmp_sess.exists():
            tmp_sess.unlink()

    print(f"\n{ok} passed, {fail} failed")
    return 0 if fail == 0 else 1


# ==================================================================================================
# CLI
# ==================================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kit", help="film-kit directory of character images (stem = character name)")
    ap.add_argument("--film", help="film name -- namespaces the upload-once cache")
    ap.add_argument("--generator", action="append",
                    help=f"generator to relay into (repeatable). default: all "
                         f"({', '.join(GENERATORS)})")
    ap.add_argument("--relay", action="store_true",
                    help="actually upload (replay the recorded session with the character bytes). "
                         "default is plan mode, which touches no network.")
    ap.add_argument("--status", action="store_true", help="print the upload-once cache and exit")
    ap.add_argument("--selftest", action="store_true", help="prove the engine with no network")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.status:
        m = _load_map()
        if a.json:
            print(json.dumps(m, indent=2))
        else:
            ents = m.get("entries", {})
            print(f"upload-once cache: {len(ents)} entry(ies) in {RELAY_MAP.relative_to(ROOT)}")
            for k, v in ents.items():
                print(f"  {k}  -> {v.get('handle')}  ({v.get('uploadedAt')})")
        return 0

    if not a.kit or not a.film:
        ap.error("--kit and --film are required (or use --selftest / --status)")

    gens = a.generator or list(GENERATORS)
    unknown = [g for g in gens if g not in GENERATORS]
    if unknown:
        ap.error(f"unknown generator(s): {unknown}. known: {list(GENERATORS)}")

    try:
        summary = relay_film(pathlib.Path(a.kit), a.film, gens, do_upload=a.relay)
    except (FileNotFoundError, ValueError) as e:
        print(f"kit error: {e}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"film={summary['film']}  kit={summary['kit']}  mode={summary['mode']}")
        print(f"characters: {', '.join(c['name'] for c in summary['characters'])}")
        for r in summary["results"]:
            line = f"  [{r['status']:<14}] {r['generator']:<10} {r['character']:<12}"
            if r.get("handle"):
                line += f" -> {r['handle']}"
            if r.get("wall"):
                line += f"  WALL:{r['wall']}"
            if r.get("detail") and r["status"] in ("PENDING_CAPTURE", "ERROR", "WALL"):
                line += f"\n                   {r['detail']}"
            print(line)
        print(f"\ncounts: {summary['counts']}")
        pend = summary["counts"].get("PENDING_CAPTURE", 0)
        if pend:
            print(f"\n{pend} pending capture -- these generators need a recorded upload session before "
                  f"--relay can push a character. That is the 'testing later' step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
