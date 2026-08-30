# Consumer Execution Lineage Audit

**Scope:** OiiOii filmmaker and EmergentSH vibe-coding/app-builder consumers  
**Audit date:** 2026-08-31  
**Canonical supply origin:** `http://127.0.0.1:8190`  
**Canonical API base:** `http://127.0.0.1:8190/v1`

## Executive verdict

There is more than one execution lineage in each consumer repository.

The intended production architecture is one authenticated execution lineage per application:

```text
OiiOii       /api/v1/films
                  -> FilmOrchestrator
                  -> ChatPoolClient / VideoRouterClient
                  -> http://127.0.0.1:8190/v1

EmergentSH   /api/pipeline/*
                  -> durable pipeline worker
                  -> AgentPipeline
                  -> AsyncOmniRouteClient
                  -> http://127.0.0.1:8190/v1
```

That is not yet the complete implementation reality.

The honest current verdict is:

- OiiOii's newer durable `/api/v1/films` lineage follows the canonical consumer contract.
- OiiOii's currently visible seven-stage frontend flow still uses older `/projects/.../pipeline/*` routes that call an in-process provider registry directly.
- OiiOii also retains direct utility routes and an old `studio_pipeline`/CLI client that bypass the canonical origin.
- EmergentSH's FastAPI pipeline can use the canonical endpoint, but `auto` mode can select direct NVIDIA NIM instead.
- EmergentSH's separate PySide desktop single-agent and multi-agent stacks directly use NVIDIA NIM and optional OpenRouter.
- Therefore neither repository currently satisfies the strict invariant that every reachable production execution lineage is authenticated and uses only `http://127.0.0.1:8190/v1`.

This document distinguishes the intended main path from the path that is actually reachable today.

## The contract every consumer execution path must obey

The supply-side consumer boundary is:

```text
Base URL: http://127.0.0.1:8190/v1
```

The `127.0.0.1` address is intentional. `localhost` must not be substituted because a system proxy intercepts loopback traffic in this environment.

### Chat

```http
POST http://127.0.0.1:8190/v1/chat/completions
Content-Type: application/json

{
  "model": "session-pool/auto",
  "messages": [
    {"role": "user", "content": "..."}
  ]
}
```

### Video

Video uses the same OpenAI-shaped completion surface:

```http
POST http://127.0.0.1:8190/v1/chat/completions
Content-Type: application/json

{
  "model": "video/auto",
  "messages": [
    {"role": "user", "content": "..."}
  ]
}
```

A provider may be pinned with `video/<host>/auto`, for example:

```text
video/labs.google/auto
```

### Discovery

```http
GET http://127.0.0.1:8190/v1/models
```

The response is the source for currently advertised routes. Inventory rows, provider names, Chrome routes, or adapter skeletons are not capacity by themselves. Capacity must be proven with live healthy provider/account evidence and, for video, completed downloadable media.

### Durable video operations

The merged shim also exposes its durable video-job surface where applicable:

```text
POST   /v1/video/jobs
GET    /v1/video/jobs/{id}
GET    /v1/video/jobs/{id}/content
GET    /v1/video/capacity
DELETE /v1/video/jobs/{id}
```

Consumers must not silently substitute the old synchronous `/v1/videos/generations` contract for the merged production path.

## OiiOii lineage map

Repository: `D:\god_ai\oioi\oioi`

### Count

There are five relevant OiiOii lineages:

1. New durable filmmaker lineage — the intended main production path.
2. Current frontend seven-stage split lineage — older and still visibly reachable.
3. Legacy unattended seven-stage lineage — one-call version of the older pipeline.
4. Legacy utility chat/image/audio/video lineage — direct in-process provider access.
5. Old `studio_pipeline` and CLI lineage — operational/legacy code with a separate old gateway client.

The first three can perform application inference or filmmaking work. The fourth provides additional user-facing inference/generation endpoints. The fifth is operationally reachable code and must not be allowed to certify production supply.

### OiiOii lineage 1 — durable filmmaker path

```text
Authenticated user
  -> /api/v1/films
  -> FilmOrchestrator
  -> film_pipeline.clients.ChatPoolClient
  -> film_pipeline.clients.VideoRouterClient
  -> http://127.0.0.1:8190/v1
```

Relevant implementation:

- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\films.py`
- `D:\god_ai\oioi\oioi\backend\film_pipeline\clients.py`

Transport behavior:

- Chat uses `POST /v1/chat/completions` with `session-pool/auto`.
- Video uses `POST /v1/chat/completions` with `video/auto` or a pinned `video/<host>/auto` route.
- Discovery uses `GET /v1/models`.
- Provider, session, and tenant provenance are retained.
- Live video requires explicit live mode and a positive clip cap.
- The client treats an unknown video submission receipt as ambiguous and does not blindly repost it.

Auth behavior:

- The parent API router applies `Depends(get_current_user)`.
- Film endpoints also take an explicit authenticated user.
- Film ownership is checked before readback and artifact access.
- The direct film admission escape hatch is owner-restricted.

Status:

```text
Auth:     aligned
Transport: aligned
Role:     intended main production lineage
```

This is the only OiiOii lineage that currently matches the target supply boundary end to end.

### OiiOii lineage 2 — current frontend seven-stage split path

```text
OiiOii frontend
  -> /api/v1/projects/{project_id}/pipeline/scriptwriter
  -> in-process agent_pipeline
  -> ProviderRegistry
  -> direct provider adapters

Then:

OiiOii frontend
  -> /api/v1/projects/{project_id}/pipeline/animate
  -> in-process agent_pipeline
  -> ProviderRegistry
  -> direct provider adapters / native video adapter
```

Relevant implementation:

- `D:\god_ai\oioi\oioi\src\app\page.tsx`
- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\pipeline.py`
- `D:\god_ai\oioi\oioi\backend\agent_pipeline.py`
- `D:\god_ai\oioi\oioi\backend\app\services\provider_service.py`

This is important because it is the path the current frontend visibly calls for the seven-stage filmmaker flow. It does not go through `ChatPoolClient` or `VideoRouterClient`. Instead, it obtains the provider registry inside OiiOii and calls provider adapters directly.

Auth behavior:

- The parent API router protects the route with `get_current_user`.
- The endpoint functions also receive an authenticated user.
- Ownership checks are present in the surrounding project flows.

Transport behavior:

- Direct provider registry access.
- Native OiiOii video adapter access where configured.
- No guarantee that requests traverse `http://127.0.0.1:8190/v1`.

Status:

```text
Auth:     mostly aligned at API boundary
Transport: not aligned
Role:     current frontend-visible path, but not approved main architecture
```

This path must be migrated to the durable `/api/v1/films` lineage or permanently retired.

### OiiOii lineage 3 — legacy unattended seven-stage path

```text
Authenticated caller
  -> /api/v1/projects/{project_id}/pipeline/run
  -> create_animation_pipeline()
  -> agent_pipeline
  -> ProviderRegistry
  -> direct provider adapters
```

This is the one-call version of the older seven-stage flow. It runs the crew in one request and can reach the direct provider registry.

Auth behavior:

- Authenticated through the parent router.
- The function also takes a user dependency.
- Some operations use `require_legacy_demo_mode()` as an additional safety brake.

Transport behavior:

- Not a `:8190` consumer path.
- Direct in-process registry and provider access remain possible.

Status:

```text
Auth:     gated
Transport: not aligned
Role:     legacy unattended alternate
```

The legacy demo gate is not a substitute for architectural removal. It reduces accidental production use but still leaves a second execution design in the repository.

### OiiOii lineage 4 — utility chat, image, audio, and direct-video routes

Relevant routes include:

```text
/api/v1/chat/completions
/api/v1/chat/stream
/api/v1/chat/send
/api/v1/images/generations
/api/v1/audio/speech
/api/v1/videos/generations
/api/v1/providers/health
/api/v1/models
```

Examples:

- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\chat.py`
- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\images.py`
- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\audio.py`
- `D:\god_ai\oioi\oioi\backend\app\api\v1\endpoints\videos.py`

These routes use the in-process `ProviderRegistry` or direct keyless logic. They do not consistently use the merged `:8190` contract.

Auth behavior:

- The parent API router applies a protected dependency to the non-auth routers.
- Some functions also explicitly take `get_current_user`.
- The video route is additionally retired with HTTP 410 outside an explicit development/demo configuration.

Transport behavior:

```text
Auth-gated does not mean contract-compliant.
```

These routes may be authenticated while still bypassing the one-and-only supply endpoint.

Status:

```text
Auth:     mostly gated
Transport: not aligned
Role:     legacy utility surface
```

The preferred action is to retire these generation routes or turn them into thin calls to the canonical consumer client. Direct upstream adapters may remain inside the supply service, but consumer application code should not call them.

### OiiOii lineage 5 — old Studio pipeline and CLI

```text
studio_pipeline.selfcheck / context / CLI
  -> studio_pipeline.omniroute.OmniRouteClient
  -> http://127.0.0.1:20128/v1
  -> legacy synchronous video candidates
```

Relevant implementation:

- `D:\god_ai\oioi\oioi\backend\studio_pipeline\omniroute.py`
- `D:\god_ai\oioi\oioi\backend\studio_pipeline\selfcheck.py`
- `D:\god_ai\oioi\oioi\backend\film_pipeline\cli.py`

The old Studio client:

- Defaults to `http://127.0.0.1:20128/v1`.
- Probes `/videos/generations`, `/video/generations`, `/videos`, and related legacy paths.
- Expects an inline media URL rather than the merged durable video contract.

This is not the intended main product lineage, but it remains executable operational code. It must not be used for final production certification because it can produce a result unrelated to the actual consumer endpoint.

Status:

```text
Auth:     not covered by the customer API dependency chain
Transport: not aligned
Role:     operational/legacy
```

### OiiOii authentication exceptions

The following are expected exceptions to “every execution route requires an existing user token”:

- Login and bootstrap endpoints must be reachable before a user has a token.
- Root and health endpoints may be public operational endpoints.

These exceptions must not be confused with billable generation routes.

The static `/media` mount is outside the normal API dependency chain and should be reviewed separately. If it can expose generated customer artifacts without ownership checks, it is an access-control bypass even though it is not itself a model-execution lineage.

## EmergentSH lineage map

Repository: `D:\god_ai\emergentsh-standalone-clean`

### Count

There are three relevant EmergentSH execution stacks:

1. FastAPI SaaS durable pipeline — intended main web/backend lineage, but currently conditional.
2. PySide desktop single-agent lineage — direct provider bypass.
3. PySide desktop multi-agent lineage — separate direct provider bypass.

The CRUD and conversation persistence routes are authenticated application-data paths but do not themselves invoke inference. They are not counted as independent model-execution lineages here.

### EmergentSH lineage 1 — FastAPI SaaS pipeline

```text
Authenticated user
  -> POST /api/pipeline/run
  -> durable PipelineJob
  -> background pipeline worker
  -> backend.agent_pipeline.AgentPipeline
  -> AsyncOmniRouteClient, if explicitly selected
  -> http://127.0.0.1:8190/v1
```

Relevant implementation:

- `D:\god_ai\emergentsh-standalone-clean\backend\app\api\pipeline.py`
- `D:\god_ai\emergentsh-standalone-clean\backend\app\services\nim_client.py`
- `D:\god_ai\emergentsh-standalone-clean\backend\agent_pipeline.py`

Auth behavior:

- Pipeline submission uses `get_current_active_user`.
- Job streaming, status, export, preview, and credit operations use the active-user dependency and ownership checks.
- Durable jobs are associated with the submitting user.

Transport behavior:

The OmniRoute client itself is configured correctly:

```text
Default OmniRoute URL: http://127.0.0.1:8190/v1
Default route:         chat/session-pool/auto
Chat path:             /v1/chat/completions
Model discovery:       /v1/models
```

However, provider selection is not strict enough for the single-endpoint deployment:

- `INFERENCE_PROVIDER=omniroute` selects the canonical client.
- `INFERENCE_PROVIDER=auto` selects OmniRoute only when `OMNIROUTE_BASE_URL` is explicitly present.
- Otherwise `auto` selects direct NVIDIA NIM.
- Non-strict execution can fall back to an in-process mock when credentials are missing.
- `use_mock` is accepted by the pipeline request model.

Therefore the FastAPI lineage is only compliant under a production configuration that explicitly forces OmniRoute and disallows mock/direct-NIM downgrade.

Required production posture:

```text
INFERENCE_PROVIDER=omniroute
OMNIROUTE_BASE_URL=http://127.0.0.1:8190/v1
INFERENCE_STRICT_MODE=true
```

