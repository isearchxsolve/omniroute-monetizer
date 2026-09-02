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

# VeoAIFree's WordPress AJAX poll is a long-held request: the measured local
# client sees roughly 100 seconds before an ordinary pending poll returns. The
# published executor used the same 30-second cap for every exchange, so it
# aborted the poll before the provider could answer and then retried internally.
# Keep this an exact source-plus-compiled replacement; do not broaden the patch
# to unrelated providers or change the service process here.
VEO_SOURCE_TIMEOUT_OLD = "const FETCH_TIMEOUT_MS = 30_000;"
VEO_SOURCE_TIMEOUT_NEW = "const FETCH_TIMEOUT_MS = 120_000;"
VEO_RUNTIME_TIMEOUT_OLD = 'i=setTimeout(()=>n.abort(Error("VeoAIFree request timed out")),3e4)'
VEO_RUNTIME_TIMEOUT_NEW = 'i=setTimeout(()=>n.abort(Error("VeoAIFree request timed out")),12e4)'

# Pollinations publishes a synchronous GET /video/{prompt} endpoint that returns
# raw MP4 bytes. The 3.8.50 video registry already declares `pollinations-video`,
# but the handler chain falls through to `Unsupported video format`; keep the
# source and compiled additions exact and count-checked like the earlier repairs.
POLLINATIONS_SOURCE_BRANCH_OLD = '''  if (providerConfig.format === "veoaifree-web") {
    return handleVeoAiFreeVideoGeneration({ model, provider, body, credentials, log });
  }
'''
POLLINATIONS_SOURCE_BRANCH_NEW = POLLINATIONS_SOURCE_BRANCH_OLD + '''
  if (providerConfig.format === "pollinations-video") {
    return handlePollinationsVideoGeneration({
      model,
      provider,
      providerConfig,
      body,
      credentials,
      log,
    });
  }
'''
POLLINATIONS_SOURCE_FUNCTION_MARKER = '''
async function handleComfyUIVideoGeneration'''
POLLINATIONS_SOURCE_FUNCTION = r'''
function appendPollinationsQuery(url: URL, key: string, value: unknown): void {
  if (value === undefined || value === null || value === "") return;
  const normalized = Array.isArray(value)
    ? value.filter((item) => item !== undefined && item !== null && String(item).length > 0).join("|")
    : String(value);
  if (normalized) url.searchParams.set(key, normalized);
}

function pollinationsVideoModel(model: string): string {
  const shortModel = String(model || "").split("/").pop() || "";
  // The native registry exposes `default`; the documented Pollinations video
  // endpoint defaults to Veo, so make that mapping explicit at send time.
  return shortModel === "default" ? "veo" : shortModel;
}

async function handlePollinationsVideoGeneration({
  model,
  provider,
  providerConfig,
  body,
  credentials,
  log,
}) {
  const bodyObj = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const prompt = String(bodyObj.prompt ?? "").trim();
  if (!prompt) {
    return { success: false, status: 400, error: "Pollinations video prompt is required" };
  }

  const creds = (credentials || {}) as Record<string, any>;
  const providerSpecificData =
    creds.providerSpecificData && typeof creds.providerSpecificData === "object"
      ? creds.providerSpecificData
      : {};
  const configuredBase =
    typeof providerSpecificData.baseUrl === "string" && providerSpecificData.baseUrl.trim()
      ? providerSpecificData.baseUrl.trim()
      : typeof creds.baseUrl === "string" && creds.baseUrl.trim()
        ? creds.baseUrl.trim()
        : providerConfig.baseUrl || "https://gen.pollinations.ai/video";

  let endpoint: URL;
  try {
    endpoint = new URL(`${configuredBase.replace(/\/+$/, "")}/${encodeURIComponent(prompt)}`);
  } catch {
    return { success: false, status: 502, error: "Invalid Pollinations video endpoint" };
  }

  const upstreamModel = pollinationsVideoModel(model);
  appendPollinationsQuery(endpoint, "model", upstreamModel || undefined);
  const duration = bodyObj.duration ?? bodyObj.durationSeconds;
  if (typeof duration === "number" && Number.isFinite(duration)) {
    appendPollinationsQuery(endpoint, "duration", duration);
  }
  appendPollinationsQuery(endpoint, "aspectRatio", bodyObj.aspectRatio ?? bodyObj.aspect_ratio);
  appendPollinationsQuery(endpoint, "width", bodyObj.width);
  appendPollinationsQuery(endpoint, "height", bodyObj.height);
  appendPollinationsQuery(endpoint, "resolution", bodyObj.resolution);
  appendPollinationsQuery(endpoint, "seed", bodyObj.seed);
  appendPollinationsQuery(endpoint, "audio", bodyObj.audio);
  appendPollinationsQuery(endpoint, "enhance", bodyObj.enhance);
  appendPollinationsQuery(endpoint, "safe", bodyObj.safe);
  appendPollinationsQuery(endpoint, "image", bodyObj.image ?? bodyObj.image_url ?? bodyObj.imageUrls);
  appendPollinationsQuery(
    endpoint,
    "reference_images",
    bodyObj.reference_images ?? bodyObj.referenceImages
  );
  appendPollinationsQuery(
    endpoint,
    "reference_videos",
    bodyObj.reference_videos ?? bodyObj.referenceVideos
  );
  appendPollinationsQuery(
    endpoint,
    "reference_audios",
    bodyObj.reference_audios ?? bodyObj.referenceAudios
  );

  const apiToken = creds.apiKey || creds.accessToken;
  const headers: Record<string, string> = { Accept: "video/mp4" };
  if (typeof apiToken === "string" && apiToken.trim()) {
    headers.Authorization = `Bearer ${apiToken.trim()}`;
  }
  log?.info?.("VIDEO", `Pollinations video generation: ${provider}/${upstreamModel}`);

  const startedAt = Date.now();
  try {
    const response = await fetchWithTimeout(endpoint.toString(), {
      method: "GET",
      headers,
      timeoutMs: POLLINATIONS_VIDEO_TIMEOUT_MS,
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!response.ok) {
      const providerText = new TextDecoder().decode(bytes).slice(0, 2000);
      log?.error?.("VIDEO", `Pollinations returned HTTP ${response.status}: ${providerText}`);
      return {
        success: false,
        status: response.status || 502,
        error: providerText || `Pollinations video request failed (${response.status})`,
      };
    }

    const isMp4 = bytes.length >= 8 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp";
    if (!isMp4) {
      log?.error?.("VIDEO", "Pollinations returned a non-MP4 success body");
      return {
        success: false,
        status: 502,
        error: {
          error: {
            message: "Pollinations did not return a valid MP4 artifact",
            type: "upstream_error",
            code: "VIDEO_ARTIFACT_UNAVAILABLE",
          },
        },
      };
    }

    return {
      success: true,
      data: {
        created: Math.floor(Date.now() / 1000),
        data: [{ b64_json: Buffer.from(bytes).toString("base64"), format: "mp4" }],
      },
      durationMs: Date.now() - startedAt,
    };
  } catch (err: unknown) {
    const message = sanitizeErrorMessage(err instanceof Error ? err.message : String(err));
    const timedOut = err instanceof FetchTimeoutError || (err as any)?.name === "AbortError";
    log?.error?.("VIDEO", `Pollinations ${timedOut ? "timeout" : "request error"}: ${message}`);
    return {
      success: false,
      status: timedOut ? 504 : 502,
      error: `Pollinations video ${timedOut ? "timed out" : "request failed"}: ${message}`,
    };
  }
}
'''
POLLINATIONS_SOURCE_FUNCTION_NEW = POLLINATIONS_SOURCE_FUNCTION + POLLINATIONS_SOURCE_FUNCTION_MARKER

