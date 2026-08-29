# :8190 Session-Pool Shim — handover report

**Date:** 2026-08-29 · **Scope:** the consumer endpoint at `http://127.0.0.1:8190/v1` and the
`graduate_all_seats.py` orchestrator. Written for the next agent, not for the operator.

---

## 1. Read this first

Every defect below is one instance of the project's signature bug: **a verdict trusted for a layer it
never measured.** Before this session, `:8190` looked healthy by every measurement anyone had taken —
`GET /v1/models` returned 200 and listed 20 routes, `live()` reported 18 dispatchable seats, and POSTs
returned HTTP 200 with `finish_reason: "stop"`. All three were true. None of them measured whether the
bytes in the response body were an answer.

**The single most important thing to internalise: the old 200s were not successes.** One seat was
returning the constant string `"Omni."` to every prompt, one was returning its 226 KB HTML landing
page, one was returning raw unassembled SSE frames, and one was returning a rate-limit wall — all as
`content`, all with `finish_reason: "stop"`. If you compare "success rate before" against "success
rate after" you will conclude this session made things worse. It did not; it stopped counting garbage.
Measure the *body*, not the status.

---

## 2. What was broken, what was done, and how each was verified

| # | Defect | Fix | Verified by |
|---|---|---|---|
| 1 | **Every POST returned HTTP 500** while the pool was healthy. A `TypeError` inside an adapter is neither `SessionExpired` nor `ChatError`, so it escaped `session_pool.chat()`'s failover loop and aborted the whole request — one broken adapter took down all 18 seats. | Generic `except Exception` in the failover loop; the seat is cooled and the walk continues. Traceback to stderr, since the caller only ever sees `str(e)` and a bug with no file/line is unfindable. | 500 → 200 on every route |
| 2 | **Garbage shipped as answers.** HTML page shells and raw SSE frames delivered as `content`. | `unusable_reply()` in `session_pool.py` — START-anchored and length-bounded on purpose, so a real answer that merely *mentions* HTML is never discarded. | `[pool] veoaifree.com returned page markup … failing over` |
| 3 | **A wall shipped as an answer.** `veoaifree.com` returned `Limit Reached: … maximum allowance of 2 videos` at `finish_reason: stop`. | `wall_in_reply()` + failover on a 3600 s cooldown. A wall is never retried. | observed and failed over |
| 4 | **Tool calls were impossible on `:8190`.** No tool contract was ever attached. | Imported (not copied) `tool_instruction` / `parse_tool_call` / `looks_like_overflow` from `chat_pool_server.py`, so `:20130` and `:8190` share one shim. Added OpenAI↔Anthropic normalisation, tool-history flattening, `tool_calls` emission, `x_pool_tools_rendered`. | `finish_reason: "tool_calls"`, `Bash{"command":"ls -la"}`, `44/44` tools, from `chat.deepseek.com` in 21 s |
| 5 | **Unbounded tool failover.** Forcing `strict_json` with tools made the pool walk all 18 seats at a real round trip each, blowing a 300 s client timeout. | `TOOL_FAILOVER_TRIES = 6`. | request completed in 21 s |
| 6 | **Broken adapters re-entered rotation every 30 s.** An `UNUSABLE_REPLY` is *our* code defect, not a provider blip — it will fail identically forever — but it was cooled like a transport error, so two broken seats burned 2 of every 6 tool tries. | `BROKEN_ADAPTER_COOLDOWN_S = 1800`, applied to `UNUSABLE_REPLY` and `ADAPTER_ERROR`. | each broken host now logged **once** per run instead of on every request |
| 7 | **Walls arriving as HTTP status codes were treated as transient.** A 402 seat consumed an attempt on every request until all 6 were gone and the call 500'd with a healthy pool behind it. | `wall_in_error()` → the 3600 s wall cooldown. Status codes matched only in `HTTP <code>` position, never as bare digits, so `"6403 bytes"` cannot quarantine a working seat. | `[pool] chat-api-v3.innerai.com is walled (HTTP 402) -- standing it down`; unit-checked against `HTTP 500` and `6403 bytes` → `None` |
| 8 | **The protocol envelope shipped as content.** A seat that correctly declined a tool returned `{"tool": null, "text": "I cannot execute shell commands…"}` and the consumer received that **JSON** as the assistant's message. `parse_tool_call` reports "no tool call" but discards the text. | `_unwrap_no_tool_text()` in the shim, gated on `tools` being present and strict about shape. | `'{"tool": null, "text": "…"}'` → `'…'`; a genuine JSON answer containing a `tool` key → untouched |
| 9 | **A proven-broken adapter had no off switch.** `api.monica.im` returns `"Omni."` to every prompt and is LRU-favoured, so it answered the *common* path first. | `state/pool_quarantine.json` + `OMNI_POOL_QUARANTINE` env var, filtered in `live()`. | 3 hosts withheld, 14 seats remain dispatchable |
| 10 | **Unbounded plain-chat failover.** Once the fast-but-garbage seat was quarantined, plain chat walked the slow Chrome-bound tail with no ceiling: >90 s with no answer. | `CHAT_FAILOVER_TRIES = 5`. | 90 s hang → 3.3 s bounded error |

**Why `pool_quarantine.json` is not `flagged_dead`:** `status.alive = False` means the *cookie* died and
is owned by keepalive. These accounts are alive and logged in — *our client* for them is broken. Putting
an adapter defect in `flagged_dead` would make a live account read as a dead one and set keepalive
fighting the entry. Two layers, two files. Releasing a host needs no code change: delete the entry and
restart the face.

---

## 3. Current honest state of `:8190`

