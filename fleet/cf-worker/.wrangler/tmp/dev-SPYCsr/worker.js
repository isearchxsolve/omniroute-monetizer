var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/web_job_coordinator.js
var WebJobCoordinator = class {
  static {
    __name(this, "WebJobCoordinator");
  }
  constructor(ctx) {
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe TEXT UNIQUE, body TEXT NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS job (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)");
  }
  read() {
    const rows = [...this.sql.exec("SELECT body FROM job WHERE id=1")];
    return rows.length ? JSON.parse(rows[0].body) : null;
  }
  write(job) {
    this.sql.exec("INSERT INTO job(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", JSON.stringify(job));
  }
  reply(value, status = 200) {
    return Response.json(value, { status });
  }
  async fetch(request) {
    const action = new URL(request.url).pathname;
    const input = request.method === "POST" ? await request.json() : {};
    if (action === "/append") {
      this.sql.exec("INSERT OR IGNORE INTO orders(dedupe,body) VALUES(?,?)", input.dedupe, JSON.stringify(input.order));
      this.sql.exec("DELETE FROM orders WHERE id NOT IN (SELECT id FROM orders ORDER BY id DESC LIMIT 2000)");
      return this.reply({ ok: true });
    }
    if (action === "/orders") {
      const orders = [...this.sql.exec("SELECT body FROM orders ORDER BY id DESC LIMIT 2000")].reverse().map((row) => JSON.parse(row.body));
      return this.reply({ orders });
    }
    let job = this.read();
    if (action === "/get") return this.reply(job || { err: "unknown_job" }, job ? 200 : 404);
    if (action === "/register") {
      if (!job) {
        job = input.job;
        this.write(job);
      }
      return this.reply({ ok: true, job });
    }
    if (!job) return this.reply({ err: "unknown_job" }, 404);
    if (action === "/claim") {
      const generation = job.spec._queue_generation;
      const executor = job.spec.mode === "playwright" ? "playwright" : "fleet";
      if (input.generation !== generation || input.executor !== executor)
        return this.reply({ claimed: false, reason: "stale_generation_or_wrong_executor" });
      if (!["pending", "queued", "queued_cold_harvest", "healing_in_playwright"].includes(job.status))
        return this.reply({ claimed: false, reason: "not_pending" });
      if (job.lease && job.lease.expires_at > Date.now())
        return this.reply({ claimed: false, reason: "leased" });
      if (job.lease && !["GET", "HEAD"].includes((job.spec.method || "GET").toUpperCase())) {
        job.status = "failed";
        job.error = "execution lease expired; remote side-effect state unknown";
        this.write(job);
        return this.reply({ claimed: false, reason: "side_effect_state_unknown" });
      }
      job.lease = { token: crypto.randomUUID(), expires_at: Date.now() + 18e4 };
      this.write(job);
      return this.reply({ claimed: true, spec: { ...job.spec, job_id: job.job_id, _lease_token: job.lease.token } });
    }
    if (action === "/update") {
      if (!job.lease || input.lease !== job.lease.token || input.generation !== job.spec._queue_generation || job.lease.expires_at <= Date.now())
        return this.reply({ ok: false, err: "stale_or_missing_execution_lease" }, 409);
      const next = input.job;
      if (next.job_id !== job.job_id) return this.reply({ ok: false, err: "job_mismatch" }, 409);
      next.lease = null;
      this.write(next);
      return this.reply({ ok: true });
    }
    return this.reply({ err: "unknown_action" }, 404);
  }
};