POLLINATIONS_RUNTIME_BRANCH_OLD = r''':"adobe-firefly-video"===y.format?(0,m.handleAdobeFireflyVideoGeneration)({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):o?(0,f.handleOpenAIVideoGeneration)({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):{success:!1,status:400,error:`Unsupported video format: ${y.format}`}'''
POLLINATIONS_RUNTIME_BRANCH_NEW = r''':"adobe-firefly-video"===y.format?(0,m.handleAdobeFireflyVideoGeneration)({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):"pollinations-video"===y.format?__omniPollinationsVideo({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):o?(0,f.handleOpenAIVideoGeneration)({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):{success:!1,status:400,error:`Unsupported video format: ${y.format}`}'''
POLLINATIONS_RUNTIME_FUNCTION_MARKER = 'async function N({model:e,body:t,credentials:r,log:a})'
POLLINATIONS_RUNTIME_FUNCTION = r'''async function __omniPollinationsVideo({model:e,provider:t,providerConfig:r,body:a,credentials:o,log:s}){let n=a&&"object"==typeof a?a:{},u=String(n.prompt??"").trim();if(!u)return{success:!1,status:400,error:"Pollinations video prompt is required"};let l=o&&"object"==typeof o?o:{},d=l.providerSpecificData&&"object"==typeof l.providerSpecificData?l.providerSpecificData:{},c="string"==typeof d.baseUrl&&d.baseUrl.trim()?d.baseUrl.trim():"string"==typeof l.baseUrl&&l.baseUrl.trim()?l.baseUrl.trim():r&&r.baseUrl||"https://gen.pollinations.ai/video",f=new URL(`${c.replace(/\/+$/,"")}/${encodeURIComponent(u)}`),p=String(e||"").split("/").pop()||"",m="default"===p?"veo":p,h=(e,t)=>{if(void 0!==t&&null!==t&&""!==t){let r=Array.isArray(t)?t.filter(e=>null!=e&&String(e).length>0).join("|"):String(t);r&&f.searchParams.set(e,r)}};h("model",m||void 0);let g=n.duration??n.durationSeconds;"number"==typeof g&&Number.isFinite(g)&&h("duration",g),h("aspectRatio",n.aspectRatio??n.aspect_ratio),h("width",n.width),h("height",n.height),h("resolution",n.resolution),h("seed",n.seed),h("audio",n.audio),h("enhance",n.enhance),h("safe",n.safe),h("image",n.image??n.image_url??n.imageUrls),h("reference_images",n.reference_images??n.referenceImages),h("reference_videos",n.reference_videos??n.referenceVideos),h("reference_audios",n.reference_audios??n.referenceAudios);let v={Accept:"video/mp4"},w=l.apiKey||l.accessToken;typeof w==="string"&&w.trim()&&(v.Authorization=`Bearer ${w.trim()}`),s?.info?.("VIDEO",`Pollinations video generation: ${t}/${m}`);let b=new AbortController,y=setTimeout(()=>b.abort(),9e5);try{let e=await fetch(f.toString(),{method:"GET",headers:v,signal:b.signal}),t=new Uint8Array(await e.arrayBuffer());if(!e.ok){let r=new TextDecoder().decode(t).slice(0,2e3);return s?.error?.("VIDEO",`Pollinations returned HTTP ${e.status}: ${r}`),{success:!1,status:e.status||502,error:r||`Pollinations video request failed (${e.status})`}}if(t.length<8||"ftyp"!==String.fromCharCode(t[4],t[5],t[6],t[7]))return s?.error?.("VIDEO","Pollinations returned a non-MP4 success body"),{success:!1,status:502,error:{error:{message:"Pollinations did not return a valid MP4 artifact",type:"upstream_error",code:"VIDEO_ARTIFACT_UNAVAILABLE"}}};return{success:!0,data:{created:Math.floor(Date.now()/1e3),data:[{b64_json:Buffer.from(t).toString("base64"),format:"mp4"}]}}}catch(e){let t="AbortError"===e?.name,r=String(e?.message||e).slice(0,500);return s?.error?.("VIDEO",`Pollinations ${t?"timeout":"request error"}: ${r}`),{success:!1,status:t?504:502,error:`Pollinations video ${t?"timed out":"request failed"}: ${r}`}}finally{clearTimeout(y)}}'''
POLLINATIONS_RUNTIME_FUNCTION_NEW = POLLINATIONS_RUNTIME_FUNCTION + POLLINATIONS_RUNTIME_FUNCTION_MARKER

