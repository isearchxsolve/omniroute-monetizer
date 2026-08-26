# PENDING — how to finish without paying an agent to re-derive it

Written 2026-08-27. Everything marked **[VERIFIED]** was measured, with the timestamp. Everything
marked **[OPEN]** is not known and says how to settle it.

**Read this first: the scripts in this repo are free to run. The agent is what costs money.**
`preflight_planner.py`, `probe_tool_fidelity.py` and the `curl` checks below run against harvested
free supply and your local services. Running them yourself costs nothing. Asking an Opus agent to
run them costs full context per call. Run them yourself; bring an agent in only for a decision.

---

## 1. Status snapshot

| thing | state | how it was checked |
|---|---|---|
| Video supply | **[VERIFIED]** 16 clips across 4 rtst.ai seats, no cooldowns | `curl -s -m 25 http://127.0.0.1:8189/v1/video/capacity` |
| `:8189` video face | **[VERIFIED]** up, `{"status":"ok","face":"video-jobs","engine":"pool"}` | `curl -s -m 10 http://127.0.0.1:8189/health` |
| `:20130` planner | **[VERIFIED]** 6/6 strict-JSON scenes, slowest 11.5s, exit 0 | `python scripts/automation/preflight_planner.py --scenes 6` |
| Chat pool seats | **[VERIFIED]** 5 served: cohere, huggingface, perplexity, you, aymo (aymo cooling) | `logs/chat_pool.log` |
| Tool-safe funded route | **[OPEN]** — the blocker. See §2. | — |

`:8189` capacity takes **>8s on a cold call**. An 8s timeout makes a healthy port look dead. Use `-m 25`.

---

## 2. THE BLOCKER — no confirmed funded tool-capable route

This is the only thing actually stopping work, and no config edit fixes it.

What went wrong on 2026-08-26/27: Claude Code was pointed at `:20130` with 18 models and
`isFamilyDefault: false` on **every one**, so the served route was undefined. 7 of the 12 non-pool
routes are dead, and `:20130` falls back to a `pool/*` seat when upstream refuses. Pool seats are
browser replays of consumer chat UIs — text in, text out, **no `tool_use` block possible**. So the
tools array never reached a tool-capable model; the model still read in its system prompt that it had
tools, invented them from habit (`bash`, `read` — lowercase), and the case-sensitive dispatcher
rejected all ~40. Chat looked perfect throughout, which is why nothing alarmed.

**What is measured, and what is NOT:**

`state/tool_fidelity.json` and my re-probe answer exactly one question — *given a tool named `Bash`,
does the route return `Bash` byte-for-byte?* Five routes pass at 44 tools / 61KB **[VERIFIED
2026-08-27]**: `agy/claude-sonnet-4-6` 5.7s, `antigravity/claude-opus-4-6-thinking` 4.7s,
`antigravity/claude-sonnet-4-6` 5.6s, `agy/claude-opus-4-6-thinking` 7.8s,
`agentrouter/claude-opus-5` 4.2s.

**That is tool fidelity, not credit headroom, and the two are independent.** Those probes were
256-token `echo hi` calls; they fit in whatever credit was left. You have since reported
`agentrouter` and `agy` both dry. So a `tools_ok` verdict does **not** mean usable. Do not pick a
default off that table alone — that conflation is what wasted the last session.

### [OPEN] To settle it, cheapest first

1. **Check the provider dashboards directly.** Free, authoritative, no tokens. Per
   `memory/dont-declare-keys-dead-from-gateway-errors.md`: never judge a key from a gateway error —
   decrypt and curl the provider itself.
2. **`:20128` exposes no credit view** — **[VERIFIED]** `/v1/credits`, `/v1/providers`, `/v1/status`,
   `/v1/credentials` all 404; `/admin/providers` and `/health` return the Next.js HTML shell. So there
   is no cheap programmatic headroom check. Don't go looking again.
3. **A real-size smoke test is the only honest proxy.** A 256-token probe passing proves nothing about
   a session. Send one full-size request and watch for a wall.
4. **If nothing is funded: use first-party Anthropic and stop fighting the free path.** A mangling or
   dry route still bills you a full context per failed call, so a broken free route costs *more* than
   a paid working one. This is the recommendation.

---

## 3. Remaining work, in order

### Step A — pick a route, then apply the config (only if going via `:20130`)

The fixed config is `scripts/automation/98e83bfd-e627-4557-a52e-9dcc8a008f50.json` (5 entries, one
pinned default, no dead routes, no `pool/*`, labels state the measured layer). Before copying it live,
**change `isFamilyDefault: true` to whichever route you confirmed funded in §2** — as shipped it
points at `agy/claude-sonnet-4-6`, which you report is dry.

Back up first — the live file holds the only copy of your agentrouter key:

```bash
cp "C:/Users/Admin/AppData/Local/Claude-3p/configLibrary/98e83bfd-e627-4557-a52e-9dcc8a008f50.json" "C:/Users/Admin/AppData/Local/Claude-3p/configLibrary/98e83bfd.agentrouter.bak.json"
```

