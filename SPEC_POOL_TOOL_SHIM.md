# SPEC — pool tool-call shim for :20130

Owner: orchestrator (this repo owns the `:20130` chat contract). Status: **spec, not built.**
Written 2026-08-27.

## Why this exists

The harvested chat pool is the supply this project is built on. Today it serves chat and strict JSON
and nothing else, so every agentic client — Claude Code, Codex CLI, ZCode — is pushed onto paid
routes, which discards the harvest. That is the gap this spec closes.

**The pool is not incapable of tool use. `:20130` simply never translates for it.**

Evidence it is capable **[VERIFIED]**: `preflight_planner.py --scenes 6` gets strict, parseable JSON
out of `pool/auto` 6 times out of 6. A seat that can be held to a JSON contract by prompt can be held
to a tool-call contract by prompt. Nothing else is required of the upstream.

Evidence of the two real constraints **[VERIFIED 2026-08-27,
`scripts/automation/rca_toolcall_session.py`]**:

1. `pool/claude-sonnet-4-6` with a 44-tool array returns `no_tool_use` — the tools array is passed
   through and discarded, because a replayed chat UI has nowhere to put it.
2. At 61–67KB that same request came back as **scraped page HTML**
   (`width=device-width, initial-scale=1Skip the groundwork with our AI-ready Web Search APIs…`) —
   the replay overflowed. Consumer chat UIs cap message length. A full Claude Code tools array does
   not fit and must be subsetted.

## The failure this shim must make impossible

With no shim, an agentic client on a pool seat produces this, ~40 times in a row:

```
Error: No such tool available: read
Error: No such tool available: bash
```

The model cannot see a tools array, still reads in its system prompt that it has tools, and invents
them from habit — an invented shell tool is written `bash`, an invented file reader `read`. The
client's dispatcher is case-sensitive and rejects every one. **Chat looks perfect throughout.**

---

## Contract

### 1. Trigger

Engage the shim when **both** hold:

- the resolved route is `pool/*` (including a `pool/*` reached by fallback from a refusing upstream —
  fallback is where this bites hardest, because the caller never chose the pool), and
- the request carries a non-empty `tools` array.

Otherwise pass through untouched. Never engage for non-pool routes: they answer `tool_use` natively
and **[VERIFIED]** five of them return `Bash` byte-for-byte at 44 tools.

### 2. Budget the tools array — it will not fit

Render tools to text under a hard byte ceiling (start at 8KB; the observed break is ~61KB, so leave
wide margin). In priority order:

1. Name + first sentence of description + required params only. Drop prose, examples, enums.
2. If still over: drop to name + one line each.
3. If still over: **two-phase**. Turn 1 sends names only and asks which tool. Turn 2 sends just that
   tool's full schema and asks for arguments. Two cheap pool calls beat one overflowing call.

Log what was dropped. Silent truncation reads as "all tools offered" when it wasn't — that is the
same wrong-layer inference this repo keeps paying for.

### 3. Prompt contract

Reuse the discipline that already scores 6/6 on the planner: explicit fenced JSON, one shape, no
prose. Ask for exactly:

```json
{"tool": "<name from the list>", "input": { ... }}
```

…or a sentinel such as `{"tool": null, "text": "..."}` when no tool is warranted. Do **not** ask for
Anthropic block syntax; ask for the smallest JSON that carries the same information.

### 4. Resolve the name against the registry — THE LOAD-BEARING RULE

Match the returned tool name against the request's `tools` array **case-insensitively, ignoring
separators**, and emit the **exact registered name** in the `tool_use` block.

So a seat replying `bash`, `Bash`, `BASH` or `bash_tool` all resolve to the registered `Bash`.

This one rule kills the entire bug class at the shim layer, permanently, no matter what the seat
returns. It is worth more than every other line in this document. If the name resolves to nothing in
the array, that is a hard error (§6) — never a guess, never a passthrough.

### 5. Multi-turn loops

An agentic session is tool → `tool_result` → tool. A replayed chat UI has no native `tool_result`, so
render prior turns into the prompt as compact text (`Tool Bash returned: <stdout, truncated>`) and
keep the running transcript inside the pool session. Truncate oldest-first against the same byte
ceiling as §2.

### 6. Fail closed, loudly

If tools were sent and no valid tool call parses, return an explicit error — **never prose that the
client will render as an assistant answer.** Prose in that position is what made this look like a
model problem for a full session instead of a routing problem. If the seat returns page HTML (detect:
`<!DOCTYPE`, `<html`, `width=device-width`), treat it as seat overflow, mark the seat, and fail over.

### 7. Do not regress what already works

The planner path (`pool/auto`, no `tools` array, strict JSON) is **[VERIFIED]** 6/6 and must be
untouched. It is also the regression test: after the shim ships,
`preflight_planner.py --scenes 6` must still exit 0.

---

## Verification — the probe must be fixed too

`state/tool_fidelity.json` has **[VERIFIED]** probed **zero** pool seats, and
`probe_tool_fidelity.py` hardcodes `BASE = "http://127.0.0.1:20128"`, so it structurally cannot see
them. Before this shim can be trusted:

1. Point the probe at `:20130` so `pool/*` is reachable.
2. Add the pool seats to its target list.
3. Probe at **real client scale** — ~44 tools, ~61KB, not the current 14-tool `--heavy`. The 14-tool
   probe passes routes that then fail live (`antigravity/claude-sonnet-4-6` is the standing example).
4. Accept `tools_ok` for a pool seat **only** via the shim, and re-run the planner preflight to prove
   §7.

Until a pool seat has passed that, its config label must keep saying **CHAT/JSON ONLY**.

## Definition of done

A pool seat, selected explicitly in an agentic client, executes a real tool call end to end, and
`preflight_planner.py --scenes 6` still exits 0. At that point the harvested supply serves agents,
the labels in
`scripts/automation/98e83bfd-e627-4557-a52e-9dcc8a008f50.json` change from CHAT/JSON ONLY to
TOOL-SAFE with a measurement date, and the paid-route recommendation goes away.