**Working:** tool calling end-to-end (`finish_reason: "tool_calls"`, 44/44 tools rendered, correct
case-insensitive name resolution `bash_tool` → `Bash`); garbage and walls fail over instead of reaching
consumers; failures are bounded and name their cause; adapter bugs produce a traceback and an
`internal_adapter_error` that says *this is our bug, not the provider's*.

**Not working — the open regression, stated plainly:** with garbage excluded, **real serving capacity is
thin**. The final run had plain chat exhaust all 5 tries in 3.3 s and a tools request exceed 170 s. Of
20 advertised routes, the ones observed actually answering correctly this session are
`chat.deepseek.com` (21 s, tool call) and `chat.mistral.ai` (15 s, contract-compliant refusal).

**Do not "fix" this by raising the try ceilings.** That trades a fast honest error for a slow one; at
6 tries the tools path already exceeded 170 s. The ordering is the defect: `pick()` sorts
stateless-first then LRU, which has no memory of *which seats have ever actually answered*. The right
next change is **success-weighted ordering** — prefer seats with a recent verified success, so the two
known-good seats are reached first instead of by chance. That is the highest-value remaining work on
this endpoint.

**Known, deliberately not fixed:**
- `chat_pool_server.py:1046` (`:20130`, the Anthropic face) has **defect #8 verbatim** — it ships the
  raw envelope as `{"type":"text","text":text}`. The helper exists and the fix is one line. It was left
  alone because `:20130` is a 60/60-verified production path and changing it was outside this mandate.
  Gate any fix on `tools` being present and it cannot disturb the strict-JSON planner path.
- `session_pool_shim.py` can raise `ConnectionAbortedError` writing an error to a client that already
  gave up. Noisy, not fatal.
- The three quarantined adapters are withheld, **not repaired**. They still count toward the advertised
  20 routes. `GET /v1/models` lists 20; the operator's spec says 50. The spec is wrong.

---

## 4. `graduate_all_seats.py` — the orchestrator

Wraps existing tools by subprocess. It **never opens CDP, never types, never submits** — that is what
preserves `chrome_live_guard`'s refusal to touch the operator's live Chrome (which once permanently
revoked their Google session) and `tab_graduation_sweep.py`'s serial one-seat-at-a-time discipline.

Two defects found and fixed this session:

1. **The gate-truncation hazard.** `replay_check.py --only <host>` filters the session list and then
   writes the report **atomically over `state/replay_check.json`** — the gate `chat_pool_server.py`
   reads at startup to decide which seats to serve. `tab_graduation_sweep.py --execute` called it with
   **no `--out`**, so verifying one seat truncated the gate to a single row and the next restart would
   silently drop the pool from 7 seats to 1. Fixed: `execute_one` now writes to `scratch_report(site)`
   under `state/scratch/` and prints where the verdict landed. The canonical gate is written only by a
   full run, in step 3.
2. **A redundant second live request.** `execute_one` already captures *and* replays. The orchestrator
   then ran its own replay — double-spending someone else's free account to learn a fact it already
   had. Fixed: step 2 sends nothing; it reads the sweep's scratch report. The path is **imported** from
   the sweep, not recomputed, so writer and reader cannot drift and graduate a seat on a stale report.

Also hardened: a stale scratch report is deleted before each unit, so a unit that dies before writing
can't be misread as last week's pass; and if the host string doesn't match, a report already filtered
to one row by `--only` matches that row (`www.` alone was enough to break the substring test and
discard a genuine pass).

Standing rules it enforces: walls recorded once and never re-knocked (`--retry-walls` to override);
`MAX_ATTEMPTS = 2`, because a third identical attempt has never changed the answer in this project's
history and ~40 identical retries once burned a day of budget; video seats listed and **skipped** — a
video capture spends clips and a video seat must never enter the chat pool.

**It compiles and its helpers are unit-tested. It has never been run.** Running it drives Chrome, which
the operator's standing constraint reserves to them.

---

## 5. Traps that cost real time — don't re-learn these

- **Grep output mangles forward slashes here.** It rendered `/v1/models` as `\v1\models` and
  `secrets / "session_*.json"` as `secrets \ "…"`. I reported the first as a live defect; it was not.
  **Read is authoritative — never file a bug from Grep rendering alone.**
- **`start "" /b` from a `.bat` dies when the invoking `cmd` exits.** The shim's task bat looks correct
  and works under Task Scheduler, but launching it from a shell tool leaves no listener and connection
  refused. Use PowerShell `Start-Process -WindowStyle Hidden` with `-RedirectStandardOutput` /
  `-RedirectStandardError`. Same lesson as the Chrome work.
- **Always redirect stdout/stderr on relaunch.** Otherwise you are reading yesterday's log and
  diagnosing a fixed bug. Every `[pool]` decision line in this report came from `logs/shim_run.err`.
- **`OMNI_VIDEO_CONFIRM_SPEND=1` must be set on launch** — it is the operator's existing spend consent,
  set by the task bat. A manual relaunch without it silently refuses video work.

## 6. Standing constraints (do not violate)

- **Never restart, stop, or kill `:20128`** — that is OmniRoute's, not ours. `:20130` and `:8189` are ours.
- **Codex owns all of `D:\god_ai\oioi`.** Directive/spec docs may be written there; never touch oioi code.
- **Do not harvest.** Never start a competing harvest, never drive Chrome, never run
  `capture_video_job_cdp.py` unless asked.
- **A capture is real only if** a RESULT exchange was observed **and** a screenshot confirms the
  sentinel landed in a VIDEO composer.
- The `:20130` strict-JSON planner blocker is **fixed and verified 60/60** (`6505a07`). Do not
  re-investigate it.
- Never junction or drive the operator's live Chrome profile.
