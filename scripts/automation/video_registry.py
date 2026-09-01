#!/usr/bin/env python3
"""
Extract OmniRoute's native media registries (VIDEO / MUSIC / IMAGE / AUDIO) straight
out of the installed build, so the Monetizer never guesses at model ids.

Why this exists
---------------
OmniRoute serves video via a dedicated endpoint, ``POST /v1/videos/generations``, and
resolves the upstream from a *static code registry* (``VIDEO_PROVIDERS``) — not from the
database. There is no ``/api/media-providers`` CRUD route and no media table in
``storage.sqlite``; the only source of truth is the compiled registry inside the Next.js
build. Guessing model ids against it produces exactly the failures we were handed:

  * ``orcarouter/kling/kling-v3`` -> 401, because ``orcarouter`` is not a video provider
    at all (the call degrades to a chat completion).
  * ``pollinations/p-video``     -> 400, because the provider's only video model id is
    ``default`` (i.e. ``pollinations/default``).

So we read the registry instead of guessing. The registry is a plain JS object literal;
we locate it by its export marker, then let Node evaluate the literal and hand us JSON.
Node is used deliberately — the literal contains JS-isms (``!0``, unquoted keys, trailing
member expressions) that no JSON parser will accept.

Read-only. Touches nothing but the installed build.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

LEGACY_OMNIROUTE_DIST = Path(
    r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
)


def active_omniroute_dist() -> Path:
    """Resolve the build used by the registered production service.

    OmniRoute upgrades are staged outside the Hermes package tree.  Reading the
    legacy tree after a promotion silently produces a registry from the wrong
    version, so the Windows service's AppDirectory is authoritative.  The
    environment override remains first for sandbox/tests and non-Windows hosts.
    """
    override = os.environ.get("OMNIROUTE_DIST", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        try:
            import winreg

            key_path = r"SYSTEM\CurrentControlSet\Services\OmniRoute\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                app_dir = str(winreg.QueryValueEx(key, "AppDirectory")[0]).strip()
            candidate = Path(app_dir) / "dist"
            if candidate.is_dir():
                return candidate
        except (OSError, ImportError, ValueError):
            pass
    return LEGACY_OMNIROUTE_DIST


DEFAULT_OMNIROUTE_DIST = active_omniroute_dist()

# Registries we know how to extract, keyed by the exported symbol name.
REGISTRY_EXPORTS = (
    "VIDEO_PROVIDERS",
    "MUSIC_PROVIDERS",
    "IMAGE_PROVIDERS",
    "AUDIO_SPEECH_PROVIDERS",
    "AUDIO_TRANSCRIPTION_PROVIDERS",
)


class RegistryNotFound(RuntimeError):
    pass


def _chunks_dir(dist: Path) -> Path:
    d = dist / ".build" / "next" / "server" / "chunks"
    if not d.is_dir():
        raise RegistryNotFound(f"OmniRoute build chunks not found at {d}")
    return d


def _video_route_chunks(dist: Path) -> List[Path]:
    """Return only chunks loaded by the native video-generation route."""
    route = (
        dist
        / ".build"
        / "next"
        / "server"
        / "app"
        / "api"
        / "v1"
        / "videos"
        / "generations"
        / "route.js"
    )
    if not route.is_file():
        return []
    src = route.read_text(encoding="utf-8", errors="replace")
    out: List[Path] = []
    for rel in re.findall(r'R\.c\("server/chunks/([^\"]+)"\)', src):
        p = _chunks_dir(dist) / rel
        if p.is_file():
            out.append(p)
    return out


def _candidate_chunks(dist: Path, export_name: str) -> List[Path]:
    """Chunk files that declare ``export_name``, smallest first.

    Smallest-first matters: the config chunks are a few KB and contain just the
    registry, while the fat route bundles inline the same literal alongside a
    megabyte of unrelated code. Both parse, but the small one is far faster.
    """
    needles = [f'"{export_name}"'.encode()]
    if export_name == "VIDEO_PROVIDERS":
        # 3.8.50 stopped exporting the object itself.  The same registry is the
        # local captured by getVideoProvider/getAllVideoModels.
        needles.append(b'"getVideoProvider"')
    hits: List[Path] = []

    # Media route manifests list the ~100 chunks actually loaded by the route.
    # Search those first instead of reading 8,000+ unrelated Next.js chunks.
    candidates: List[Path] = []
    if export_name == "VIDEO_PROVIDERS":
        candidates = _video_route_chunks(dist)
    if not candidates:
        candidates = list(_chunks_dir(dist).rglob("*.js"))

    for p in candidates:
        try:
            raw = p.read_bytes()
            if any(needle in raw for needle in needles):
                hits.append(p)
        except OSError:
            continue
    if not hits:
        raise RegistryNotFound(f"No build chunk declares {export_name}")
    return sorted(hits, key=lambda p: p.stat().st_size)


def _extract_object_literal(src: str, export_name: str) -> str:
    """Pull the JS object literal that ``export_name`` is exported from.

    The compiled shape is::

        let i={ ...registry... };e.s(["VIDEO_PROVIDERS",0,i, ...])

    So: find the export site, read back to learn which local holds the registry,
    find that local's assignment, and brace-match forward.
    """
    export_at = src.find(f'"{export_name}"')
    local: Optional[str] = None
    if export_at != -1:
        # "VIDEO_PROVIDERS",0,i  -> capture the local identifier (`i`).
        m = re.compile(
            r'"' + re.escape(export_name) + r'"\s*,\s*\d+\s*,\s*([A-Za-z_$][\w$]*)'
        ).search(src, export_at)
        if m:
            local = m.group(1)
    elif export_name == "VIDEO_PROVIDERS":
        # 3.8.50 exports accessors rather than the object.  Pin the local from
        # getVideoProvider's measured body: function(e){return t[e]||null}.
        export_at = src.find('"getVideoProvider"')
        if export_at != -1:
            before = src[max(0, export_at - 1000) : export_at + 1000]
            m = re.search(
                r'"getVideoProvider"\s*,\s*\d+\s*,\s*function\([^)]*\)\s*\{'
                r'\s*return\s+([A-Za-z_$][\w$]*)\[',
                before,
            )
            if m:
                local = m.group(1)
    if export_at == -1:
        raise RegistryNotFound(f"{export_name} accessors not present in chunk")
    if not local:
        raise RegistryNotFound(f"Could not identify the local bound to {export_name}")

    # Find that local's object assignment, searching backwards from the export.
    assign = None
    for am in re.finditer(
        r"(?:let|const|var)\s+" + re.escape(local) + r"\s*=\s*\{", src[:export_at]
    ):
        assign = am
    if assign is None:
        raise RegistryNotFound(f"Could not find assignment for local {local!r}")

    start = src.index("{", assign.start())
    depth, i, n = 0, start, len(src)
    in_str: Optional[str] = None
    escaped = False
    while i < n:
        ch = src[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise RegistryNotFound(f"Unbalanced braces while reading {export_name}")


def _node_bin() -> str:
    node = shutil.which("node")
    if not node:
        raise RegistryNotFound(
            "node not found on PATH; required to evaluate the registry literal"
        )
    return node


def _eval_literal_to_json(literal: str) -> Dict[str, Any]:
    """Evaluate a JS object literal via Node and return it as Python data.

    Some entries reference other build modules (e.g. runwayml pulls its model list
    from ``e.i(405469).RUNWAYML_SUPPORTED_VIDEO_MODELS``). Those cross-module reads
    cannot be resolved outside the turbopack runtime, so we neutralise them to an
    empty list and flag the provider as ``modelsUnresolved`` afterwards.
    """
    neutralised = re.sub(r"e\.i\(\s*\d+\s*\)\s*\.\s*[A-Za-z_$][\w$]*", "[]", literal)
    neutralised = re.sub(
        r"(?<=models:)[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*",
        "[]",
        neutralised,
    )
    # 3.8.50's Adobe entry calls an imported model-list helper inside the
    # otherwise static object: models:(0,r.toRegistryVideoModels)().  The helper
    # is outside the extracted literal, so preserve the provider and mark its
    # model list unresolved instead of making the entire registry unreadable.
    neutralised = re.sub(
        r"\(\s*0\s*,\s*[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\s*\)\s*\(\s*\)",
        "[]",
        neutralised,
    )
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "dump.js"
        script.write_text(
            "const reg = (" + neutralised + ");\n"
            "process.stdout.write(JSON.stringify(reg));\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [_node_bin(), str(script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    if proc.returncode != 0:
        raise RegistryNotFound(f"Node failed to evaluate registry: {proc.stderr[-800:]}")
    return json.loads(proc.stdout)


def load_registry(
    export_name: str = "VIDEO_PROVIDERS", dist: Path = DEFAULT_OMNIROUTE_DIST
) -> Dict[str, Any]:
    """Return one of OmniRoute's media registries as ``{provider_id: definition}``."""
    last_err: Optional[Exception] = None
    for chunk in _candidate_chunks(dist, export_name):
        try:
            src = chunk.read_text(encoding="utf-8", errors="replace")
            literal = _extract_object_literal(src, export_name)
            reg = _eval_literal_to_json(literal)
            if not isinstance(reg, dict) or not reg:
                raise RegistryNotFound("registry evaluated to something unusable")
            for pid, definition in reg.items():
                if isinstance(definition, dict) and definition.get("models") == []:
                    definition["modelsUnresolved"] = True
            return reg
        except Exception as e:  # try the next candidate chunk
            last_err = e
            continue
    raise RegistryNotFound(f"Could not extract {export_name}: {last_err}")