# Hugging Face Inference Providers routes text-to-video through Fal AI's queue
# transport. The installed huggingface_hub client measured the exact contract:
# POST /fal-ai/<mapped-model>?_subdomain=queue with a Bearer hf_ token, then
# poll the response_url-derived /status endpoint, fetch the completed result
# JSON, download its video.url, and admit only real MP4 bytes. Keep this
# provider separate from the direct Fal handler: HF routing bills the HF
# account and requires an HF token, while direct Fal keys use a different
# authentication contract.
HUGGINGFACE_SOURCE_REGISTRY_OLD = '''  pollinations: {
    id: "pollinations",
    baseUrl: "https://gen.pollinations.ai/video",
    authType: "apikey",
    authHeader: "bearer",
    format: "pollinations-video",
    models: [{ id: "default", name: "Pollinations Video (Free)" }],
  },

  minimax: {'''
HUGGINGFACE_SOURCE_REGISTRY_NEW = '''  pollinations: {
    id: "pollinations",
    baseUrl: "https://gen.pollinations.ai/video",
    authType: "apikey",
    authHeader: "bearer",
    format: "pollinations-video",
    models: [{ id: "default", name: "Pollinations Video (Free)" }],
  },

  // Hugging Face Inference Providers routes these public text-to-video model
  // IDs through Fal AI. The route mapping is intentionally explicit: do not
  // guess a provider path for an unverified model and accidentally spend a
  // credit on the wrong upstream.
  huggingface: {
    id: "huggingface",
    baseUrl: "https://router.huggingface.co",
    authType: "apikey",
    authHeader: "bearer",
    format: "huggingface-video",
    models: [
      { id: "tencent/HunyuanVideo", name: "HunyuanVideo (HF/Fal)" },
      { id: "Wan-AI/Wan2.2-TI2V-5B", name: "Wan 2.2 TI2V 5B (HF/Fal)" },
      { id: "meituan-longcat/LongCat-Video", name: "LongCat Video (HF/Fal)" },
    ],
  },

  minimax: {'''

HUGGINGFACE_RUNTIME_REGISTRY_OLD = 'pollinations:{id:"pollinations",baseUrl:"https://gen.pollinations.ai/video",authType:"apikey",authHeader:"bearer",format:"pollinations-video",models:[{id:"default",name:"Pollinations Video (Free)"}]},minimax:{'
HUGGINGFACE_RUNTIME_REGISTRY_NEW = 'pollinations:{id:"pollinations",baseUrl:"https://gen.pollinations.ai/video",authType:"apikey",authHeader:"bearer",format:"pollinations-video",models:[{id:"default",name:"Pollinations Video (Free)"}]},huggingface:{id:"huggingface",baseUrl:"https://router.huggingface.co",authType:"apikey",authHeader:"bearer",format:"huggingface-video",models:[{id:"tencent/HunyuanVideo",name:"HunyuanVideo (HF/Fal)"},{id:"Wan-AI/Wan2.2-TI2V-5B",name:"Wan 2.2 TI2V 5B (HF/Fal)"},{id:"meituan-longcat/LongCat-Video",name:"LongCat Video (HF/Fal)"}]},minimax:{'

HUGGINGFACE_SOURCE_BRANCH_OLD = POLLINATIONS_SOURCE_BRANCH_NEW
HUGGINGFACE_SOURCE_BRANCH_NEW = HUGGINGFACE_SOURCE_BRANCH_OLD + '''
  if (providerConfig.format === "huggingface-video") {
    return handleHuggingFaceVideoGeneration({
      model,
      provider,
      providerConfig,
      body,
      credentials,
      log,
    });
  }
'''

