// OMNIROUTE RELAY WORKER v3 -- permanent door + WEB-EXECUTE + PLAYWRIGHT + GATEWAY.
// Token lives in Worker secret OMNIROUTE_TOKEN (rotatable without redeploy);
// falls back to GOLD24 while secret is unset so legacy callers never break.
// Endpoints:
//   GET  /health?token=                        -> {"ok":true}
//   POST /say?token=  {body,text}              -> append order
//   GET  /say?token=&body=X&limit=N            -> {"orders":[...]}
//   POST /v1/tools/web.execute?token=          -> agent tool: edge fast path / fleet queue / playwright queue
//   GET  /v1/tools/web.result?token=&job_id=   -> fetch job result
//   POST /v1/tools/web.result?token=           -> fleet posts results here
//   POST /v1/gateway/register?token=           -> kernel registers live session {service,url,meta} (TTL 1800s)
//   GET  /v1/gateway?token=                    -> live session pool (all services)
//   ANY  /v1/gateway/route?token=&service=X&path=/... -> proxy through to a live session
// Storage: KV "LEDGER" — ledger:{body} for queues, wx:{job_id} tool jobs, gw:{service} session pool.

const DEFAULT_TOKEN = "GOLD24";
const MAX_RESULT_BYTES = 100000;   // KV result cap (base64)
const SESSION_TTL = 1800;          // gateway session liveness (30 min)

function jsonResp(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
  });
}

function b64encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

// KV writes are rate-limited (free tier 1k/day). A failed write must NEVER kill a request.
async function kvPut(env, key, value, ttl) {
  try {
    const opts = ttl ? { expirationTtl: ttl } : undefined;
    await env.LEDGER.put(key, value, opts);
    return true;
  } catch (e) {
    return false;
  }
}

async function kvGet(env, key) {
  try {
    return await env.LEDGER.get(key);
  } catch {
    return null;
  }
}

function jobId() {
  return "wx_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
}

function bytesToB64(bytes) {
  let bin = "";
  const CH = 32768;
  for (let i = 0; i < bytes.length; i += CH) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(bin);
}

// Edge fast path: Worker fetches the URL itself (public web, no login).
async function edgeFetch(spec) {
  const t0 = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), Math.min(spec.timeout_s || 15, 25) * 1000);
  try {
    const init = {
      method: spec.method || "GET",
      headers: spec.headers || { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" },
      redirect: "follow",
      signal: ctl.signal,
    };
    if (spec.body && init.method !== "GET") init.body = typeof spec.body === "string" ? spec.body : JSON.stringify(spec.body);
    const resp = await fetch(spec.url, init);
    const text = await resp.text();
    const capped = text.length > MAX_RESULT_BYTES ? text.slice(0, MAX_RESULT_BYTES) : text;
    clearTimeout(timer);
    return {
      status: "done",
      mode: "edge",
      http_status: resp.status,
      content_type: resp.headers.get("content-type") || "",
      content_b64: b64encode(capped),
      truncated: text.length > MAX_RESULT_BYTES,
      executed_by: "worker-edge",
      duration_ms: Date.now() - t0,
    };
  } catch (e) {
    clearTimeout(timer);
    return {
      status: "failed",
      mode: "edge",
      error: String(e).slice(0, 300),
      executed_by: "worker-edge",
      duration_ms: Date.now() - t0,
    };
  }
}

// Decide edge vs fleet vs playwright.
function wantsEdge(spec) {
  if (spec.mode === "fleet" || spec.mode === "playwright") return false;
  if (spec.mode === "edge") return true;
  // auto: no capture, no cookies, simple method -> edge
  const simple = ["GET", "HEAD"].includes((spec.method || "GET").toUpperCase());
  const noCapture = !spec.capture_id;
  const noCookies = !(spec.headers && (spec.headers["cookie"] || spec.headers["Cookie"]));
  return simple && noCapture && noCookies;
}

