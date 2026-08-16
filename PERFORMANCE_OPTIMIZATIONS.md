# Performance Optimizations

**Date:** 2026-08-15 09:51:53

## Applied Optimizations

- **No restart-dependent optimizations applied** (service preserved)
- Script uses connection reuse via urllib keep-alive
- Verification probes are minimal (max_tokens=10) to reduce inference cost
- Model list cached across steps within a single run

## Recommended Optimizations (Deferred)

These would require service restart or deeper integration:

1. **Response caching** for /v1/models (TTL 60s) — reduces repeated serialization
2. **Connection pooling** for provider health checks — reduces TCP handshake overhead
3. **Dead-route suppression** — prevent routing attempts to known-dead models
4. **Bounded retries** — limit retry amplification on transient failures
5. **Candidate reduction** — pre-filter provider/model candidates before routing
6. **SQLite query optimization** — index frequently queried columns
7. **Deduplication** — avoid redundant provider discovery/model import cycles

## Priority Fix Order Implemented

The live mitigation stack is now codified in `scripts/omniroute_performance_fixer.py` and ordered as:

1. Stale lock guardrails and read-only DB fallback for heavy endpoints
2. Aggressive TTL caching for `/v1/models`, `/api/providers`, and `/api/combos`
3. Live provider validation via actual inference probe before marking as healthy
4. Write-time validation of model IDs, provider IDs, and combo payloads
5. Request queue caps, timeout budgets, and circuit breakers
6. Response schema validation to reject silent empty `200` responses
7. Periodic catalog-to-combo reconciliation for production drift detection

This is intentionally non-destructive and does not require stopping the OmniRoute service.

## Constraints

- No routing quality trade-offs for superficial latency improvements
- All optimizations must be non-disruptive to live service