HUGGINGFACE_SOURCE_FUNCTION_MARKER = POLLINATIONS_SOURCE_FUNCTION_MARKER
HUGGINGFACE_SOURCE_FUNCTION = r'''
const HUGGINGFACE_VIDEO_TIMEOUT_MS = 900_000;
const HUGGINGFACE_VIDEO_MODEL_ROUTES: Record<string, string> = {
  "tencent/HunyuanVideo": "fal-ai/hunyuan-video",
  "Wan-AI/Wan2.2-TI2V-5B": "fal-ai/wan/v2.2-5b/text-to-video",
  "meituan-longcat/LongCat-Video": "fal-ai/longcat-video/text-to-video/480p",
};

type HuggingFaceRecord = Record<string, unknown>;

function isHuggingFaceRecord(value: unknown): value is HuggingFaceRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function huggingFaceString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function huggingFaceDiagnostic(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value.trim().slice(0, 2000);
  if (isHuggingFaceRecord(value)) {
    for (const key of ["error", "message", "detail"]) {
      const candidate = huggingFaceString(value[key]);
      if (candidate) return candidate.slice(0, 2000);
    }
  }
  return fallback;
}

function huggingFaceMp4(bytes: Uint8Array): boolean {
  return bytes.length >= 8 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp";
}

function huggingFaceHeaderToken(credentials: unknown): string | undefined {
  if (!isHuggingFaceRecord(credentials)) return undefined;
  return huggingFaceString(credentials.apiKey) || huggingFaceString(credentials.accessToken);
}

function huggingFaceNumeric(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function huggingFaceEndpoint(baseUrl: string, route: string): URL | null {
  try {
    return new URL(`${baseUrl.replace(/\/+$/, "")}/fal-ai/${route}?_subdomain=queue`);
  } catch {
    return null;
  }
}

function huggingFaceResultUrls(submitUrl: URL, responseUrl: string | undefined, requestId: string | undefined) {
  try {
    const resultUrl = new URL(
      responseUrl || `${submitUrl.toString().replace(/\?[^?]*$/, "")}/requests/${encodeURIComponent(requestId || "")}`,
      submitUrl,
    );
    const path = resultUrl.pathname.replace(/\/status\/?$/, "").replace(/\/+$/, "");
    const statusUrl = new URL(`${path}/status`, resultUrl.origin);
    resultUrl.searchParams.forEach((value, key) => statusUrl.searchParams.set(key, value));
    return { resultUrl, statusUrl };
  } catch {
    return null;
  }
}

async function huggingFaceResponse(response: Response): Promise<{ text: string; json: unknown }> {
  const text = await response.text();
  try {
    return { text, json: JSON.parse(text) };
  } catch {
    return { text, json: null };
  }
}

async function handleHuggingFaceVideoGeneration({
  model,
  provider,
  providerConfig,
  body,
  credentials,
  log,
}) {
  const startedAt = Date.now();
  const bodyObj = body && typeof body === "object" ? (body as HuggingFaceRecord) : {};
  const prompt = huggingFaceString(bodyObj.prompt);
  if (!prompt) {
    return { success: false, status: 400, error: "Hugging Face video prompt is required" };
  }

  const route = HUGGINGFACE_VIDEO_MODEL_ROUTES[model];
  if (!route) {
    return {
      success: false,
      status: 400,
      error: `Unsupported Hugging Face video model: ${model}`,
    };
  }

  const token = huggingFaceHeaderToken(credentials);
  if (!token) {
    return { success: false, status: 401, error: "Hugging Face requires an hf_ access token" };
  }
  if (!token.startsWith("hf_")) {
    return {
      success: false,
      status: 401,
      error: "Hugging Face Inference Providers requires an hf_ access token",
    };
  }

  const configuredBase =
    providerConfig && typeof providerConfig.baseUrl === "string" && providerConfig.baseUrl.trim()
      ? providerConfig.baseUrl.trim()
      : "https://router.huggingface.co";
  const submitUrl = huggingFaceEndpoint(configuredBase, route);
  if (!submitUrl) {
    return { success: false, status: 502, error: "Invalid Hugging Face video endpoint" };
  }

  const payload: HuggingFaceRecord = { prompt };
  for (const field of ["guidance_scale", "num_frames", "num_inference_steps", "seed"]) {
    const value = huggingFaceNumeric(bodyObj[field]);
    if (value !== undefined) payload[field] = field === "num_inference_steps" ? Math.floor(value) : value;
  }
  const negativePrompt = bodyObj.negative_prompt;
  if (Array.isArray(negativePrompt)) {
    const values = negativePrompt.filter((value): value is string => typeof value === "string" && value.trim());
    if (values.length) payload.negative_prompt = values;
  } else {
    const value = huggingFaceString(negativePrompt);
    if (value) payload.negative_prompt = [value];
  }
  if (isHuggingFaceRecord(bodyObj.extra_body)) {
    for (const [key, value] of Object.entries(bodyObj.extra_body)) {
      if (key !== "prompt" && key !== "model" && value !== undefined && value !== null) payload[key] = value;
    }
  }

  const requestedTimeout = huggingFaceNumeric(bodyObj.timeout_ms);
  const timeoutMs =
    requestedTimeout === undefined
      ? HUGGINGFACE_VIDEO_TIMEOUT_MS
      : Math.min(HUGGINGFACE_VIDEO_TIMEOUT_MS, Math.max(1000, requestedTimeout));
  const requestedPoll = huggingFaceNumeric(bodyObj.poll_interval_ms);
  const pollIntervalMs =
    requestedPoll === undefined ? 2500 : Math.min(30_000, Math.max(0, requestedPoll));
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  log?.info?.("VIDEO", `Hugging Face video generation: ${provider}/${model}`);
  try {
    const createResponse = await fetchWithTimeout(submitUrl.toString(), {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      timeoutMs,
    });
    const create = await huggingFaceResponse(createResponse);
    if (!createResponse.ok) {
      const diagnostic = huggingFaceDiagnostic(create.json, create.text || `Hugging Face submit failed (${createResponse.status})`);
      log?.error?.("VIDEO", `Hugging Face submit HTTP ${createResponse.status}: ${diagnostic}`);
      return { success: false, status: createResponse.status, error: diagnostic };
    }
    const createRecord = isHuggingFaceRecord(create.json) ? create.json : {};
    const requestId = huggingFaceString(createRecord.request_id);
    const responseUrl = huggingFaceString(createRecord.response_url);
    const urls = huggingFaceResultUrls(submitUrl, responseUrl, requestId);
    if (!urls) {
      return { success: false, status: 502, error: "Hugging Face submit returned invalid response_url" };
    }
    if (!requestId && !responseUrl) {
      return { success: false, status: 502, error: "Hugging Face submit returned no request_id" };
    }

    const deadline = Date.now() + timeoutMs;
    let completed = false;
    while (Date.now() < deadline) {
      const remaining = deadline - Date.now();
      const statusResponse = await fetchWithTimeout(urls.statusUrl.toString(), {
        method: "GET",
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        timeoutMs: Math.min(timeoutMs, Math.max(1000, remaining)),
      });
      const status = await huggingFaceResponse(statusResponse);
      if (!statusResponse.ok) {
        const diagnostic = huggingFaceDiagnostic(status.json, status.text || `Hugging Face status failed (${statusResponse.status})`);
        return { success: false, status: statusResponse.status, error: diagnostic };
      }
      const statusRecord = isHuggingFaceRecord(status.json) ? status.json : {};
      const state = String(statusRecord.status ?? "").toUpperCase();
      if (state === "COMPLETED") {
        completed = true;
        break;
      }
      if (["FAILED", "CANCELLED", "CANCELED", "ERROR"].includes(state)) {
        return {
          success: false,
          status: 502,
          error: `Hugging Face video job ${state.toLowerCase()}: ${huggingFaceDiagnostic(status.json, state)}`,
        };
      }
      await new Promise((resolve) => setTimeout(resolve, Math.min(pollIntervalMs, Math.max(0, deadline - Date.now()))));
    }
    if (!completed) {
      return { success: false, status: 504, error: `Hugging Face video timed out after ${timeoutMs}ms` };
    }

    const resultResponse = await fetchWithTimeout(urls.resultUrl.toString(), {
      method: "GET",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      timeoutMs: Math.min(timeoutMs, Math.max(1000, deadline - Date.now())),
    });
    const result = await huggingFaceResponse(resultResponse);
    if (!resultResponse.ok) {
      const diagnostic = huggingFaceDiagnostic(result.json, result.text || `Hugging Face result failed (${resultResponse.status})`);
      return { success: false, status: resultResponse.status, error: diagnostic };
    }
    const resultRecord = isHuggingFaceRecord(result.json) ? result.json : {};
    const videoRecord = isHuggingFaceRecord(resultRecord.video) ? resultRecord.video : {};
    const videoUrl = huggingFaceString(videoRecord.url) || huggingFaceString(resultRecord.video) || huggingFaceString(resultRecord.url);
    if (!videoUrl) {
      return { success: false, status: 502, error: "Hugging Face completed without a video URL" };
    }

    const mediaResponse = await fetchWithTimeout(new URL(videoUrl, urls.resultUrl).toString(), {
      method: "GET",
      headers: { Accept: "video/mp4" },
      timeoutMs: Math.min(timeoutMs, Math.max(1000, deadline - Date.now())),
    });
    const mediaBytes = new Uint8Array(await mediaResponse.arrayBuffer());
    if (!mediaResponse.ok) {
      const diagnostic = new TextDecoder().decode(mediaBytes).slice(0, 2000);
      return { success: false, status: mediaResponse.status, error: diagnostic || `Hugging Face media download failed (${mediaResponse.status})` };
    }
    if (!huggingFaceMp4(mediaBytes)) {
      log?.error?.("VIDEO", "Hugging Face returned a non-MP4 success body");
      return {
        success: false,
        status: 502,
        error: {
          error: {
            message: "Hugging Face did not return a valid MP4 artifact",
            type: "upstream_error",
            code: "VIDEO_ARTIFACT_UNAVAILABLE",
          },
        },
      };
    }

    saveCallLog({
      method: "POST",
      path: "/v1/videos/generations",
      status: 200,
      model: `${provider}/${model}`,
      provider,
      duration: Date.now() - startedAt,
      responseBody: { videos_count: 1, mode: "huggingface-fal", requestId: requestId || "response_url" },
    }).catch(() => {});
    return {
      success: true,
      data: {
        created: Math.floor(Date.now() / 1000),
        data: [{ b64_json: Buffer.from(mediaBytes).toString("base64"), format: "mp4" }],
      },
    };
  } catch (err: unknown) {
    const message = sanitizeErrorMessage(err instanceof Error ? err.message : String(err));
    const timedOut = err instanceof FetchTimeoutError || (err as any)?.name === "AbortError";
    log?.error?.("VIDEO", `Hugging Face ${timedOut ? "timeout" : "request error"}: ${message}`);
    return {
      success: false,
      status: timedOut ? 504 : 502,
      error: `Hugging Face video ${timedOut ? "timed out" : "request failed"}: ${message}`,
    };
  }
}
'''
HUGGINGFACE_SOURCE_FUNCTION_NEW = HUGGINGFACE_SOURCE_FUNCTION + HUGGINGFACE_SOURCE_FUNCTION_MARKER