export default {
  async fetch(request, env) {
    const TOKEN = (env && env.OMNIROUTE_TOKEN) || DEFAULT_TOKEN;
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const token = url.searchParams.get("token") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    }

    if (path === "/health") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      return jsonResp({ ok: true, service: "omniroute-relay-worker", version: 3,
                        tools: ["web.execute", "web.result", "gateway"], ts: Date.now() });
    }

    if (path === "/say") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);

      if (request.method === "POST") {
        let data;
        try {
          data = await request.json();
        } catch {
          return jsonResp({ ok: false, err: "bad json" }, 400);
        }
        const body = String(data.body || "KILO").slice(0, 64);
        const text = String(data.text || "").slice(0, 20000);
        const key = "ledger:" + body;
        let arr = [];
        try {
          arr = JSON.parse((await kvGet(env, key)) || "[]");
        } catch {
          arr = [];
        }
        arr.push({ at: Date.now() / 1000, text });
        if (arr.length > 2000) arr = arr.slice(-2000);
        const stored = await kvPut(env, key, JSON.stringify(arr));
        return jsonResp({ ok: true, queued: arr.length, stored,
                          degraded: !stored ? "kv_write_limit" : undefined });
      }

      if (request.method === "GET") {
        const body = (url.searchParams.get("body") || "KILO").slice(0, 64);
        const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10) || 20, 200);
        const key = "ledger:" + body;
        let arr = [];
        try {
          arr = JSON.parse((await kvGet(env, key)) || "[]");
        } catch {
          arr = [];
        }
        return jsonResp({ orders: arr.slice(-limit), count: arr.length });
      }
    }

    // ============ AGENT TOOL: web.execute ============
    if (path === "/v1/tools/web.execute") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method !== "POST") return jsonResp({ ok: false, err: "POST required" }, 405);

      let spec;
      try {
        spec = await request.json();
      } catch {
        return jsonResp({ ok: false, err: "bad json" }, 400);
      }
      if (!spec.url || !/^https?:\/\//.test(spec.url)) {
        return jsonResp({ ok: false, err: "url required (http/https)" }, 400);
      }
      spec.timeout_s = Math.min(parseInt(spec.timeout_s || 15, 10) || 15, 30);
      const isPlaywright = spec.mode === "playwright";

      const jid = jobId();
      const job = { job_id: jid, spec, created_at: Date.now() / 1000, status: "pending" };

      if (wantsEdge(spec)) {
        const result = await edgeFetch(spec);
        const final = { ...job, ...result };
        const stored = await kvPut(env, "wx:" + jid, JSON.stringify(final), 86400);
        return jsonResp({ job_id: jid, mode: "edge", status: final.status, http_status: final.http_status || null, result: final, stored });
      }

      // fleet / playwright path: queue to Kaggle via ledger, store pending job
      const queueKey = isPlaywright ? "ledger:PLAYWRIGHT" : "ledger:WEBEXEC";
      let arr = [];
      try {
        arr = JSON.parse((await kvGet(env, queueKey)) || "[]");
      } catch {
        arr = [];
      }
      arr.push({ at: Date.now() / 1000, text: (isPlaywright ? "PW_EXECUTE:" : "WEB_EXECUTE:") + JSON.stringify({ job_id: jid, ...spec }) });
      if (arr.length > 2000) arr = arr.slice(-2000);
      const q_ok = await kvPut(env, queueKey, JSON.stringify(arr));
      const j_ok = await kvPut(env, "wx:" + jid, JSON.stringify(job), 86400);
      if (!q_ok) {
        // queue write failed (daily KV limit) -> honest error, agent falls back to edge
        return jsonResp({ ok: false, err: "queue_write_failed", job_id: jid, hint: "use edge path or retry" }, 503);
      }
      return jsonResp({ job_id: jid, mode: isPlaywright ? "playwright" : "fleet", status: "queued", stored: j_ok });
    }

    // ============ AGENT TOOL: web.result ============
    if (path === "/v1/tools/web.result") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);

      if (request.method === "GET") {
        const jid = (url.searchParams.get("job_id") || "").slice(0, 40);
        if (!jid) return jsonResp({ ok: false, err: "job_id required" }, 400);
        const raw = await kvGet(env, "wx:" + jid);
        if (!raw) return jsonResp({ ok: false, err: "unknown job_id" }, 404);
        return jsonResp(JSON.parse(raw));
      }

      if (request.method === "POST") {
        // fleet posts results here
        let data;
        try {
          data = await request.json();
        } catch {
          return jsonResp({ ok: false, err: "bad json" }, 400);
        }
        const jid = String(data.job_id || "").slice(0, 40);
        if (!jid) return jsonResp({ ok: false, err: "job_id required" }, 400);
        const raw = await kvGet(env, "wx:" + jid);
        if (!raw) return jsonResp({ ok: false, err: "unknown job_id" }, 404);
        const job = JSON.parse(raw);
        const merged = {
          ...job,
          status: data.status || "done",
          http_status: data.http_status ?? null,
          content_type: data.content_type || "",
          content_b64: String(data.content_b64 || "").slice(0, MAX_RESULT_BYTES + 40000),
          truncated: !!data.truncated,
          error: data.error || null,
          executed_by: data.executed_by || "kaggle",
          duration_ms: data.duration_ms || null,
        };
        await kvPut(env, "wx:" + jid, JSON.stringify(merged), 86400);
        return jsonResp({ ok: true, job_id: jid, status: merged.status, degraded: "result_may_not_persist" });
      }
    }

    // ============ GATEWAY: kernel session pool (inference gateway) ============
    if (path === "/v1/gateway/register") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method !== "POST") return jsonResp({ ok: false, err: "POST required" }, 405);
      let data;
      try {
        data = await request.json();
      } catch {
        return jsonResp({ ok: false, err: "bad json" }, 400);
      }
      const service = String(data.service || "").toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 40);
      const surl = String(data.url || "");
      if (!service || !/^https?:\/\//.test(surl)) {
        return jsonResp({ ok: false, err: "service and url (http/https) required" }, 400);
      }
      const session = { service, url: surl, meta: data.meta || null, ts: Date.now() / 1000 };
      const ok = await kvPut(env, "gw:" + service, JSON.stringify(session), SESSION_TTL);
      return jsonResp({ ok: true, service, stored: ok, ttl: SESSION_TTL });
    }

    if (path === "/v1/gateway") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      const sessions = [];
      try {
        const list = await env.LEDGER.list({ prefix: "gw:" });
        for (const k of (list.keys || [])) {
          const raw = await kvGet(env, k.name);
          if (!raw) continue;
          try { sessions.push(JSON.parse(raw)); } catch {}
        }
      } catch {}
      const service = (url.searchParams.get("service") || "").toLowerCase();
      if (service) {
        const s = sessions.find((x) => x.service === service);
        if (!s) return jsonResp({ ok: false, err: "no live session", service }, 503);
        return jsonResp({ ok: true, ...s, age_s: Math.round(Date.now() / 1000 - s.ts) });
      }
      return jsonResp({ ok: true, sessions, count: sessions.length });
    }

    if (path === "/v1/gateway/route") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      const service = (url.searchParams.get("service") || "").toLowerCase();
      if (!service) return jsonResp({ ok: false, err: "service required" }, 400);
      const raw = await kvGet(env, "gw:" + service);
      if (!raw) return jsonResp({ ok: false, err: "no live session", service }, 503);
      let session;
      try { session = JSON.parse(raw); } catch { return jsonResp({ ok: false, err: "corrupt session" }, 500); }
      const subpath = url.searchParams.get("path") || "/";
      const target = session.url.replace(/\/+$/, "") + (subpath.startsWith("/") ? subpath : "/" + subpath);
      const method = (url.searchParams.get("method") || request.method).toUpperCase();
      const t0 = Date.now();
      try {
        const init = { method, redirect: "follow" };
        if (request.method === "POST" && !url.searchParams.get("method")) {
          init.body = await request.text();
          init.headers = { "content-type": request.headers.get("content-type") || "application/json" };
        } else if (method !== "GET" && method !== "HEAD") {
          const bodyParam = url.searchParams.get("body");
          if (bodyParam) { init.body = bodyParam; init.headers = { "content-type": "application/json" }; }
        }
        const resp = await fetch(target, init);
        const text = await resp.text();
        const capped = text.length > MAX_RESULT_BYTES ? text.slice(0, MAX_RESULT_BYTES) : text;
        return new Response(capped, {
          status: resp.status,
          headers: { "content-type": resp.headers.get("content-type") || "text/plain",
                     "x-omniroute-session": session.url.slice(0, 100),
                     "x-omniroute-duration-ms": String(Date.now() - t0),
                     "access-control-allow-origin": "*" },
        });
      } catch (e) {
        return jsonResp({ ok: false, err: String(e).slice(0, 300), target, duration_ms: Date.now() - t0 }, 502);
      }
    }

    // ============ ASSETS: kernel supply line (app code bundles, KV up to 25MB) ============
    if (path.startsWith("/v1/assets/")) {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      const key = "asset:" + path.split("/v1/assets/")[1].replace(/[^a-z0-9_.-]/gi, "").slice(0, 48);
      if (!key || key === "asset:") return jsonResp({ ok: false, err: "asset key required" }, 400);
      if (request.method === "POST" || request.method === "PUT") {
        const raw = new Uint8Array(await request.arrayBuffer());
        if (raw.length > 20 * 1024 * 1024) return jsonResp({ ok: false, err: "asset too large (20MB cap)" }, 413);
        const ok = await kvPut(env, key, bytesToB64(raw));
        return jsonResp({ ok: true, key, bytes: raw.length, stored: ok });
      }
      if (request.method === "GET") {
        const raw = await kvGet(env, key);
        if (!raw) return jsonResp({ ok: false, err: "no such asset", key }, 404);
        return new Response(raw, {
          headers: { "content-type": "text/plain", "access-control-allow-origin": "*" },
        });
      }
    }

    return jsonResp({ ok: false, err: "not found" }, 404);
  },
};