In addition, production should reject `use_mock=true` for customer execution rather than silently accepting it.

Status:

```text
Auth:     aligned for FastAPI routes
Transport: conditionally aligned
Role:     intended main web/SaaS lineage
```

### EmergentSH lineage 2 — desktop single-agent flow

```text
PySide desktop UI
  -> AgentWorker
  -> NIMAgentCore
  -> ProviderPool
  -> direct NVIDIA NIM
```

Relevant implementation:

- `D:\god_ai\emergentsh-standalone-clean\src\ui\main_window.py`
- `D:\god_ai\emergentsh-standalone-clean\src\workers\agent_worker.py`
- `D:\god_ai\emergentsh-standalone-clean\src\core\agent_core.py`
- `D:\god_ai\emergentsh-standalone-clean\src\core\providers.py`

The provider pool directly defines:

```text
https://integrate.api.nvidia.com/v1
https://openrouter.ai/api/v1
```

Auth behavior:

- This worker does not inherit the FastAPI `get_current_active_user` dependency.
- Its local profile/provider credentials are a separate configuration path.

Status:

```text
Auth:     not covered by FastAPI customer auth
Transport: not aligned
Role:     legacy desktop single-agent path
```

If this desktop path ships or remains reachable to customers, it must either be retired, protected by an application entitlement/session gate, and routed through `:8190`, or explicitly removed from the production product.

### EmergentSH lineage 3 — desktop multi-agent orchestration flow

```text
PySide desktop UI
  -> OrchestratorWorker
  -> multiple AgentWorker instances
  -> NIMAgentCore
  -> ProviderPool
  -> direct NVIDIA NIM / optional OpenRouter
```

Relevant implementation:

- `D:\god_ai\emergentsh-standalone-clean\src\ui\main_window.py`
- `D:\god_ai\emergentsh-standalone-clean\src\workers\orchestrator_worker.py`
- `D:\god_ai\emergentsh-standalone-clean\src\workers\agent_worker.py`
- `D:\god_ai\emergentsh-standalone-clean\src\core\providers.py`

This is a separate stack from the FastAPI `AgentPipeline`, even though both use agent terminology. It creates agent workers through the desktop orchestration layer and uses the direct provider pool.

Status:

```text
Auth:     not covered by FastAPI customer auth
Transport: not aligned
Role:     legacy desktop multi-agent path
```

## Cross-application status matrix

| Application | Lineage | Auth gate | Canonical `:8190/v1` only | Production role |
|---|---|---:|---:|---|
| OiiOii | Durable `/api/v1/films` | Yes | Yes | Approved target main path |
| OiiOii | Frontend `/projects/.../pipeline/*` | Yes at API layer | No | Current visible legacy path |
| OiiOii | Utility chat/image/audio/video | Mostly yes | No | Legacy utility surface |
| OiiOii | Studio pipeline/CLI | No customer API gate | No | Operational/legacy |
| EmergentSH | FastAPI `/api/pipeline/*` | Yes | Only when forced by config | Approved target main path |
| EmergentSH | Desktop single-agent | No FastAPI gate | No | Legacy desktop path |
| EmergentSH | Desktop multi-agent | No FastAPI gate | No | Legacy desktop path |

## What “auth-gated” means here

There are two separate controls:

### Consumer-user authorization

The application must authenticate the customer before allowing a billable or state-changing execution. This includes:

- Film creation and scheduling.
- Seven-stage pipeline execution.
- App-builder pipeline submission.
- Job status and artifact access.
- Video generation requests.

### Supply transport boundary

After the consumer authorizes the operation, the consumer must send model work only to:

```text
http://127.0.0.1:8190/v1
```

The consumer should not know or call:

- `:20128`
- `:20130`
- direct NVIDIA NIM URLs
- direct OpenRouter URLs
- provider-specific browser/session transports
- the old synchronous video routes

An authenticated route that directly calls a provider adapter is still a contract violation. Authentication and endpoint unification are independent gates.

## Required target architecture

### OiiOii target

```text
Frontend filmmaker action
  -> authenticated /api/v1/films or its authenticated durable film subroutes
  -> FilmOrchestrator
  -> ChatPoolClient / VideoRouterClient
  -> http://127.0.0.1:8190/v1
```