HUGGINGFACE_RUNTIME_BRANCH_OLD = POLLINATIONS_RUNTIME_BRANCH_NEW
HUGGINGFACE_RUNTIME_BRANCH_NEW = POLLINATIONS_RUNTIME_BRANCH_NEW.replace(
    ':o?(0,f.handleOpenAIVideoGeneration)',
    ':"huggingface-video"===y.format?__omniHuggingFaceVideo({model:h,provider:i,providerConfig:y,body:e,credentials:t,log:r}):o?(0,f.handleOpenAIVideoGeneration)',
)
HUGGINGFACE_RUNTIME_FUNCTION_MARKER = POLLINATIONS_RUNTIME_FUNCTION_MARKER
HUGGINGFACE_RUNTIME_FUNCTION = r'''
const __omniHfRoutes = {
  "tencent/HunyuanVideo": "fal-ai/hunyuan-video",
  "Wan-AI/Wan2.2-TI2V-5B": "fal-ai/wan/v2.2-5b/text-to-video",
  "meituan-longcat/LongCat-Video": "fal-ai/longcat-video/text-to-video/480p",
};
const __omniHfTimeoutMs = 900_000;

function __omniHfText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function __omniHfRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function __omniHfDiagnostic(value, fallback) {
  if (typeof value === "string" && value.trim()) return value.trim().slice(0, 2000);
  if (__omniHfRecord(value)) {
    for (const key of ["error", "message", "detail"]) {
      const candidate = __omniHfText(value[key]);
      if (candidate) return candidate.slice(0, 2000);
    }
  }
  return fallback;
}

function __omniHfMp4(bytes) {
  return bytes.length >= 8 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp";
}

function __omniHfUrls(submitUrl, responseUrl, requestId) {
  try {
    const fallback = `${submitUrl.origin}${submitUrl.pathname.replace(/\/+$/, "")}/requests/${encodeURIComponent(requestId || "")}${submitUrl.search}`;
    const resultUrl = new URL(responseUrl || fallback, submitUrl);
    const path = resultUrl.pathname.replace(/\/status\/?$/, "").replace(/\/+$/, "");
    const statusUrl = new URL(`${path}/status`, resultUrl.origin);
    resultUrl.searchParams.forEach((value, key) => statusUrl.searchParams.set(key, value));
    return { resultUrl, statusUrl };
  } catch {
    return null;
  }
}

async function __omniHfRead(response) {
  const text = await response.text();
  try {
    return { text, json: JSON.parse(text) };
  } catch {
    return { text, json: null };
  }
}

async function __omniHuggingFaceVideo({ model, provider, providerConfig, body, credentials, log }) {
  const startedAt = Date.now();
  const bodyObj = body && typeof body === "object" ? body : {};
  const prompt = __omniHfText(bodyObj.prompt);
  if (!prompt) return { success: false, status: 400, error: "Hugging Face video prompt is required" };

  const route = __omniHfRoutes[model];
  if (!route) return { success: false, status: 400, error: `Unsupported Hugging Face video model: ${model}` };
  const creds = credentials && typeof credentials === "object" ? credentials : {};
  const token = __omniHfText(creds.apiKey) || __omniHfText(creds.accessToken);
  if (!token) return { success: false, status: 401, error: "Hugging Face requires an hf_ access token" };
  if (!token.startsWith("hf_")) {
    return { success: false, status: 401, error: "Hugging Face Inference Providers requires an hf_ access token" };
  }

  const configuredBase = providerConfig && typeof providerConfig.baseUrl === "string" && providerConfig.baseUrl.trim()
    ? providerConfig.baseUrl.trim()
    : "https://router.huggingface.co";
  let submitUrl;
  try {
    submitUrl = new URL(`${configuredBase.replace(/\/+$/, "")}/fal-ai/${route}?_subdomain=queue`);
  } catch {
    return { success: false, status: 502, error: "Invalid Hugging Face video endpoint" };
  }

  const payload = { prompt };
  for (const field of ["guidance_scale", "num_frames", "num_inference_steps", "seed"]) {
    const value = bodyObj[field];
    if (typeof value === "number" && Number.isFinite(value)) {
      payload[field] = field === "num_inference_steps" ? Math.floor(value) : value;
    }
  }
  const negativePrompt = bodyObj.negative_prompt;
  if (Array.isArray(negativePrompt)) {
    const values = negativePrompt.filter((value) => typeof value === "string" && value.trim());
    if (values.length) payload.negative_prompt = values;
  } else {
    const value = __omniHfText(negativePrompt);
    if (value) payload.negative_prompt = [value];
  }
  if (__omniHfRecord(bodyObj.extra_body)) {
    for (const [key, value] of Object.entries(bodyObj.extra_body)) {
      if (key !== "prompt" && key !== "model" && value !== undefined && value !== null) payload[key] = value;
    }
  }

  const requestedTimeout = bodyObj.timeout_ms;
  const timeoutMs = typeof requestedTimeout === "number" && Number.isFinite(requestedTimeout)
    ? Math.min(__omniHfTimeoutMs, Math.max(1000, requestedTimeout))
    : __omniHfTimeoutMs;
  const requestedPoll = bodyObj.poll_interval_ms;
  const pollIntervalMs = typeof requestedPoll === "number" && Number.isFinite(requestedPoll)
    ? Math.min(30_000, Math.max(0, requestedPoll))
    : 2500;
  const authHeaders = { Authorization: `Bearer ${token}`, Accept: "application/json" };
  const abortController = new AbortController();
  const timer = setTimeout(() => abortController.abort(), timeoutMs);
  log?.info?.("VIDEO", `Hugging Face video generation: ${provider}/${model}`);
  try {
    const createResponse = await fetch(submitUrl.toString(), {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: abortController.signal,
    });
    const create = await __omniHfRead(createResponse);
    if (!createResponse.ok) {
      const diagnostic = __omniHfDiagnostic(create.json, create.text || `Hugging Face submit failed (${createResponse.status})`);
      return { success: false, status: createResponse.status, error: diagnostic };
    }
    const createRecord = __omniHfRecord(create.json) ? create.json : {};
    const requestId = __omniHfText(createRecord.request_id);
    const responseUrl = __omniHfText(createRecord.response_url);
    const urls = __omniHfUrls(submitUrl, responseUrl, requestId);
    if (!urls) return { success: false, status: 502, error: "Hugging Face submit returned invalid response_url" };
    if (!requestId && !responseUrl) return { success: false, status: 502, error: "Hugging Face submit returned no request_id" };

    const deadline = Date.now() + timeoutMs;
    let completed = false;
    while (Date.now() < deadline) {
      const statusResponse = await fetch(urls.statusUrl.toString(), {
        method: "GET",
        headers: authHeaders,
        signal: abortController.signal,
      });
      const status = await __omniHfRead(statusResponse);
      if (!statusResponse.ok) {
        const diagnostic = __omniHfDiagnostic(status.json, status.text || `Hugging Face status failed (${statusResponse.status})`);
        return { success: false, status: statusResponse.status, error: diagnostic };
      }
      const statusRecord = __omniHfRecord(status.json) ? status.json : {};
      const state = String(statusRecord.status ?? "").toUpperCase();
      if (state === "COMPLETED") {
        completed = true;
        break;
      }
      if (["FAILED", "CANCELLED", "CANCELED", "ERROR"].includes(state)) {
        return { success: false, status: 502, error: `Hugging Face video job ${state.toLowerCase()}: ${__omniHfDiagnostic(status.json, state)}` };
      }
      await new Promise((resolve) => setTimeout(resolve, Math.min(pollIntervalMs, Math.max(0, deadline - Date.now()))));
    }
    if (!completed) return { success: false, status: 504, error: `Hugging Face video timed out after ${timeoutMs}ms` };

    const resultResponse = await fetch(urls.resultUrl.toString(), {
      method: "GET",
      headers: authHeaders,
      signal: abortController.signal,
    });
    const result = await __omniHfRead(resultResponse);
    if (!resultResponse.ok) {
      const diagnostic = __omniHfDiagnostic(result.json, result.text || `Hugging Face result failed (${resultResponse.status})`);
      return { success: false, status: resultResponse.status, error: diagnostic };
    }
    const resultRecord = __omniHfRecord(result.json) ? result.json : {};
    const videoRecord = __omniHfRecord(resultRecord.video) ? resultRecord.video : {};
    const videoUrl = __omniHfText(videoRecord.url) || __omniHfText(resultRecord.video) || __omniHfText(resultRecord.url);
    if (!videoUrl) return { success: false, status: 502, error: "Hugging Face completed without a video URL" };

    const mediaResponse = await fetch(new URL(videoUrl, urls.resultUrl).toString(), {
      method: "GET",
      headers: { Accept: "video/mp4" },
      signal: abortController.signal,
    });
    const mediaBytes = new Uint8Array(await mediaResponse.arrayBuffer());
    if (!mediaResponse.ok) {
      return { success: false, status: mediaResponse.status, error: new TextDecoder().decode(mediaBytes).slice(0, 2000) || `Hugging Face media download failed (${mediaResponse.status})` };
    }
    if (!__omniHfMp4(mediaBytes)) {
      log?.error?.("VIDEO", "Hugging Face returned a non-MP4 success body");
      return { success: false, status: 502, error: { error: { message: "Hugging Face did not return a valid MP4 artifact", type: "upstream_error", code: "VIDEO_ARTIFACT_UNAVAILABLE" } } };
    }
    (0,o.saveCallLog)({
      method: "POST",
      path: "/v1/videos/generations",
      status: 200,
      model: `${provider}/${model}`,
      provider,
      duration: Date.now() - startedAt,
      responseBody: { videos_count: 1, mode: "huggingface-fal", requestId: requestId || "response_url" },
    }).catch(() => {});
    return { success: true, data: { created: Math.floor(Date.now() / 1000), data: [{ b64_json: Buffer.from(mediaBytes).toString("base64"), format: "mp4" }] } };
  } catch (err) {
    const message = (0,s.sanitizeErrorMessage)(err instanceof Error ? err.message : String(err));
    const timedOut = err?.name === "AbortError";
    log?.error?.("VIDEO", `Hugging Face ${timedOut ? "timeout" : "request error"}: ${message}`);
    return { success: false, status: timedOut ? 504 : 502, error: `Hugging Face video ${timedOut ? "timed out" : "request failed"}: ${message}` };
  } finally {
    clearTimeout(timer);
  }
}
'''
HUGGINGFACE_RUNTIME_FUNCTION_NEW = HUGGINGFACE_RUNTIME_FUNCTION + HUGGINGFACE_RUNTIME_FUNCTION_MARKER


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


