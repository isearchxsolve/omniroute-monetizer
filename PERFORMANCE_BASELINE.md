# Performance Baseline

**Date:** 2026-08-14 12:08:08
**OmniRoute:** v3.8.49 on http://localhost:20128

## Baseline Measurements

### auto/best-chat
- Min: 6.938s
- Max: 7.14s
- Avg: 7.039s
- Runs: 2

### auto/best-coding
- Min: 7.406s
- Max: 8.875s
- Avg: 8.141s
- Runs: 2

### auto/pro-coding
- Min: 6.656s
- Max: 11.36s
- Avg: 9.008s
- Runs: 2

### auto/pro-reasoning
- Min: 6.687s
- Max: 6.797s
- Avg: 6.742s
- Runs: 2

### mgmt_login
- Min: 2.531s
- Max: 2.625s
- Avg: 2.578s
- Runs: 2

### root
- Min: 6.187s
- Max: 6.204s
- Avg: 6.198s
- Runs: 3

### v1_models
- Min: 12.0s
- Max: 12.0s
- Avg: 12.0s
- Runs: 1

## Notes

- Measurements taken via localhost loopback
- Chat probes use minimal max_tokens=10
- /v1/models may include 50+ model entries
- Management API auth adds cookie/session overhead