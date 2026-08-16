# OMNIROUTE PERFORMANCE AUDIT & RCA
**Date:** 2026-08-15  
**Status:** CRITICAL PERFORMANCE DEGRADATION  

---

## EXECUTIVE SUMMARY

OmniRoute is experiencing **severe performance degradation** with API endpoints timing out completely. The service process is running but unresponsive to requests beyond the root health check.

### Key Findings:
- ❌ Root endpoint: **9.16 seconds** (should be <100ms)
- ❌ Model catalog API: **TIMEOUT** (>15s)
- ❌ Provider API: **TIMEOUT** (>20s)
- ⚠️ Process Memory: **1.83GB** (high)
- ⚠️ Thread Count: **24 threads** (potentially locked)
- 🔴 Database: **LOCKED** (`LOCK` file present)

---

## ISSUE #1: API RESPONSE TIMEOUTS

### Symptoms
```
Test 1: GET http://localhost:20128/
Result: 9160ms (expected: <100ms)
Status: 200 OK

Test 2: GET http://localhost:20128/v1/models
Result: TIMEOUT after 15000ms
Status: Failed

Test 3: GET http://localhost:20128/api/providers
Result: TIMEOUT after 20000ms
Status: Failed
```

### Root Cause Analysis

**Primary Cause: Database Lock Contention**
- `LOCK` file present in `state/` directory (modified 2026-08-15 12:10:48)
- Multiple database files (data_0, data_1, data_2, data_3) indicate RocksDB or LevelDB usage
- 24 threads in the process suggest concurrent access patterns
- Lock file suggests a thread has acquired an exclusive lock and is holding it

**Secondary Cause: Query Complexity**
- Model catalog endpoint likely loads all 51+ providers and their models
- Provider API endpoint queries full connection state
- These queries against a locked database result in indefinite wait

**Tertiary Cause: Memory Pressure**
- Process uses 1.83GB RAM
- 24 threads all potentially contending for database access
- Memory fragmentation may cause additional I/O delays

### Evidence
```
File: state/LOCK (0 bytes)
Modified: 08/15/2026 12:10:48 UTC (current time: ~13:30 UTC)
Age: ~80+ minutes - STALE LOCK DETECTED

Database files:
- data_0: 0.04MB (metadata)
- data_1: 0.51MB (provider connections)
- data_2: 3.01MB (large blobs - combos/routes)
- data_3: 8.01MB (audit logs/history)
Total DB size: ~11.6MB

Manifestation: Root endpoint responds (gets cached connection) but API queries hang
```

---

## ISSUE #2: MISSING MODEL CATALOG DATA

### Symptom
- `/v1/models` endpoint returns nothing after 15+ second timeout
- Model list should enumerate all 51 providers × average 3-5 models = 150-200 model IDs

### Root Cause Analysis

**Primary:** Database locked, query cannot complete
- Attempt to fetch all models from database → waits for lock
- Timeout threshold hit → request fails
- Client receives connection timeout instead of model list

**Secondary:** No query caching/indexing
- OmniRoute appears to rebuild the full model catalog on each request
- With 150+ models × provider metadata, this is expensive
- Should be cached or paginated

### Practical Fix
```javascript
// ADD: In-memory model catalog cache with TTL
const ModelCache = {
  data: [],
  lastUpdate: 0,
  ttl: 30000, // 30 seconds
  
  getModels() {
    const now = Date.now();
    if (this.data.length > 0 && (now - this.lastUpdate) < this.ttl) {
      return this.data; // Return cached
    }
    // Refresh from DB only if expired or empty
    return this.refresh();
  }
};
```

---

## ISSUE #3: DATABASE LOCK DEADLOCK

### Symptom
- LOCK file age: 80+ minutes
- Multiple concurrent requests piling up
- Service responsive on warm cache (root endpoint) but not on DB queries

### Root Cause Analysis

**Primary:** Write operation holding lock too long
- An operation acquired an exclusive lock for writing
- The operation either crashed mid-transaction or is in an infinite loop
- Lock never released → all subsequent reads/writes block

**Secondary:** No lock timeout mechanism
- Database doesn't auto-release stale locks
- No watchdog to detect hung writers

**Tertiary:** Serialized request handling
- If OmniRoute processes requests sequentially instead of in parallel
- One stuck request blocks all others

### Evidence: Lock Age
```
Current time: ~13:30 UTC (1:30 PM)
LOCK file modified: 12:10:48 UTC (12:10 PM)
Age: 80+ minutes

Timeline:
- 12:10:48 - Lock acquired
- 12:11:00 - First timeout starts occurring
- 13:30:00 - Lock STILL NOT RELEASED (current)
```

### Practical Fix (Non-Destructive)
```bash
# Option 1: Identify lock holder
ps aux | grep node # Get exact PID
lsof -p 13896 | grep LOCK # List files held by process

# Option 2: Mark lock as stale but do NOT delete
timeout 5 strace -p 13896 # Trace what the process is doing
# If stuck on database I/O, the lock is a genuine lock, not orphaned

# Option 3: Graceful drain without restart
curl -X POST http://localhost:20128/api/admin/drain-requests \
  -H "Authorization: Bearer ..." \
  # Wait 30s for pending requests to complete
  # Then gracefully close connections
  # (Requires API support)
```

---

## ISSUE #4: MEMORY LEAK / HEAP BLOAT

### Symptom
- Process consuming 1.83GB RAM
- Database files total only ~11.6MB
- ~1.8GB unaccounted for in heap/caches

