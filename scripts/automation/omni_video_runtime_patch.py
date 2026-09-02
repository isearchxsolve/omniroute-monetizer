#!/usr/bin/env python3
"""Plan/apply the narrowly-scoped Omni native video runtime repair.

This patch is intentionally separate from the production service process.  The
installed OmniRoute package is a published standalone artifact: its TypeScript
sources are present for inspection, but the Windows service executes the
compiled Next/Turbopack chunks under ``dist/.build/next``.  Editing only the
sources would therefore create a misleading fix, while editing a minified
chunk by hand without a reproducible record would be unsafe.

The script performs exact, count-checked replacements in both layers:

* source: KIE model-specific input defaults and current Vertex model IDs;
* runtime: the exact chunks loaded by the video-generation route.

It never restarts OmniRoute, touches the database, changes credentials, or
spends video credits.  ``--plan`` is the default.  ``--apply`` takes a
timestamped byte-for-byte backup before writing and refuses to proceed if the
expected 3.8.50 artifact or replacement counts do not match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


EXPECTED_VERSION = "3.8.50"
DEFAULT_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "state" / "omniroute-3.8.50-sandbox" / "node_modules" / "omniroute"

VERTEX_SOURCE_OLD = '''      { id: "veo-3.0-generate-001", name: "Veo 3.0 (Vertex)" },
      { id: "veo-3.0-fast-generate-001", name: "Veo 3.0 Fast (Vertex)" },
      { id: "veo-2.0-generate-001", name: "Veo 2.0 (Vertex)" },'''
VERTEX_SOURCE_NEW = '''      { id: "veo-3.1-generate-001", name: "Veo 3.1 (Vertex)" },
      { id: "veo-3.1-fast-generate-001", name: "Veo 3.1 Fast (Vertex)" },'''
VERTEX_SOURCE_PREVIEW_OLD = VERTEX_SOURCE_NEW
VERTEX_SOURCE_PREVIEW_NEW = '''      { id: "veo-3.1-generate-001", name: "Veo 3.1 (Vertex)" },
      { id: "veo-3.1-fast-generate-001", name: "Veo 3.1 Fast (Vertex)" },
      { id: "veo-3.1-generate-preview", name: "Veo 3.1 Preview (Vertex)" },
      { id: "veo-3.1-fast-generate-preview", name: "Veo 3.1 Fast Preview (Vertex)" },
      { id: "veo-3.1-lite-generate-preview", name: "Veo 3.1 Lite Preview (Vertex)" },'''

VERTEX_RUNTIME_OLD = 'models:[{id:"veo-3.0-generate-001",name:"Veo 3.0 (Vertex)"},{id:"veo-3.0-fast-generate-001",name:"Veo 3.0 Fast (Vertex)"},{id:"veo-2.0-generate-001",name:"Veo 2.0 (Vertex)"}]'
VERTEX_RUNTIME_NEW = 'models:[{id:"veo-3.1-generate-001",name:"Veo 3.1 (Vertex)"},{id:"veo-3.1-fast-generate-001",name:"Veo 3.1 Fast (Vertex)"}]'
VERTEX_RUNTIME_PREVIEW_OLD = VERTEX_RUNTIME_NEW
VERTEX_RUNTIME_PREVIEW_NEW = 'models:[{id:"veo-3.1-generate-001",name:"Veo 3.1 (Vertex)"},{id:"veo-3.1-fast-generate-001",name:"Veo 3.1 Fast (Vertex)"},{id:"veo-3.1-generate-preview",name:"Veo 3.1 Preview (Vertex)"},{id:"veo-3.1-fast-generate-preview",name:"Veo 3.1 Fast Preview (Vertex)"},{id:"veo-3.1-lite-generate-preview",name:"Veo 3.1 Lite Preview (Vertex)"}]'

KIE_SOURCE_OLD = '''  const payload = {
    model,
    input: {
      prompt,
      duration: body.duration ? String(body.duration) : "5",
      aspect_ratio: typeof body.aspect_ratio === "string" ? body.aspect_ratio : "16:9",
      sound: body.sound === true,
    },
  };'''
KIE_SOURCE_NEW = '''  const input: Record<string, unknown> = {
    prompt,
    duration: body.duration ? String(body.duration) : "5",
    aspect_ratio: typeof body.aspect_ratio === "string" ? body.aspect_ratio : "16:9",
    sound: body.sound === true,
  };

  // KIE Market models do not share one universal input schema.  These defaults
  // are the documented minimums for the two rows that previously failed with
  // schema errors/range errors; caller-supplied values still win.
  if (model === "kling-3.0/video") {
    input.mode = typeof body.mode === "string" ? body.mode : "std";
    input.multi_shots = typeof body.multi_shots === "boolean" ? body.multi_shots : false;
  }
  if (model === "grok-imagine/text-to-video") {
    input.mode = typeof body.mode === "string" ? body.mode : "normal";
    input.duration = body.duration ? String(body.duration) : "6";
    input.resolution = typeof body.resolution === "string" ? body.resolution : "480p";
  }

  const payload = { model, input };'''

KIE_SOURCE_TYPE_OLD = '''    aspect_ratio?: unknown;
    sound?: unknown;
    timeout_ms?: unknown;'''
KIE_SOURCE_TYPE_NEW = '''    aspect_ratio?: unknown;
    sound?: unknown;
    mode?: unknown;
    multi_shots?: unknown;
    resolution?: unknown;
    timeout_ms?: unknown;'''

KIE_RUNTIME_OLD = 'let m={model:e,input:{prompt:p,duration:a.duration?String(a.duration):"5",aspect_ratio:"string"==typeof a.aspect_ratio?a.aspect_ratio:"16:9",sound:!0===a.sound}};'
KIE_RUNTIME_NEW = '''let m={model:e,input:{prompt:p,duration:a.duration?String(a.duration):"5",aspect_ratio:"string"==typeof a.aspect_ratio?a.aspect_ratio:"16:9",sound:!0===a.sound}};"kling-3.0/video"===e&&(m.input.mode="string"==typeof a.mode?a.mode:"std",m.input.multi_shots="boolean"==typeof a.multi_shots?a.multi_shots:!1),"grok-imagine/text-to-video"===e&&(m.input.mode="string"==typeof a.mode?a.mode:"normal",m.input.duration=a.duration?String(a.duration):"6",m.input.resolution="string"==typeof a.resolution?a.resolution:"480p");'''

KIE_SOURCE_VEO_MARKER = '''  if (log) {
    const promptPreview = String(body.prompt ?? "").slice(0, 60);
    log.info("VIDEO", `${provider}/${model} (kie-video) | prompt: "${promptPreview}..."`);
  }'''
KIE_SOURCE_VEO_BRANCH = '''  if (model === "veo/veo-3-1" || model === "veo/veo-3-1-fast") {
    const kieModel = model === "veo/veo-3-1-fast" ? "veo3_fast" : "veo3";
    const veoPayload: Record<string, unknown> = {
      prompt,
      model: kieModel,
      aspect_ratio: typeof body.aspect_ratio === "string" ? body.aspect_ratio : "16:9",
      generationType: "TEXT_2_VIDEO",
      enableFallback: false,
      enableTranslation: true,
    };
    if (Array.isArray(body.imageUrls)) {
      veoPayload.imageUrls = body.imageUrls
        .filter((value): value is string => typeof value === "string" && value.length > 0)
        .slice(0, 1);
    }
    if (typeof body.resolution === "string") veoPayload.resolution = body.resolution;
    if (typeof body.callBackUrl === "string") veoPayload.callBackUrl = body.callBackUrl;

    try {
      const createResponse = await fetch(`${baseUrl}/api/v1/veo/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(veoPayload),
      });
      if (!createResponse.ok) {
        const errorText = await createResponse.text();
        return { success: false, status: createResponse.status, error: errorText.slice(0, 500) };
      }
      const createRaw = await createResponse.json();
      const createData = isJsonObject(createRaw) ? createRaw : {};
      const taskId = getKieTaskId(createData);
      if (!taskId) {
        return { success: false, status: 502, error: "KIE Veo did not return taskId" };
      }

      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        const statusResponse = await fetch(
          `${baseUrl}/api/v1/veo/record-info?taskId=${encodeURIComponent(String(taskId))}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!statusResponse.ok) {
          const errorText = await statusResponse.text();
          return { success: false, status: statusResponse.status, error: errorText.slice(0, 500) };
        }
        const statusRaw = await statusResponse.json();
        const statusRecord = isJsonObject(statusRaw) ? statusRaw : {};
        const statusData = isJsonObject(statusRecord.data) ? statusRecord.data : statusRecord;
        const successFlag = Number(statusData.successFlag);
        const responseData = isJsonObject(statusData.response) ? statusData.response : {};
        const resultUrls = Array.isArray(responseData.resultUrls)
          ? responseData.resultUrls.filter(
              (value): value is string => typeof value === "string" && value.length > 0
            )
          : [];

        if (successFlag === 1) {
          const videos = resultUrls.map((url) => ({ url, format: "mp4" }));
          if (!videos.length) {
            return { success: false, status: 502, error: "KIE Veo succeeded without result URL" };
          }
          saveCallLog({
            method: "POST",
            path: "/v1/videos/generations",
            status: 200,
            model: `${provider}/${model}`,
            provider,
            duration: Date.now() - startTime,
            responseBody: { videos_count: videos.length, taskId: String(taskId), mode: "veo-api" },
          }).catch(() => {});
          return { success: true, data: { created: Math.floor(Date.now() / 1000), data: videos } };
        }
        if (successFlag === 2) {
          const errorMessage =
            responseData.failMsg || statusData.failMsg || statusRecord.msg || "KIE Veo task failed";
          return { success: false, status: 502, error: String(errorMessage) };
        }
        await sleep(pollIntervalMs);
      }

      return { success: false, status: 504, error: `KIE Veo task timed out (taskId=${String(taskId)})` };
    } catch (err: unknown) {
      return {
        success: false,
        status: isJsonObject(err) && Number.isFinite(Number(err.status)) ? Number(err.status) : 502,
        error: sanitizeErrorMessage(err) || "KIE Veo provider error",
      };
    }
  }

'''
KIE_SOURCE_VEO_DIAGNOSTIC_OLD = '        return { success: false, status: 502, error: "KIE Veo did not return taskId" };'
KIE_SOURCE_VEO_DIAGNOSTIC_NEW = '''        const createResponseData = isJsonObject(createData.data) ? createData.data : {};
        const providerCode = createData.code ?? createResponseData.code;
        const providerMessage =
          createData.msg ?? createData.message ?? createResponseData.msg ?? createResponseData.message;
        return {
          success: false,
          status: 502,
          error:
            "KIE Veo create response missing taskId (code=" +
            String(providerCode ?? "unknown") +
            ")" +
            (providerMessage ? ": " + String(providerMessage).slice(0, 300) : ""),
        };'''
KIE_RUNTIME_VEO_MARKER = 'if(s){let r=String(a.prompt??"").slice(0,60);s.info("VIDEO",`${t}/${e} (kie-video) | prompt: "${r}..."`)}'
KIE_RUNTIME_VEO_BRANCH = '''if("veo/veo-3-1"===e||"veo/veo-3-1-fast"===e){let k="veo/veo-3-1-fast"===e?"veo3_fast":"veo3",q={prompt:p,model:k,aspect_ratio:"string"==typeof a.aspect_ratio?a.aspect_ratio:"16:9",generationType:"TEXT_2_VIDEO",enableFallback:!1,enableTranslation:!0};Array.isArray(a.imageUrls)&&(q.imageUrls=a.imageUrls.filter(e=>"string"==typeof e&&e.length>0).slice(0,1)),"string"==typeof a.resolution&&(q.resolution=a.resolution),"string"==typeof a.callBackUrl&&(q.callBackUrl=a.callBackUrl);try{let createResp=await fetch(`${c}/api/v1/veo/generate`,{method:"POST",headers:{Authorization:`Bearer ${d}`,"Content-Type":"application/json"},body:JSON.stringify(q)});if(!createResp.ok){let errText=await createResp.text();return{success:!1,status:createResp.status,error:errText.slice(0,500)}}let createRaw=await createResp.json(),createRec=(0,v.isJsonObject)(createRaw)?createRaw:{},task=(0,v.getKieTaskId)(createRec);if(!task)return{success:!1,status:502,error:"KIE Veo did not return taskId"};let deadline=Date.now()+u;for(;Date.now()<deadline;){let statusResp=await fetch(`${c}/api/v1/veo/record-info?taskId=${encodeURIComponent(String(task))}`,{headers:{Authorization:`Bearer ${d}`}});if(!statusResp.ok){let errText=await statusResp.text();return{success:!1,status:statusResp.status,error:errText.slice(0,500)}}let statusRaw=await statusResp.json(),statusRec=(0,v.isJsonObject)(statusRaw)?statusRaw:{},statusData=(0,v.isJsonObject)(statusRec.data)?statusRec.data:statusRec,flag=Number(statusData.successFlag),responseData=(0,v.isJsonObject)(statusData.response)?statusData.response:{},urls=Array.isArray(responseData.resultUrls)?responseData.resultUrls.filter(url=>"string"==typeof url&&url.length>0):[];if(1===flag){let vids=urls.map(url=>({url,format:"mp4"}));if(!vids.length)return{success:!1,status:502,error:"KIE Veo succeeded without result URL"};return(0,_.saveCallLog)({method:"POST",path:"/v1/videos/generations",status:200,model:`${t}/${e}`,provider:t,duration:Date.now()-n,responseBody:{videos_count:vids.length,taskId:String(task),mode:"veo-api"}}).catch(()=>{}),{success:!0,data:{created:Math.floor(Date.now()/1e3),data:vids}}}if(2===flag){let errorMsg=responseData.failMsg||statusData.failMsg||statusRec.msg||"KIE Veo task failed";return{success:!1,status:502,error:String(errorMsg)}}await V(l)}return{success:!1,status:504,error:`KIE Veo task timed out (taskId=${String(task)})`}}catch(err){return{success:!1,status:(0,v.isJsonObject)(err)&&Number.isFinite(Number(err.status))?Number(err.status):502,error:(0,D.sanitizeErrorMessage)(err)||"KIE Veo provider error"}}}'''
KIE_RUNTIME_VEO_DIAGNOSTIC_OLD = 'if(!task)return{success:!1,status:502,error:"KIE Veo did not return taskId"};'
KIE_RUNTIME_VEO_DIAGNOSTIC_NEW = 'if(!task){let detail=(0,v.isJsonObject)(createRec.data)?createRec.data:{},code=createRec.code??detail.code,msg=createRec.msg??createRec.message??detail.msg??detail.message;return{success:!1,status:502,error:"KIE Veo create response missing taskId (code="+String(code??"unknown")+")"+(msg?": "+String(msg).slice(0,300):"")}};'


@dataclass(frozen=True)
class Replacement:
    name: str
    relative_path: str
    old: str
    new: str
    required_count: int = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_root_from_service() -> Path | None:
    """Resolve the registered OmniRoute package without changing the service."""

    try:
        result = subprocess.run(
            ["reg", "query", r"HKLM\SYSTEM\CurrentControlSet\Services\OmniRoute\Parameters", "/v", "AppDirectory"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        if "AppDirectory" not in line:
            continue
        value = line.split("REG_SZ", 1)[-1].strip()
        candidate = Path(value)
        if candidate.name.lower() == "omniroute":
            return candidate
    return None


def resolve_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_root = os.environ.get("OMNIROUTE_DIST", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    registered = package_root_from_service()
    if registered:
        candidates.append(registered)
    candidates.append(DEFAULT_PACKAGE_ROOT)
    for candidate in candidates:
        if (candidate / "package.json").is_file() and (candidate / "dist" / "server.js").is_file():
            return candidate.resolve()
    raise FileNotFoundError("No active OmniRoute package root with package.json and dist/server.js was found")


def read_package_version(root: Path) -> str:
    data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    return str(data.get("version", ""))


def video_route_chunks(root: Path) -> list[Path]:
    route = root / "dist" / ".build" / "next" / "server" / "app" / "api" / "v1" / "videos" / "generations" / "route.js"
    if not route.is_file():
        raise FileNotFoundError(f"Video route manifest missing: {route}")
    text = route.read_text(encoding="utf-8")
    refs = re.findall(r'R\.c\("(server/chunks/[^"]+\.js)"\)', text)
    # ``route.js`` is under ``.../next/server/app/...``.  Turbopack's
    # references are rooted at ``next/server`` (the ``server/`` prefix is not
    # relative to ``.build``), so parents[5] is the actual server directory.
    server_root = route.parents[5]
    return [server_root.parent / ref for ref in refs if (server_root.parent / ref).is_file()]


def find_runtime_chunk(root: Path, old: str, new: str, label: str) -> Path:
    matches: list[Path] = []
    for path in video_route_chunks(root):
        text = path.read_text(encoding="utf-8")
        if old in text or new in text:
            matches.append(path)
    if len(matches) != 1:
        names = ", ".join(str(path) for path in matches) or "none"
        raise RuntimeError(f"Expected exactly one video-route chunk for {label}; found {len(matches)}: {names}")
    return matches[0]


def replacement_plan(root: Path) -> list[Replacement]:
    config_chunk = find_runtime_chunk(root, VERTEX_RUNTIME_OLD, VERTEX_RUNTIME_NEW, "Vertex registry")
    handler_chunk = find_runtime_chunk(root, KIE_RUNTIME_OLD, KIE_RUNTIME_NEW, "KIE handler")
    return [
        Replacement("Vertex source registry", "open-sse/config/videoRegistry.ts", VERTEX_SOURCE_OLD, VERTEX_SOURCE_NEW),
        Replacement("Vertex source preview registry", "open-sse/config/videoRegistry.ts", VERTEX_SOURCE_PREVIEW_OLD, VERTEX_SOURCE_PREVIEW_NEW),
        Replacement("KIE source request fields", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_TYPE_OLD, KIE_SOURCE_TYPE_NEW),
        Replacement("KIE source model defaults", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_OLD, KIE_SOURCE_NEW),
        Replacement("KIE source Veo API branch", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_VEO_MARKER, KIE_SOURCE_VEO_BRANCH + KIE_SOURCE_VEO_MARKER),
        Replacement("KIE source Veo response diagnostics", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_VEO_DIAGNOSTIC_OLD, KIE_SOURCE_VEO_DIAGNOSTIC_NEW),
        Replacement("Vertex compiled registry", str(config_chunk.relative_to(root)), VERTEX_RUNTIME_OLD, VERTEX_RUNTIME_NEW),
        Replacement("Vertex compiled preview registry", str(config_chunk.relative_to(root)), VERTEX_RUNTIME_PREVIEW_OLD, VERTEX_RUNTIME_PREVIEW_NEW),
        Replacement("KIE compiled model defaults", str(handler_chunk.relative_to(root)), KIE_RUNTIME_OLD, KIE_RUNTIME_NEW),
        Replacement("KIE compiled Veo API branch", str(handler_chunk.relative_to(root)), KIE_RUNTIME_VEO_MARKER, KIE_RUNTIME_VEO_BRANCH + KIE_RUNTIME_VEO_MARKER),
        Replacement("KIE compiled Veo response diagnostics", str(handler_chunk.relative_to(root)), KIE_RUNTIME_VEO_DIAGNOSTIC_OLD, KIE_RUNTIME_VEO_DIAGNOSTIC_NEW),
    ]


def check_replacement(replacement: Replacement, root: Path) -> tuple[Path, int, str, str]:
    path = root / replacement.relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Patch target missing: {path}")
    text = path.read_text(encoding="utf-8")
    old_count = text.count(replacement.old)
    new_count = text.count(replacement.new)
    # A replacement's new text may contain the old text as a prefix (the
    # minified KIE patch does this).  Presence of the complete new text is the
    # authoritative applied-state check; an extra standalone old occurrence
    # is still rejected below as ambiguous.
    if new_count == replacement.required_count and old_count in (0, replacement.required_count):
        status = "applied"
    elif old_count == replacement.required_count and new_count == 0:
        status = "pending"
    else:
        raise RuntimeError(
            f"Unexpected replacement state for {replacement.name}: "
            f"old_matches={old_count}, new_matches={new_count}, "
            f"expected old={replacement.required_count} or new={replacement.required_count}"
        )
    return path, old_count, sha256(path), status


def plan(root: Path) -> list[dict[str, object]]:
    version = read_package_version(root)
    if version != EXPECTED_VERSION:
        raise RuntimeError(f"Refusing package version {version!r}; this patch is for {EXPECTED_VERSION}")
    rows: list[dict[str, object]] = []
    for replacement in replacement_plan(root):
        path, count, digest, status = check_replacement(replacement, root)
        rows.append({"name": replacement.name, "path": str(path), "matches": count, "status": status, "sha256": digest})
    return rows


def apply(root: Path, backup_root: Path) -> dict[str, object]:
    rows = plan(root)
    pending_names = {str(row["name"]) for row in rows if row["status"] == "pending"}
    if not pending_names:
        return {
            "mode": "already_applied",
            "packageVersion": EXPECTED_VERSION,
            "packageRoot": str(root),
            "restartPerformed": False,
            "videoSpendPerformed": False,
            "replacements": rows,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    replacements = replacement_plan(root)
    manifest: list[dict[str, object]] = []

    for replacement in replacements:
        path, count, before_hash, status = check_replacement(replacement, root)
        if status == "applied":
            manifest.append({
                "name": replacement.name,
                "path": str(path),
                "status": status,
                "matches": count,
                "sha256": before_hash,
            })
            continue
        backup_path = backup_dir / replacement.relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(replacement.old, replacement.new, replacement.required_count), encoding="utf-8", newline="")
        after_hash = sha256(path)
        manifest.append({
            "name": replacement.name,
            "path": str(path),
            "backup": str(backup_path),
            "status": status,
            "matches": count,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
        })

    record = {
        "schemaVersion": 1,
        "packageVersion": EXPECTED_VERSION,
        "packageRoot": str(root),
        "appliedAt": datetime.now(timezone.utc).isoformat(),
        "restartPerformed": False,
        "videoSpendPerformed": False,
        "replacements": manifest,
    }
    record_path = backup_dir / "manifest.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="active OmniRoute package root; defaults to the registered service root")
    parser.add_argument("--backup-root", default=str(Path(__file__).resolve().parents[2] / "state" / "omni_video_runtime_backups"))
    parser.add_argument("--plan", action="store_true", help="print the exact plan; this is also the default")
    parser.add_argument("--apply", action="store_true", help="apply exact replacements after taking backups")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.apply and args.plan:
            raise ValueError("--apply and --plan are mutually exclusive")
        root = resolve_root(args.root)
        if args.apply:
            result = apply(root, Path(args.backup_root))
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"mode": "plan", "packageRoot": str(root), "replacements": plan(root)}, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
