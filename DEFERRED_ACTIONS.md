# Deferred Actions — OmniRoute Monetizer

This file records actions that cannot be safely completed while preserving the live OmniRoute v3.8.49 service on port 20128. It complements the incremental history in `MASTER_WORKLOG.md`; worklog entries are the authoritative session record.

## 1. Catalog/runtime upgrade or restart — deferred

The live service intermittently stalls on `GET /v1/models` after provider health/refresh activity. Local evidence is recorded in worklog entries #129, #140, and #146. Upstream OmniRoute issue #6408 describes the same `/v1/models` request serialization/lock contention class and points to provider-registry rebuild, single-flight locking, or SQLite WAL reads as possible causes.

Do not restart, kill, rebind, reinstall, remove a lock, checkpoint, or replace the live service in this mission. A future maintenance window must:

1. Reproduce the stall in a fresh sandbox on a separate port/data directory.
2. Replay provider state incrementally.
3. Verify the candidate OmniRoute release and its published fix status.
4. Take a complete production backup.
5. Apply the upgrade/restart only with a tested restore path.

## 2. xAI OAuth re-authentication — blocked pending fresh account authorization

Native refresh was attempted for all four connections in worklog #150. Two rows require re-authentication because their refresh tokens are expired; two returned an upstream 402 after refresh. A fresh xAI OAuth login/import is required. No placeholder OAuth data may be injected.

## 3. Web-cookie providers — blocked pending authenticated browser/API-key surface

The allowed browser recon found Claude at its login page; browser-safety restrictions prohibit inspecting cookie/session stores. Existing known blockers remain as recorded in worklog entries #122–#124: WeChat QR, Meta credentials, Zed native OAuth import, and Grok TLS fingerprint mismatch. Do not retry those gates blindly.

## 4. Local runtimes — deferred pending explicit installation decision

Ollama, LM Studio, llama.cpp, vLLM, Xinference, ComfyUI, Lemonade, and related local runtimes are absent. Installing software changes the machine and may require a user decision about disk, model downloads, GPU/CPU use, and licenses; no installation was performed.

