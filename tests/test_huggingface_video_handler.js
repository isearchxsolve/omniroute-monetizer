/*
 * Offline contract test for the compiled Hugging Face video helper.
 *
 * The runtime bundle is the artifact loaded by the registered Node service,
 * so this test extracts only the newly-added top-level helper and supplies a
 * deterministic fetch harness. No network request, credential read, or
 * provider generation occurs.
 */

const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const bundlePath = "state/omniroute-3.8.50-sandbox/node_modules/omniroute/dist/.build/next/server/chunks/_0zgjgqu._.js";
const bundle = fs.readFileSync(bundlePath, "utf8");
const start = bundle.indexOf("const __omniHfRoutes = {");
const end = bundle.indexOf("async function N({model:e,body:t,credentials:r,log:a})", start);
assert(start >= 0 && end > start, "compiled Hugging Face helper boundaries not found");
const helperSource = bundle.slice(start, end);

function fakeResponse(status, body, binary = false) {
  const bytes = binary ? Buffer.from(body) : Buffer.from(typeof body === "string" ? body : JSON.stringify(body));
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => bytes.toString("utf8"),
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  };
}

function makeHarness(mediaBytes, submitResponse = null) {
  const calls = [];
  let statusCalls = 0;
  const context = {
    URL,
    URLSearchParams,
    Uint8Array,
    TextDecoder,
    Buffer,
    AbortController,
    setTimeout,
    clearTimeout,
    Date,
    JSON,
    Object,
    Math,
    encodeURIComponent,
    Promise,
    console,
    o: { saveCallLog: () => Promise.resolve() },
    s: { sanitizeErrorMessage: (value) => String(value) },
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), options });
      if (submitResponse) return submitResponse;
      if (String(url).includes("/requests/job-1/status")) {
        statusCalls += 1;
        return fakeResponse(200, { status: statusCalls === 1 ? "IN_PROGRESS" : "COMPLETED" });
      }
      if (String(url).includes("/requests/job-1") && options.method === "GET") {
        return fakeResponse(200, { video: { url: "https://cdn.example/video.mp4" } });
      }
      if (String(url) === "https://cdn.example/video.mp4") return fakeResponse(200, mediaBytes, true);
      return fakeResponse(200, {
        request_id: "job-1",
        response_url: "https://router.huggingface.co/fal-ai/fal-ai/hunyuan-video/requests/job-1?_subdomain=queue",
      });
    },
  };
  vm.runInNewContext(`${helperSource}\nthis.__handler = __omniHuggingFaceVideo;`, context);
  return { handler: context.__handler, calls };
}

async function main() {
  const mp4 = Buffer.from([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d]);
  const success = makeHarness(mp4);
  const result = await success.handler({
    model: "tencent/HunyuanVideo",
    provider: "huggingface",
    providerConfig: { baseUrl: "https://router.huggingface.co" },
    credentials: { apiKey: "hf_test" },
    body: {
      prompt: "a cat crossing a bridge",
      negative_prompt: "blur",
      guidance_scale: 7,
      num_frames: 24,
      num_inference_steps: 18.9,
      seed: 42,
      timeout_ms: 1000,
      poll_interval_ms: 0,
      extra_body: { width: 512, model: "must-not-override-route" },
    },
    log: { info() {}, error() {} },
  });
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.data.data[0].format, "mp4");
  assert.strictEqual(Buffer.from(result.data.data[0].b64_json, "base64")[4].toString(16), "66");
  assert.strictEqual(success.calls[0].url, "https://router.huggingface.co/fal-ai/fal-ai/hunyuan-video?_subdomain=queue");
  assert.strictEqual(success.calls[0].options.method, "POST");
  assert.strictEqual(success.calls[0].options.headers.Authorization, "Bearer hf_test");
  const payload = JSON.parse(success.calls[0].options.body);
  assert.deepStrictEqual(payload.negative_prompt, ["blur"]);
  assert.strictEqual(payload.num_inference_steps, 18);
  assert.strictEqual(payload.width, 512);
  assert.strictEqual(payload.model, undefined);
  const mediaCall = success.calls.find((call) => call.url === "https://cdn.example/video.mp4");
  assert(mediaCall, "signed media URL was not fetched");
  assert.strictEqual(mediaCall.options.headers.Authorization, undefined);

  const nonMp4 = makeHarness(Buffer.from("not-an-mp4"));
  const rejected = await nonMp4.handler({
    model: "tencent/HunyuanVideo",
    provider: "huggingface",
    providerConfig: { baseUrl: "https://router.huggingface.co" },
    credentials: { apiKey: "hf_test" },
    body: { prompt: "test", timeout_ms: 1000, poll_interval_ms: 0 },
    log: { info() {}, error() {} },
  });
  assert.strictEqual(rejected.success, false);
  assert.strictEqual(rejected.status, 502);
  assert.strictEqual(rejected.error.error.code, "VIDEO_ARTIFACT_UNAVAILABLE");

  const noToken = makeHarness(mp4);
  const authFailure = await noToken.handler({
    model: "tencent/HunyuanVideo",
    provider: "huggingface",
    providerConfig: { baseUrl: "https://router.huggingface.co" },
    credentials: {},
    body: { prompt: "test" },
    log: { info() {}, error() {} },
  });
  assert.strictEqual(authFailure.success, false);
  assert.strictEqual(authFailure.status, 401);
  assert.strictEqual(noToken.calls.length, 0);

  const upstreamFailure = makeHarness(mp4, fakeResponse(401, { error: "unauthorized" }));
  const failed = await upstreamFailure.handler({
    model: "tencent/HunyuanVideo",
    provider: "huggingface",
    providerConfig: { baseUrl: "https://router.huggingface.co" },
    credentials: { apiKey: "hf_test" },
    body: { prompt: "test", timeout_ms: 1000 },
    log: { info() {}, error() {} },
  });
  assert.strictEqual(failed.success, false);
  assert.strictEqual(failed.status, 401);

  console.log("Hugging Face compiled helper mocked submit/poll/MP4/auth tests: PASS");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