def flatten_models(registry: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flatten a registry into the ``provider/model`` strings the API accepts."""
    out: List[Dict[str, str]] = []
    for pid, definition in registry.items():
        if not isinstance(definition, dict):
            continue
        for model in definition.get("models") or []:
            if not isinstance(model, dict) or not model.get("id"):
                continue
            mid = str(model["id"])
            out.append(
                {
                    "qualified": mid if mid.startswith(f"{pid}/") else f"{pid}/{mid}",
                    "provider": pid,
                    "model": mid,
                    "name": str(model.get("name") or mid),
                    "authType": str(definition.get("authType") or ""),
                    "format": str(definition.get("format") or ""),
                    "baseUrl": str(definition.get("baseUrl") or ""),
                }
            )
    return out


def zero_auth_providers(registry: Dict[str, Any]) -> List[str]:
    """Providers needing no credential at all — the cheapest thing that can work."""
    return sorted(
        pid
        for pid, d in registry.items()
        if isinstance(d, dict) and str(d.get("authType", "")).lower() == "none"
    )


def supported_video_formats(dist: Path = DEFAULT_OMNIROUTE_DIST) -> List[str]:
    """Formats that OmniRoute's video router actually implements a handler for.

    Being listed in ``VIDEO_PROVIDERS`` is necessary but NOT sufficient: the router
    dispatches on ``providerConfig.format`` through a chain of ternaries and falls
    through to ``Unsupported video format: <format>``. Several registered providers
    have no handler at all — ``pollinations`` declares format ``pollinations-video``
    and is registered, keyed and active, yet every call 400s on that fallthrough.

    So the registry tells us what is *declared*; this tells us what is *wired*. Only
    the intersection can ever return a video. Derived from the build rather than
    hardcoded, so an OmniRoute upgrade that adds handlers is picked up automatically.
    """
    marker = "Unsupported video format"
    candidates = _video_route_chunks(dist)
    if not candidates:
        candidates = list(_chunks_dir(dist).rglob("*.js"))
    for path in candidates:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        at = src.find(marker)
        if at == -1:
            continue
        # The dispatch chain immediately precedes the fallthrough:
        #   "deepinfra-video"===f.format?(0,n.handleDeepinfra...):...
        window = src[max(0, at - 12000) : at]
        formats = re.findall(r'"([a-z0-9][a-z0-9\-]*)"\s*===\s*[A-Za-z_$][\w$]*\.format', window)
        if formats:
            return sorted(set(formats))
    raise RegistryNotFound("Could not locate the video format dispatch chain")


def annotate_supported(registry: Dict[str, Any], dist: Path = DEFAULT_OMNIROUTE_DIST) -> Dict[str, Any]:
    """Tag each provider with ``handlerImplemented`` from the dispatch chain."""
    try:
        implemented = set(supported_video_formats(dist))
    except RegistryNotFound:
        return registry
    for d in registry.values():
        if isinstance(d, dict):
            d["handlerImplemented"] = str(d.get("format") or "") in implemented
    return registry


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default="VIDEO_PROVIDERS", choices=REGISTRY_EXPORTS)
    ap.add_argument("--dist", default=str(DEFAULT_OMNIROUTE_DIST))
    ap.add_argument("--json", action="store_true", help="dump raw registry JSON")
    args = ap.parse_args()

    reg = load_registry(args.registry, Path(args.dist))
    if args.json:
        print(json.dumps(reg, indent=2))
        raise SystemExit(0)

    if args.registry == "VIDEO_PROVIDERS":
        annotate_supported(reg, Path(args.dist))
        try:
            impl = supported_video_formats(Path(args.dist))
            print(f"implemented video formats ({len(impl)}): {', '.join(impl)}")
        except RegistryNotFound as e:
            print(f"[!] {e}")

    models = flatten_models(reg)
    print(f"{args.registry}: {len(reg)} providers, {len(models)} models")
    print(f"zero-auth providers: {', '.join(zero_auth_providers(reg)) or '(none)'}")
    print()
    for pid in sorted(reg):
        d = reg[pid]
        mine = [m for m in models if m["provider"] == pid]
        flag = " [models unresolved]" if d.get("modelsUnresolved") else ""
        if d.get("handlerImplemented") is False:
            flag += "  <-- NO HANDLER (always 400s)"
        print(f"  {pid:26} auth={str(d.get('authType')):8} format={str(d.get('format')):22} models={len(mine)}{flag}")
