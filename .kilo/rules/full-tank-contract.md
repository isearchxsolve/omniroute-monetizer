# FULL TANK CONTRACT (OPERATOR MANDATE 2026-09-04)

> Injected into every session. "Full tank" means ALL lanes, ALL providers — NOT a handful,
> NOT one lane. Thin-provider grinding (small seats while giants wait) is forbidden.

## 1. OMNI LANE (the giants)
- All ~11,662 catalog rows carry terminal verdicts. No row abandoned.
- ALL direct-proven routes (382 as of 2026-09-04) each get a consumer proof through :8190.
- Every passing route lands ADMITTED in `state/omniroute_verified_routes.json` and is
  visible on `/v1/models`. Target: 21 → 300+ admitted routes.
- The shim's `_omni_consumer_proof_eligible_ids()` lets DIRECT_LAW3_OK routes from the
  graduation run file be dispatched for consumer proof; the ledger stays the authority
  for ADMITTED. (Deadlock fix 2026-09-04.)

## 2. SEAT CHAT LANE
- All dispatchable seats consumer-proven live with computed Law-3 proof (target 12/12).
- groq + chathub: re-auth queue. felo: Cloudflare wall (named, evidence archived).

## 3. SEAT VIDEO LANE
- All video seats graduated or walled. LTX admitted; rtst/Flow renders in flight;
  kie = insufficient credits (wall); aistudio = capture needed.

## 4. REPORTING LANGUAGE (NON-NEGOTIABLE)
- One line per lane: **"X/Y proven, Z walls, evidence attached."**
- Never claim done until every supply unit is proven or has a named wall.
- Walls named plainly (Google queue, Cloudflare, dead credits) with archived evidence.
- Claims still require the matching acceptance state (CAPACITY_ADMITTED etc.).
- No goalpost moving. ETA given in hours/days, honestly.