// src/worker.js
var DEFAULT_TOKEN = "GOLD24";
var MAX_RESULT_BYTES = 1e5;
var SESSION_TTL = 1800;
function jsonResp(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "access-control-allow-origin": "*" }
  });
}
__name(jsonResp, "jsonResp");
function b64encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
__name(b64encode, "b64encode");
async function kvPut(env, key, value, ttl) {
  try {
    const opts = ttl ? { expirationTtl: ttl } : void 0;
    await env.LEDGER.put(key, value, opts);
    return true;
  } catch (e) {
    return false;
  }
}
__name(kvPut, "kvPut");
async function kvGet(env, key) {
  try {
    return await env.LEDGER.get(key);
  } catch {
    return null;
  }
}
__name(kvGet, "kvGet");
function jobId() {
  return "wx_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
}
__name(jobId, "jobId");
function validCaptureId(value) {
  return typeof value === "string" && /^[A-Za-z0-9_.-]{1,160}$/.test(value);
}
__name(validCaptureId, "validCaptureId");
function publicCaptureTarget(value) {
  try {
    const target = new URL(value);
    return target.protocol === "https:" && !target.username && !target.password && !Array.from(target.searchParams.keys()).some((key) => /token|secret|password|key|session|auth/i.test(key));
  } catch {
    return false;
  }
}
__name(publicCaptureTarget, "publicCaptureTarget");
async function coordinateJob(env, jid, action, data) {
  if (!env.WEB_JOBS) throw new Error("web_job_coordinator_binding_required");
  const stub = env.WEB_JOBS.get(env.WEB_JOBS.idFromName(jid));
  return stub.fetch("https://coordinator/" + action, data === void 0 ? {} : {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data)
  });
}
__name(coordinateJob, "coordinateJob");
async function getWebJob(env, jid) {
  const response = await coordinateJob(env, jid, "get");
  if (response.ok) return response.json();
  const raw = await kvGet(env, "wx:" + jid);
  return raw ? JSON.parse(raw) : null;
}
__name(getWebJob, "getWebJob");
async function enqueueWebJob(env, job) {
  job.spec._queue_generation = job.spec._queue_generation || 1;
  const registered = await coordinateJob(env, job.job_id, "register", { job });
  if (!registered.ok) return false;
  const pw = job.spec.mode === "playwright";
  const queueKey = pw ? "ledger:PLAYWRIGHT" : "ledger:WEBEXEC";
  const order = { at: Date.now() / 1e3, text: (pw ? "PW_EXECUTE:" : "WEB_EXECUTE:") + JSON.stringify({ ...job.spec, job_id: job.job_id }) };
  const queued = await coordinateJob(env, queueKey, "append", { order, dedupe: job.job_id + ":" + job.spec._queue_generation });
  if (!queued.ok) return false;
  await kvPut(env, "wx:" + job.job_id, JSON.stringify(job), 86400);
  return true;
}
__name(enqueueWebJob, "enqueueWebJob");
function bytesToB64(bytes) {
  let bin = "";
  const CH = 32768;
  for (let i = 0; i < bytes.length; i += CH) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(bin);
}
__name(bytesToB64, "bytesToB64");
async function edgeFetch(spec) {
  const t0 = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), Math.min(spec.timeout_s || 15, 25) * 1e3);
  try {
    const init = {
      method: spec.method || "GET",
      headers: spec.headers || { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" },
      redirect: "follow",
      signal: ctl.signal
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
      duration_ms: Date.now() - t0
    };
  } catch (e) {
    clearTimeout(timer);
    return {
      status: "failed",
      mode: "edge",
      error: String(e).slice(0, 300),
      executed_by: "worker-edge",
      duration_ms: Date.now() - t0
    };
  }
}
__name(edgeFetch, "edgeFetch");
function wantsEdge(spec) {
  if (spec.mode === "fleet" || spec.mode === "playwright") return false;
  if (spec.mode === "edge") return true;
  const simple = ["GET", "HEAD"].includes((spec.method || "GET").toUpperCase());
  const noCapture = !spec.capture_id;
  const noCookies = !(spec.headers && (spec.headers["cookie"] || spec.headers["Cookie"]));
  return simple && noCapture && noCookies;
}
__name(wantsEdge, "wantsEdge");
var worker_default = {
  async fetch(request, env) {
    const TOKEN = env && env.OMNIROUTE_TOKEN || DEFAULT_TOKEN;
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const token = url.searchParams.get("token") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "content-type"
        }
      });
    }
    if (path === "/health") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      return jsonResp({
        ok: true,
        service: "omniroute-relay-worker",
        version: "3.3.0-fenced-graduation",
        tools: ["web.execute", "web.result", "gateway"],
        ts: Date.now()
      });
    }
    if (path === "/v1/captures/status") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method !== "GET") return jsonResp({ ok: false, err: "GET required" }, 405);
      const id = url.searchParams.get("capture_id");
      if (!validCaptureId(id)) return jsonResp({ ok: false, err: "invalid capture_id" }, 400);
      const raw = await kvGet(env, "capture:" + id);
      if (!raw) return jsonResp({ ok: true, exists_in_kv: false, requested_id: id });
      let cap;
      try {
        cap = JSON.parse(raw);
      } catch {
        return jsonResp({ ok: false, err: "invalid stored capture" }, 500);
      }
      const target = new URL(cap.request.url);
      return jsonResp({
        ok: true,
        exists_in_kv: true,
        requested_id: id,
        active_version_id: cap.capture_id,
        execution_pin: cap.execution_pin,
        verification: cap.verification,
        synthesized_at: cap.synthesized_at,
        target_method: cap.request.method,
        target_url: target.origin + target.pathname,
        observed_body_sha256: cap.observed_body_sha256,
        sentinel: cap.sentinel,
        shadow_proof: cap.shadow_proof
      });
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
        const text = String(data.text || "").slice(0, 2e4);
        if (/BUILD_SAAS:|RENDER_VIDEO:/.test(text)) {
          return jsonResp({ ok: false, stored: false, err: "legacy_build_render_backend_retired" }, 503);
        }
        if (body === "OMNIROUTE_OUT") {
          let output;
          try {
            output = JSON.parse(text);
          } catch {
            output = null;
          }
          if (["oiioii_film_kit", "emergentsh"].includes(output?.service) && output?.status === "COMPLETED") {
            return jsonResp({ ok: false, stored: false, err: "legacy_completion_has_no_artifact_proof" }, 422);
          }
        }
        if (body === "TUNNELDBG" && /Failed building wheel|pip exception:|dependency install failed/.test(text) && !/\[\d+\]/.test(text)) {
          return jsonResp({ ok: true, queued: -1, stored: false, filtered: "retry_noise" });
        }
        const key = "ledger:" + body;
        let arr = [];
        try {
          arr = JSON.parse(await kvGet(env, key) || "[]");
        } catch {
          arr = [];
        }
        arr.push({ at: Date.now() / 1e3, text });
        if (arr.length > 2e3) arr = arr.slice(-2e3);
        const stored = await kvPut(env, key, JSON.stringify(arr));
        return jsonResp({
          ok: true,
          queued: arr.length,
          stored,
          degraded: !stored ? "kv_write_limit" : void 0
        });
      }
      if (request.method === "GET") {
        const body = (url.searchParams.get("body") || "KILO").slice(0, 64);
        const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10) || 20, 200);
        const key = "ledger:" + body;
        let arr = [];
        try {
          arr = JSON.parse(await kvGet(env, key) || "[]");
        } catch {
          arr = [];
        }
        if (["WEBEXEC", "PLAYWRIGHT"].includes(body)) {
          const response = await coordinateJob(env, key, "orders");
          if (!response.ok) return response;
          const current = (await response.json()).orders;
          arr = [...arr, ...current];
        }
        return jsonResp({ orders: arr.slice(-limit), count: arr.length });
      }
    }
    if (path === "/v1/tools/web.execute") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method !== "POST") return jsonResp({ ok: false, err: "POST required" }, 405);
      let spec;
      try {
        spec = await request.json();
      } catch {
        return jsonResp({ ok: false, err: "bad json" }, 400);
      }
      if (spec.capture_id !== void 0) {
        if (!validCaptureId(spec.capture_id)) return jsonResp({ ok: false, err: "invalid capture_id" }, 400);
        if ((spec.method || "GET").toUpperCase() !== "GET" || spec.cookies || Object.keys(spec.headers || {}).some((key) => /authorization|cookie|token|secret|api.key/i.test(key))) {
          return jsonResp({ ok: false, err: "capture_contract_public_get_only" }, 400);
        }
        const raw = await kvGet(env, "capture:" + spec.capture_id);
        if (raw) {
          let cap;
          try {
            cap = JSON.parse(raw);
          } catch {
            return jsonResp({ ok: false, err: "invalid stored capture" }, 500);
          }
          spec.url = cap.request.url;
          if (cap.execution_pin === "wire_verified") {
            spec.capture_recipe = cap;
            spec.mode = "fleet";
          } else {
            spec.harvest = true;
            spec.mode = "playwright";
          }
        } else {
          spec.harvest = true;
          spec.mode = "playwright";
        }
        if (!publicCaptureTarget(spec.url)) return jsonResp({ ok: false, err: "public_https_capture_url_required" }, 400);
      }
      if (!spec.url || !/^https?:\/\//.test(spec.url)) {
        return jsonResp({ ok: false, err: "url required (http/https)" }, 400);
      }
      spec.timeout_s = Math.min(parseInt(spec.timeout_s || 15, 10) || 15, 30);
      const isPlaywright = spec.mode === "playwright";
      const jid = jobId();
      const job = { job_id: jid, spec, created_at: Date.now() / 1e3, status: "pending" };
      if (wantsEdge(spec)) {
        const result = await edgeFetch(spec);
        const final = { ...job, ...result };
        const stored = await kvPut(env, "wx:" + jid, JSON.stringify(final), 86400);
        return jsonResp({ job_id: jid, mode: "edge", status: final.status, http_status: final.http_status || null, result: final, stored });
      }
      const queued = await enqueueWebJob(env, job);
      if (!queued) {
        return jsonResp({ ok: false, err: "queue_write_failed", job_id: jid, hint: "use edge path or retry" }, 503);
      }
      return jsonResp({ job_id: jid, mode: isPlaywright ? "playwright" : "fleet", status: spec.harvest ? "queued_cold_harvest" : "queued", stored: true });
    }
    if (path === "/v1/tools/web.claim") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method !== "POST") return jsonResp({ ok: false, err: "POST required" }, 405);
      let data;
      try {
        data = await request.json();
      } catch {
        return jsonResp({ err: "bad json" }, 400);
      }
      if (!/^wx_[a-f0-9]{12}$/.test(data.job_id || "")) return jsonResp({ err: "invalid job_id" }, 400);
      return coordinateJob(env, data.job_id, "claim", data);
    }
    if (path === "/v1/tools/web.result") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      if (request.method === "GET") {
        const jid = (url.searchParams.get("job_id") || "").slice(0, 40);
        if (!jid) return jsonResp({ ok: false, err: "job_id required" }, 400);
        const job = await getWebJob(env, jid);
        if (!job) return jsonResp({ ok: false, err: "unknown job_id" }, 404);
        const publicJob = { ...job };
        delete publicJob.lease;
        return jsonResp(publicJob);
      }
      if (request.method === "POST") {
        let data;
        try {
          data = await request.json();
        } catch {
          return jsonResp({ ok: false, err: "bad json" }, 400);
        }
        const jid = String(data.job_id || "").slice(0, 40);
        if (!jid) return jsonResp({ ok: false, err: "job_id required" }, 400);
        const job = await getWebJob(env, jid);
        if (!job) return jsonResp({ ok: false, err: "unknown job_id" }, 404);
        if (job.spec._queue_generation && (!job.lease || data._lease_token !== job.lease.token || data._queue_generation !== job.spec._queue_generation || job.lease.expires_at <= Date.now()))
          return jsonResp({ ok: false, err: "stale_or_missing_execution_lease" }, 409);
        if (["done", "failed"].includes(job.status)) return jsonResp({ ok: true, job_id: jid, status: job.status, duplicate_result_ignored: true });
        if (job.spec.harvest && data.status === "done" && !data.graduated_capture) {
          return jsonResp({ ok: false, err: "graduation_proof_missing" }, 503);
        }
        if (job.spec.capture_recipe && data.status === "done") {
          const sentinel = job.spec.capture_recipe.sentinel || {};
          let pass = false;
          try {
            const decoded = atob(String(data.content_b64 || ""));
            pass = data.http_status === sentinel.expect_status && decoded.length >= (sentinel.min_bytes || 1) && (!sentinel.content_type || String(data.content_type).split(";")[0].trim() === sentinel.content_type);
            if (sentinel.require_json_keys?.length || sentinel.content_type === "application/json") {
              const obj = JSON.parse(new TextDecoder().decode(Uint8Array.from(decoded, (ch) => ch.charCodeAt(0))));
              pass = pass && obj !== null && typeof obj === "object" && !Array.isArray(obj) && (sentinel.require_json_keys || []).every((key) => Object.hasOwn(obj, key)) && !(obj.error || obj.errors || obj.success === false || obj.login_required);
            }
          } catch {
            pass = false;
          }
          if (!pass) {
            data.status = "sentinel_failed";
            data.error = "door_rejected_wire_sentinel";
          }
        }
        if (data.status === "sentinel_failed" && job.spec.capture_id) {
          if ((job.spec.heal_attempts || 0) >= 1) {
            data.status = "failed";
            data.error = "capture_healing_limit_reached";
          } else {
            const previous = job.spec.capture_id;
            const next = /\.v\d+$/.test(previous) ? previous.replace(/\.v(\d+)$/, (_, n) => ".v" + (Number(n) + 1)) : previous + ".v2";
            job.spec = {
              ...job.spec,
              capture_id: next,
              replaces_capture_id: previous,
              mode: "playwright",
              harvest: true,
              heal_attempts: (job.spec.heal_attempts || 0) + 1,
              _queue_generation: (job.spec._queue_generation || 0) + 1
            };
            delete job.spec.capture_recipe;
            job.status = "healing_in_playwright";
            const advance = await coordinateJob(env, jid, "update", { job, lease: data._lease_token, generation: data._queue_generation });
            if (!advance.ok) return advance;
            if (!await enqueueWebJob(env, job)) return jsonResp({ ok: false, err: "healing_queue_write_failed" }, 503);
            return jsonResp({ ok: true, job_id: jid, status: job.status, stored: true });
          }
        }
        let graduated = null;
        let captureToStore = null;
        if (data.graduated_capture) {
          const cap = data.graduated_capture;
          const allowed = cap.capture_id === job.spec.capture_id && validCaptureId(cap.capture_id) && cap.authenticated === false && cap.request?.method === "GET" && publicCaptureTarget(cap.request.url) && !cap.request.cookies && !Object.keys(cap.request.headers || {}).length && ["wire_verified", "playwright"].includes(cap.execution_pin) && (cap.execution_pin !== "wire_verified" || cap.verification === "shadow_curl_passed" && cap.shadow_proof?.status === "done" && cap.shadow_proof?.http_status === 200);
          if (!allowed) return jsonResp({ ok: false, err: "invalid_graduation_proof" }, 400);
          captureToStore = cap;
          graduated = { capture_id: cap.capture_id, execution_pin: cap.execution_pin, verification: cap.verification };
        }
        const merged = {
          ...job,
          status: data.status || "done",
          http_status: data.http_status ?? null,
          content_type: data.content_type || "",
          content_b64: String(data.content_b64 || "").slice(0, MAX_RESULT_BYTES + 4e4),
          truncated: !!data.truncated,
          error: data.error || null,
          executed_by: data.executed_by || "kaggle",
          duration_ms: data.duration_ms || null,
          graduated_capture: graduated
        };
        if (job.spec._queue_generation) {
          const accepted = await coordinateJob(env, jid, "update", { job: merged, lease: data._lease_token, generation: data._queue_generation });
          if (!accepted.ok) return accepted;
        }
        if (captureToStore) {
          if (!await kvPut(env, "capture:" + captureToStore.capture_id, JSON.stringify(captureToStore)))
            return jsonResp({ ok: false, err: "graduation_write_failed" }, 503);
          if (job.spec.replaces_capture_id && !await kvPut(env, "capture:" + job.spec.replaces_capture_id, JSON.stringify(captureToStore)))
            return jsonResp({ ok: false, err: "capture_alias_write_failed" }, 503);
        }
        const stored = await kvPut(env, "wx:" + jid, JSON.stringify(merged), 86400);
        return jsonResp({ ok: stored, job_id: jid, status: merged.status, stored }, stored ? 200 : 503);
      }
    }
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
      const session = { service, url: surl, meta: data.meta || null, ts: Date.now() / 1e3 };
      const ok = await kvPut(env, "gw:" + service, JSON.stringify(session), SESSION_TTL);
      return jsonResp({ ok: true, service, stored: ok, ttl: SESSION_TTL });
    }
    if (path === "/v1/gateway") {
      if (token !== TOKEN) return jsonResp({ ok: false, err: "bad token" }, 403);
      const sessions = [];
      try {
        const list = await env.LEDGER.list({ prefix: "gw:" });
        for (const k of list.keys || []) {
          const raw = await kvGet(env, k.name);
          if (!raw) continue;
          try {
            sessions.push(JSON.parse(raw));
          } catch {
          }
        }
      } catch {
      }
      const service = (url.searchParams.get("service") || "").toLowerCase();
      if (service) {
        const s = sessions.find((x) => x.service === service);
        if (!s) return jsonResp({ ok: false, err: "no live session", service }, 503);
        return jsonResp({ ok: true, ...s, age_s: Math.round(Date.now() / 1e3 - s.ts) });
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
      try {
        session = JSON.parse(raw);
      } catch {
        return jsonResp({ ok: false, err: "corrupt session" }, 500);
      }
      const subpath = url.searchParams.get("path") || "/";
      const target = session.url.replace(/\/+$/, "") + (subpath.startsWith("/") ? subpath : "/" + subpath);
      const method = (url.searchParams.get("method") || request.method).toUpperCase();
      const t0 = Date.now();
      try {
        const headers = new Headers();
        for (const name of ["authorization", "cookie", "content-type", "accept", "range", "if-range", "if-none-match", "if-modified-since"]) {
          const value = request.headers.get(name);
          if (value !== null) headers.set(name, value);
        }
        const init = { method, redirect: "manual", headers };
        if (request.method === "POST" && !url.searchParams.get("method")) {
          init.body = request.body;
        } else if (method !== "GET" && method !== "HEAD") {
          const bodyParam = url.searchParams.get("body");
          if (bodyParam) {
            init.body = bodyParam;
            headers.set("content-type", "application/json");
          } else if (request.method === method) init.body = request.body;
        }
        const resp = await fetch(target, init);
        const resultHeaders = new Headers({
          "content-type": resp.headers.get("content-type") || "application/octet-stream",
          "cache-control": resp.headers.get("cache-control") || "private, no-store",
          "x-omniroute-duration-ms": String(Date.now() - t0),
          "access-control-allow-origin": "*"
        });
        for (const name of ["content-disposition", "content-range", "accept-ranges", "etag", "last-modified"]) {
          const value = resp.headers.get(name);
          if (value !== null) resultHeaders.set(name, value);
        }
        const location = resp.headers.get("location");
        if (location) {
          const next = new URL(location, target);
          if (next.origin !== new URL(session.url).origin) return jsonResp({ ok: false, err: "cross_origin_redirect_refused" }, 502);
          const routed = new URL(request.url);
          routed.searchParams.set("path", next.pathname + next.search);
          resultHeaders.set("location", routed.toString());
        }
        return new Response(resp.body, { status: resp.status, headers: resultHeaders });
      } catch (e) {
        return jsonResp({ ok: false, err: String(e).slice(0, 300), target, duration_ms: Date.now() - t0 }, 502);
      }
    }
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
          headers: { "content-type": "text/plain", "access-control-allow-origin": "*" }
        });
      }
    }
    return jsonResp({ ok: false, err: "not found" }, 404);
  }
};

// C:/Users/Admin/AppData/Local/npm-cache/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// C:/Users/Admin/AppData/Local/npm-cache/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    const body = JSON.stringify(error);
    const headers = {
      "Content-Type": "application/json",
      "MF-Experimental-Error-Stack": "true"
    };
    const encoded = encodeURIComponent(body);
    if (encoded.length <= 8192) {
      headers["MF-Experimental-Error-Stack-Payload"] = encoded;
    }
    return new Response(body, { status: 500, headers });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-wjEtPz/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = worker_default;

// C:/Users/Admin/AppData/Local/npm-cache/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-wjEtPz/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  scheduledTime;
  cron;
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  WebJobCoordinator,
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=worker.js.map