def find_runtime_chunk(root: Path, old: str, new: str, label: str, alternatives: tuple[str, ...] = ()) -> Path:
    matches: list[Path] = []
    for path in video_route_chunks(root):
        text = path.read_text(encoding="utf-8")
        if old in text or new in text or any(candidate in text for candidate in alternatives):
            matches.append(path)
    if len(matches) != 1:
        names = ", ".join(str(path) for path in matches) or "none"
        raise RuntimeError(f"Expected exactly one video-route chunk for {label}; found {len(matches)}: {names}")
    return matches[0]


def replacement_plan(root: Path) -> list[Replacement]:
    config_chunk = find_runtime_chunk(
        root,
        VERTEX_RUNTIME_OLD,
        VERTEX_RUNTIME_NEW,
        "Vertex registry",
        alternatives=(VERTEX_RUNTIME_PREVIEW_NEW,),
    )
    handler_chunk = find_runtime_chunk(root, KIE_RUNTIME_OLD, KIE_RUNTIME_NEW, "KIE handler")
    veoaifree_chunk = find_runtime_chunk(
        root,
        VEO_RUNTIME_TIMEOUT_OLD,
        VEO_RUNTIME_TIMEOUT_NEW,
        "VeoAIFree executor",
    )
    return [
        Replacement("Vertex source registry", "open-sse/config/videoRegistry.ts", VERTEX_SOURCE_OLD, VERTEX_SOURCE_NEW),
        Replacement("Vertex source preview registry", "open-sse/config/videoRegistry.ts", VERTEX_SOURCE_PREVIEW_OLD, VERTEX_SOURCE_PREVIEW_NEW),
        Replacement("Hugging Face source video registry", "open-sse/config/videoRegistry.ts", HUGGINGFACE_SOURCE_REGISTRY_OLD, HUGGINGFACE_SOURCE_REGISTRY_NEW),
        Replacement("KIE source request fields", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_TYPE_OLD, KIE_SOURCE_TYPE_NEW),
        Replacement("KIE source model defaults", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_OLD, KIE_SOURCE_NEW),
        Replacement("KIE source Veo API branch", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_VEO_MARKER, KIE_SOURCE_VEO_BRANCH + KIE_SOURCE_VEO_MARKER),
        Replacement("KIE source Veo response diagnostics", "open-sse/handlers/videoGeneration.ts", KIE_SOURCE_VEO_DIAGNOSTIC_OLD, KIE_SOURCE_VEO_DIAGNOSTIC_NEW),
        Replacement("Vertex compiled registry", str(config_chunk.relative_to(root)), VERTEX_RUNTIME_OLD, VERTEX_RUNTIME_NEW),
        Replacement("Vertex compiled preview registry", str(config_chunk.relative_to(root)), VERTEX_RUNTIME_PREVIEW_OLD, VERTEX_RUNTIME_PREVIEW_NEW),
        Replacement("Hugging Face compiled video registry", str(config_chunk.relative_to(root)), HUGGINGFACE_RUNTIME_REGISTRY_OLD, HUGGINGFACE_RUNTIME_REGISTRY_NEW),
        Replacement("KIE compiled model defaults", str(handler_chunk.relative_to(root)), KIE_RUNTIME_OLD, KIE_RUNTIME_NEW),
        Replacement("KIE compiled Veo API branch", str(handler_chunk.relative_to(root)), KIE_RUNTIME_VEO_MARKER, KIE_RUNTIME_VEO_BRANCH + KIE_RUNTIME_VEO_MARKER),
        Replacement("KIE compiled Veo response diagnostics", str(handler_chunk.relative_to(root)), KIE_RUNTIME_VEO_DIAGNOSTIC_OLD, KIE_RUNTIME_VEO_DIAGNOSTIC_NEW),
        Replacement("VeoAIFree source AJAX timeout", "open-sse/executors/veoaifree-web.ts", VEO_SOURCE_TIMEOUT_OLD, VEO_SOURCE_TIMEOUT_NEW),
        Replacement("VeoAIFree compiled AJAX timeout", str(veoaifree_chunk.relative_to(root)), VEO_RUNTIME_TIMEOUT_OLD, VEO_RUNTIME_TIMEOUT_NEW),
        Replacement(
            "Pollinations source video branch",
            "open-sse/handlers/videoGeneration.ts",
            POLLINATIONS_SOURCE_BRANCH_OLD,
            POLLINATIONS_SOURCE_BRANCH_NEW,
        ),
        Replacement(
            "Pollinations source video handler",
            "open-sse/handlers/videoGeneration.ts",
            POLLINATIONS_SOURCE_FUNCTION_MARKER,
            POLLINATIONS_SOURCE_FUNCTION_NEW,
        ),
        Replacement(
            "Pollinations compiled video branch",
            str(handler_chunk.relative_to(root)),
            POLLINATIONS_RUNTIME_BRANCH_OLD,
            POLLINATIONS_RUNTIME_BRANCH_NEW,
        ),
        Replacement(
            "Pollinations compiled video handler",
            str(handler_chunk.relative_to(root)),
            POLLINATIONS_RUNTIME_FUNCTION_MARKER,
            POLLINATIONS_RUNTIME_FUNCTION_NEW,
        ),
        Replacement(
            "Hugging Face source video branch",
            "open-sse/handlers/videoGeneration.ts",
            HUGGINGFACE_SOURCE_BRANCH_OLD,
            HUGGINGFACE_SOURCE_BRANCH_NEW,
        ),
        Replacement(
            "Hugging Face source video handler",
            "open-sse/handlers/videoGeneration.ts",
            HUGGINGFACE_SOURCE_FUNCTION_MARKER,
            HUGGINGFACE_SOURCE_FUNCTION_NEW,
        ),
        Replacement(
            "Hugging Face compiled video branch",
            str(handler_chunk.relative_to(root)),
            HUGGINGFACE_RUNTIME_BRANCH_OLD,
            HUGGINGFACE_RUNTIME_BRANCH_NEW,
        ),
        Replacement(
            "Hugging Face compiled video handler",
            str(handler_chunk.relative_to(root)),
            HUGGINGFACE_RUNTIME_FUNCTION_MARKER,
            HUGGINGFACE_RUNTIME_FUNCTION_NEW,
        ),
    ]