Required changes before final certification:

1. Move the frontend's seven-stage execution from `/projects/.../pipeline/*` to the durable `/films` lineage, or make the old routes thin authenticated wrappers around the same durable implementation.
2. Prevent `pipeline.py` from calling the in-process provider registry for customer execution.
3. Retire or convert `/api/v1/chat/*`, `/images/generations`, `/audio/speech`, and `/videos/generations` where they represent model execution.
4. Remove or permanently quarantine the old `studio_pipeline` client from production certification.
5. Preserve authentication and per-user/per-film ownership checks.
6. Ensure generated artifact access cannot bypass ownership through the static `/media` mount.

### EmergentSH target

```text
Authenticated web or approved desktop action
  -> one durable app-builder pipeline
  -> one shared OmniRoute client
  -> http://127.0.0.1:8190/v1
```

Required changes before final certification:

1. Force `INFERENCE_PROVIDER=omniroute` in production.
2. Force `OMNIROUTE_BASE_URL=http://127.0.0.1:8190/v1`.
3. Make production startup or first execution fail closed if direct NIM/OpenRouter configuration is selected.
4. Make production execution reject `use_mock=true` and disallow silent mock fallback.
5. Retire the direct `src/core/providers.py` desktop pool or refactor it to use the shared `:8190` client.
6. Apply application-session/entitlement authorization to any desktop worker path that remains shipped.
7. Keep conversation CRUD separate from inference; when a message requires generation, it must enter the one approved pipeline.

## Certification tests required

### Static/contract tests

For every reachable consumer execution entrypoint:

- Unauthenticated request is rejected.
- Authenticated request reaches only the consumer application endpoint.
- Downstream request target is `http://127.0.0.1:8190/v1`.
- No request target contains `:20128`, `:20130`, direct NIM, or direct OpenRouter.
- Chat model is `session-pool/auto` or an approved route alias.
- Video model is `video/auto` or an explicitly pinned `video/<host>/auto`.
- Provider/session/tenant provenance is retained where returned.
- Video submission timeout is treated as ambiguous and is not blindly reposted.
- Mock mode is impossible in production configuration.

### Live smoke gates

Before a full consumer E2E:

1. `GET /v1/models` through `127.0.0.1:8190` succeeds within the accepted timeout.
2. One valid `session-pool/auto` chat completion succeeds.
3. One bounded `video/auto` or pinned video submission produces an honest receipt.
4. The response identifies provider and session where available.
5. The durable job state is queryable and terminal.
6. At least one video path produces downloadable, container-verified media before video capacity is advertised as graduated.

### Consumer E2E gates

After GLM completes Profile 2-4 expansion and both OmniRoute-native and seat-pool video workstreams:

- OiiOii: execute one bounded seven-stage film run through the approved durable filmmaker lineage.
- EmergentSH: execute one complete app-builder pipeline through its approved durable FastAPI lineage.
- Run both consumers concurrently only after individual runs pass.
- Verify retry, fallback, idempotency, artifact persistence, and ownership isolation.
- Count only live healthy models and result-verified video capacity.
- Report OmniRoute capacity, seat-pool capacity, and the deduplicated combined total separately.

## Evidence gathered for this audit

Focused hermetic tests were run without live provider generation:

```text
OiiOii:
pytest -q backend\\tests\\test_film_pipeline.py -k "consumer_v1_contract or consumer_video_timeout"
2 passed, 26 deselected

EmergentSH:
pytest -q backend\\tests\\test_nim_client.py
16 passed
```

These tests establish useful adapter and contract behavior but do not prove current live gateway health or graduated video capacity.

The preceding supply-side audit also recorded:

- A live `GET /v1/models` timeout through `:8190`.
- Zero new result-verified video rows from the latest GLM adapter sweep.
- Profile 2-4 expansion evidence still outstanding at the time of the audit.

Those are rollout gates, not consumer-code failures.

## Final answer in one sentence

Use OiiOii's durable `/api/v1/films` lineage and EmergentSH's forced-OmniRoute FastAPI `/api/pipeline/*` lineage as the only production paths; retire or refactor every other reachable inference stack so it is authenticated and sends exclusively through `http://127.0.0.1:8190/v1`.