Then apply:

```bash
cp "D:/omniroute-monetizer/scripts/automation/98e83bfd-e627-4557-a52e-9dcc8a008f50.json" "C:/Users/Admin/AppData/Local/Claude-3p/configLibrary/98e83bfd-e627-4557-a52e-9dcc8a008f50.json"
```

`_meta.json` already has `appliedId` set to this UUID, so no other edit is needed. Restart the client.

**Confirm it took** — if tool calls work, the fix is live. If you still see
`No such tool available: read`, the route is dropping the tools array: switch to the next
`tools_ok` route rather than re-investigating.

### Step B — video supply (the real bottleneck)

16 clips exist. A 3-hour film needs ~2,160 (`memory/three-hour-film-clip-arithmetic.md`), so ~540 free
accounts per film at 4 clips each. The Gemini 3.6 harvest agent runs against `MASTER_PROMPT.md` and
needs nothing from you. Watch progress:

```bash
curl -s -m 25 http://127.0.0.1:8189/v1/video/capacity
```

**A capture is real only if a RESULT exchange was observed and a screenshot confirms the sentinel
landed in a VIDEO composer.** giz.ai once reported CAPTURED with every signal green while the text
sat in a chat assistant. `totalClipsAvailable` going up is the only claim that counts; a ledger entry
saying CAPTURED is not.

### Step C — the film run

Codex has its go-signal in `oioi/ROUTER_DIRECTIVE_PLANNER_FIXED.md` and can run in parallel with the
harvest. The `:20130` strict-JSON planner blocker is fixed and verified 60/60 (commit `6505a07`) —
**do not re-investigate it.** Before launching:

```bash
python scripts/automation/preflight_planner.py --scenes 6
```

Exit 0 means the planner path won't die on supply. This runs on free pool supply — costs nothing.

### Step D — commit when satisfied

Nothing is committed. Two modified, two new:

```bash
cd D:/omniroute-monetizer && git status --short
```

To discard the config work entirely:

```bash
cd D:/omniroute-monetizer && git checkout -- scripts/automation/98e83bfd-e627-4557-a52e-9dcc8a008f50.json scripts/automation/sync_confirmed_models_to_clients.py
```

---

## 4. Traps — each of these has already cost a session

- **Do not run `sync_confirmed_models_to_clients.py` while Codex is mid-film.** It rewrites
  `codex omni.yml` and `~/.zcode/v2/config.json`, and replaces the curated 5-entry list with
  5 tool-safe + 149 `UNVETTED`. It is fixed but it is still a wholesale regenerator.
- **Never leave `isFamilyDefault` unset on every entry.** That is the original defect: undefined route
  → dead route → silent pool fallback → every tool call fails while chat looks fine.
- **`pool/*` IS tool-capable and belongs in every client — do not remove it.** As of 2026-08-27 the
  shim in `chat_pool_server.py` renders the tools array into the prompt, asks for the call back as
  JSON, and resolves the returned name case/separator-insensitively against the request's own tools
  array, so it emits the exact registered name. **[VERIFIED]** a Cohere seat returned
  `tool_use`/`Bash`/`{"command":"ls -la"}` with `stop_reason: tool_use`, and
  `preflight_planner.py --scenes 6` still exits 0. Earlier drafts of this file said the opposite; that
  was the mistake — it read one missing translation layer as a missing capability and wrote the whole
  harvest off in favour of paid routes.
- **Never restart, stop or kill `:20128`.** Not ours. `:20130` and `:8189` are ours.
- **`antigravity/claude-sonnet-4-6` passes every probe and has broken a real session.** It stays
  listed but is barred from the default slot (`SUSPECT_ROUTES`). The probe does not reproduce whatever
  kills it — do not promote it because the number looks good.
- **A "confirmed" label means confirmed for the layer that was tested.** `route_truth.json` calls 186
  routes valid; that is *chat*. Only 12 have ever been tool-probed. This wrong-layer read is the
  single most repeated bug in this project — it produced the giz.ai false capture, the stale
  `test_status` capacity overstatement, and this session.
- **An 8s timeout on `:8189` looks like a dead port.** Cold call needs >8s.

---

## 5. Files touched, and why

- `scripts/automation/98e83bfd-…json` — 18 entries → 5; one pinned default; dead routes and `pool/*`
  removed; labels renamed from `OmniRoute confirmed:` to the layer actually measured.
- `scripts/automation/sync_confirmed_models_to_clients.py` — the generator, and the reason the config
  would have regressed. Was rebuilding `inferenceModels` from the *chat* probe and manufacturing the
  `OmniRoute confirmed:` label at line 56. Now gates on `tool_fidelity.json`, hard-stops when it is
  missing rather than silently emitting chat-only truth, pins the fastest measured tool-safe route,
  labels the rest `UNVETTED for tools`, never emits `pool/*`, bars suspect routes from the default.
- `scripts/automation/rca_toolcall_session.py` — new; the probe that isolated this. Its docstring is
  the full RCA.
- `state/rca_toolcall_session.json` — its output.
