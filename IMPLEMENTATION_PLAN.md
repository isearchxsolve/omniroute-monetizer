# Implementation Plan — OmniRoute Monetizer V1

## Overview
This document defines the ordered, idempotent implementation sequence for
bringing the OmniRoute environment from "already running" to **MONETIZER_READY**
or **MONETIZER_BLOCKED**. Every phase must preserve the live runtime and
converge on repeated execution.

---

## Phase 0 — Runtime Preflight
**Goal:** Confirm OmniRoute is reachable; abort or defer if not.

## Phase 1 — Secure Management Authentication
**Goal:** Obtain a management session token without hard-coded secrets.

## Phase 2 — Provider / Account / Credential / Model / Route Normalization
**Goal:** Ensure all entities maintain distinct identities and no data is lost.

## Phase 3 — API-First Provider Onboarding & Repair
**Goal:** Bring non-functional providers into working state using the management API, falling back to Playwright only when the API cannot resolve the issue.

## Phase 4 — Minimal Live Verification
**Goal:** Confirm each candidate route with exactly one representative inference.

## Phase 5 — Routing Pools
**Goal:** Assemble verified models into the canonical routing pools.

## Phase 6 — Client Integration
- Zed
- Codex
- Claude Code

## Phase 7 — Performance Engineering
**Goal:** Baseline and improve end-to-end latency without degrading routing quality.

## Phase 8 — Acceptance Tests
**Goal:** Run after all phases. Every test must pass for **MONETIZER_READY**.