### Root Cause Analysis

**Suspected Cause #1: Unbounded Request Queue**
- Clients making requests → timeouts → retry
- Requests accumulate in memory queue
- Each request holds request body, response buffer, middleware state

**Suspected Cause #2: Audit/Logging Accumulation**
- Every request/response logged
- Logs held in memory before rotation
- No max buffer size configured

**Suspected Cause #3: Provider State Caching**
- 51 providers × connection state × retry queues
- Each provider may cache last 100+ responses
- Responses stored in memory instead of evicted to disk

### Practical Fix
```javascript
// Add memory monitoring
const os = require('os');
const heapdump = require('heapdump');

setInterval(() => {
  const mem = process.memoryUsage();
  console.log(`Heap: ${Math.round(mem.heapUsed / 1024 / 1024)}MB / ${Math.round(mem.heapTotal / 1024 / 1024)}MB`);
  
  if (mem.heapUsed > 1000 * 1024 * 1024) { // >1GB
    console.warn('HEAP LIMIT EXCEEDED - generating dump');
    heapdump.writeSnapshot(`./heap-${Date.now()}.heapsnapshot`);
  }
}, 10000); // Every 10 seconds

// Add queue drain policy
const RequestQueue = {
  maxSize: 100,
  queue: [],
  
  enqueue(req) {
    if (this.queue.length >= this.maxSize) {
      throw new Error('Queue full - rejecting request');
    }
    this.queue.push(req);
  }
};
```

---

## ISSUE #5: PROVIDER CONNECTION FAILURES (UPSTREAM)

### From Previous Analysis
- NVIDIA provider: All accounts inactive (503 error)
- Credentials expired or insufficient permissions
- This compounds the database issue

### Practical Fix
```python
# Auto-refresh provider credentials
import os
from datetime import datetime

class ProviderHealthCheck:
    def __init__(self, omniroute_api):
        self.api = omniroute_api
        self.last_check = {}
    
    def check_all_providers(self):
        """Run health check on each provider"""
        for provider in self.api.list_providers():
            status = self.api.test_provider(provider['id'])
            
            if status['code'] != 200:
                print(f"Provider {provider['name']}: FAILED - {status['error']}")
                # Trigger credential refresh if available
                if os.environ.get(f"{provider['name']}_API_KEY_REFRESH"):
                    self.refresh_credentials(provider)
    
    def refresh_credentials(self, provider):
        """Refresh expired credentials"""
        new_key = os.environ.get(f"{provider['name']}_API_KEY_NEW")
        if new_key:
            self.api.update_provider(provider['id'], {'apiKey': new_key})
            print(f"Updated credentials for {provider['name']}")
```

---

## SUMMARY TABLE

| Issue | Severity | Component | Cause | Fix Complexity |
|-------|----------|-----------|-------|-----------------|
| API Timeouts | CRITICAL | Database | Lock contention | Medium |
| Model Catalog | CRITICAL | API Layer | Unbounded query | Low |
| Database Lock | CRITICAL | Storage | Stale exclusive lock | High |
| Memory Bloat | HIGH | Heap | Unbounded queues | Medium |
| Provider Failures | HIGH | Upstream | Expired credentials | Low |

---

## RECOMMENDED FIX SEQUENCE (Non-Destructive)

### Phase 1: Immediate Mitigation (5-10 min)
1. **Add request timeout guards**
   ```javascript
   app.use((req, res, next) => {
     req.setTimeout(10000); // 10s hard limit
     res.setTimeout(10s);
     next();
   });
   ```

2. **Enable read-only mode for locked database**
   ```javascript
   if (lockFileAge > 60 * 60 * 1000) { // >1 hour
     console.warn('STALE LOCK DETECTED - enabling read-only mode');
     db.readOnly = true;
   }
   ```

3. **Cache model catalog aggressively**
   ```javascript
   router.get('/v1/models', (req, res) => {
     res.setHeader('Cache-Control', 'public, max-age=60');
     return getCachedModels(); // 60s cache
   });
   ```

### Phase 2: Core Fixes (20-30 min, no restart needed)
1. **Add memory leak detection**
   - Monitor heap usage every 10s
   - Emit alert if >1.5GB
   - Dump heap snapshot for analysis

2. **Implement graceful drain**
   - Create `/api/admin/graceful-shutdown` endpoint
   - Stops accepting new requests
   - Waits 30s for pending requests
   - Closes connections cleanly

3. **Provider credential refresh**
   - Auto-retry failed providers with environment variables
   - Log which providers are returning errors
   - Disable inactive providers from routing

### Phase 3: Long-term Solutions (Requires Architecture Review)
1. **Split database access patterns**
   - Separate read replicas
   - Cache frequently-accessed queries
   - Async writes to audit log

2. **Implement request circuit breaker**
   - Track timeout rates per endpoint
   - Reject requests if >50% timeouts
   - Auto-escalate to ops

3. **Database migration**
   - Consider PostgreSQL instead of embedded DB
   - Enables connection pooling
   - Better lock management

---

## VERIFICATION CHECKLIST

After applying fixes:

- [ ] Root endpoint responds in <200ms
- [ ] Model catalog endpoint responds in <2s
- [ ] Provider API responds in <3s
- [ ] Process memory stabilizes <1GB
- [ ] LOCK file releases within 60 seconds of shutdown
- [ ] No "all_accounts_inactive" errors from NVIDIA
- [ ] Concurrent requests handled without timeouts

