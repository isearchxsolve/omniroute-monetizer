// One serialized SQLite-backed coordinator per web job. No eventually-consistent
// read/check/write is used to grant an execution lease or accept a result.
export class WebJobCoordinator {
  constructor(ctx) {
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe TEXT UNIQUE, body TEXT NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS job (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)");
  }
  read() {
    const rows = [...this.sql.exec("SELECT body FROM job WHERE id=1")];
    return rows.length ? JSON.parse(rows[0].body) : null;
  }
  write(job) {
    this.sql.exec("INSERT INTO job(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", JSON.stringify(job));
  }
  reply(value, status=200) { return Response.json(value, {status}); }
  async fetch(request) {
    const action = new URL(request.url).pathname;
    // Parse before entering the synchronous SQLite mutation section.
    const input = request.method === "POST" ? await request.json() : {};
    if (action === "/append") {
      this.sql.exec("INSERT OR IGNORE INTO orders(dedupe,body) VALUES(?,?)",input.dedupe,JSON.stringify(input.order));
      this.sql.exec("DELETE FROM orders WHERE id NOT IN (SELECT id FROM orders ORDER BY id DESC LIMIT 2000)");
      return this.reply({ok:true});
    }
    if (action === "/orders") {
      const orders=[...this.sql.exec("SELECT body FROM orders ORDER BY id DESC LIMIT 2000")].reverse().map(row=>JSON.parse(row.body));
      return this.reply({orders});
    }
    let job = this.read();
    if (action === "/get") return this.reply(job || {err:"unknown_job"}, job ? 200 : 404);
    if (action === "/register") {
      if (!job) { job = input.job; this.write(job); }
      // Register is idempotent, never reset a lease that was already granted.
      return this.reply({ok:true, job});
    }
    if (!job) return this.reply({err:"unknown_job"},404);
    if (action === "/claim") {
      const generation = job.spec._queue_generation;
      const executor = job.spec.mode === "playwright" ? "playwright" : "fleet";
      if (input.generation !== generation || input.executor !== executor)
        return this.reply({claimed:false, reason:"stale_generation_or_wrong_executor"});
      if (!["pending","queued","queued_cold_harvest","healing_in_playwright"].includes(job.status))
        return this.reply({claimed:false, reason:"not_pending"});
      if (job.lease && job.lease.expires_at > Date.now())
        return this.reply({claimed:false, reason:"leased"});
      if (job.lease && !["GET","HEAD"].includes((job.spec.method || "GET").toUpperCase())) {
        job.status="failed"; job.error="execution lease expired; remote side-effect state unknown";
        this.write(job);
        return this.reply({claimed:false, reason:"side_effect_state_unknown"});
      }
      job.lease = {token:crypto.randomUUID(), expires_at:Date.now()+180000};
      this.write(job);
      return this.reply({claimed:true, spec:{...job.spec,job_id:job.job_id,_lease_token:job.lease.token}});
    }
    if (action === "/update") {
      if (!job.lease || input.lease !== job.lease.token || input.generation !== job.spec._queue_generation
          || job.lease.expires_at <= Date.now())
        return this.reply({ok:false,err:"stale_or_missing_execution_lease"},409);
      const next=input.job;
      if (next.job_id !== job.job_id) return this.reply({ok:false,err:"job_mismatch"},409);
      // Terminal writes or a single healing generation consume the lease atomically.
      next.lease=null;
      this.write(next);
      return this.reply({ok:true});
    }
    return this.reply({err:"unknown_action"},404);
  }
}