def check_replacement(replacement: Replacement, root: Path) -> tuple[Path, int, str, str]:
    path = root / replacement.relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Patch target missing: {path}")
    text = path.read_text(encoding="utf-8")
    old_count = text.count(replacement.old)
    new_count = text.count(replacement.new)
    # The KIE diagnostic follow-up intentionally changes one line inside the
    # already-applied dedicated branch.  Its original whole-branch `new` text
    # can therefore no longer match byte-for-byte, but the branch is still
    # applied when its marker and the exact diagnostic block are both present.
    # Treat that superseded state as applied so a later registry patch cannot
    # accidentally reinsert a second KIE branch.
    diagnostic_applied = (
        replacement.name == "KIE source Veo API branch"
        and old_count == replacement.required_count
        and KIE_SOURCE_VEO_DIAGNOSTIC_NEW in text
    ) or (
        replacement.name == "KIE compiled Veo API branch"
        and old_count == replacement.required_count
        and KIE_RUNTIME_VEO_DIAGNOSTIC_NEW in text
    )
    if diagnostic_applied:
        return path, old_count, sha256(path), "applied"
    # The preview-registry follow-up appends three models, so the original
    # minified two-model registry text (which ends in `}]`) is no longer a
    # substring.  Recognize the exact final registry as applied to keep the
    # patch plan idempotent across that expansion.
    preview_registry_applied = (
        replacement.name == "Vertex source registry"
        and VERTEX_SOURCE_PREVIEW_NEW in text
    ) or (
        replacement.name == "Vertex compiled registry"
        and VERTEX_RUNTIME_PREVIEW_NEW in text
    )
    if preview_registry_applied:
        return path, old_count, sha256(path), "applied"
    # Follow-up provider helpers/branches are inserted immediately before the
    # shared fallback marker. Once a later helper is present, the earlier
    # helper+marker pair is no longer contiguous even though the earlier
    # provider is already wired. Recognize those exact markers so rerunning the
    # deterministic patch cannot duplicate top-level functions or branches.
    if replacement.name == "Pollinations source video handler" and POLLINATIONS_SOURCE_FUNCTION in text:
        return path, old_count, sha256(path), "applied"
    if replacement.name == "Pollinations compiled video handler" and POLLINATIONS_RUNTIME_FUNCTION in text:
        return path, old_count, sha256(path), "applied"
    if replacement.name == "Pollinations compiled video branch" and '"pollinations-video"===y.format?__omniPollinationsVideo' in text:
        return path, old_count, sha256(path), "applied"
    if replacement.name == "Hugging Face source video handler" and HUGGINGFACE_SOURCE_FUNCTION in text:
        return path, old_count, sha256(path), "applied"
    if replacement.name == "Hugging Face compiled video handler" and HUGGINGFACE_RUNTIME_FUNCTION in text:
        return path, old_count, sha256(path), "applied"
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
    backed_up_paths: set[Path] = set()

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
        # Several exact replacements can target one file (the video handler
        # branch plus its helper). Preserve the first pre-edit bytes once; a
        # second `copy2` here would overwrite the recovery image with a
        # partially patched file.
        if path not in backed_up_paths:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
            backed_up_paths.add(path)
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
