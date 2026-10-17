// Private encrypted checkpoint storage. SQLite BLOBs are bounded to 256 KiB.
// The ciphertext key never enters this service; manifests use optimistic versions.
const MAX_BYTES=32*1024*1024;
const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
export class FilmVault {
  constructor(ctx) {
    this.sql=ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS blobs (sha TEXT PRIMARY KEY, payload BLOB NOT NULL)");
  }
  read(){const r=[...this.sql.exec("SELECT body FROM meta WHERE id=1")];return r.length?JSON.parse(r[0].body):{version:0};}
  write(s){this.sql.exec("INSERT INTO meta(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",JSON.stringify(s));}
  reply(b,status=200){return Response.json(b,{status});}
  validLease(s,d){return s.lease && s.lease.holder===d.holder && s.lease.token===d.lease && s.lease.until>Date.now();}
  manifest(m){
    if (!m || !Array.isArray(m.parts) || !m.parts.length || m.parts.length>128 || !/^[a-f0-9]{64}$/.test(m.sha256||"")) return false;
    let bytes=0;
    for(const sha of m.parts){if(!/^[a-f0-9]{64}$/.test(sha)) return false;const rows=[...this.sql.exec("SELECT length(payload) AS n FROM blobs WHERE sha=?",sha)];if(!rows.length)return false;bytes+=rows[0].n;}
    return bytes===m.bytes && bytes<=MAX_BYTES;
  }
  gc(s){const keep=new Set([s.deployment,s.checkpoint,s.previous].flatMap(m=>m?.parts||[]));
    for(const row of this.sql.exec("SELECT sha FROM blobs"))if(!keep.has(row.sha))this.sql.exec("DELETE FROM blobs WHERE sha=?",row.sha);}
  async fetch(request){
    const path=new URL(request.url).pathname;
    if(path.startsWith("/blob/")){
      const sha=path.slice(6);if(!/^[a-f0-9]{64}$/.test(sha))return this.reply({error:"invalid_hash"},400);
      if(request.method==="GET") {const r=[...this.sql.exec("SELECT payload FROM blobs WHERE sha=?",sha)];return r.length?new Response(r[0].payload,{headers:{"content-type":"application/octet-stream"}}):this.reply({error:"missing_blob"},404);}
      if(request.method!=="PUT")return this.reply({error:"method"},405);
      const b=await request.arrayBuffer();if(b.byteLength>262144 || await hash(b)!==sha)return this.reply({error:"invalid_blob"},400);
      this.sql.exec("INSERT OR IGNORE INTO blobs(sha,payload) VALUES(?,?)",sha,b);return this.reply({stored:true});
    }
    const d=request.method==="POST"?await request.json():{};
    const s=this.read();
    if(path==="/state")return this.reply({version:s.version,checkpoint:s.checkpoint||null,deployment:s.deployment||null,
      writer:s.lease&&s.lease.until>Date.now()?s.lease.holder:null,active:s.active||null});
    if(path==="/deployment") {if(!this.manifest(d.manifest))return this.reply({error:"invalid_manifest"},400);s.deployment=d.manifest;this.write(s);return this.reply({stored:true});}
    if(path==="/acquire") {
      if(typeof d.holder!=="string"||!/^[a-zA-Z0-9_.-]{1,100}$/.test(d.holder))return this.reply({error:"invalid_holder"},400);
      if(s.lease&&s.lease.until>Date.now()&&s.lease.holder!==d.holder)return this.reply({error:"writer_exists"},409);
      s.lease={holder:d.holder,token:crypto.randomUUID(),until:Date.now()+120000};this.write(s);
      return this.reply({lease:s.lease.token,version:s.version});
    }
    if(path==="/renew"||path==="/release") {
      if(!this.validLease(s,d))return this.reply({error:"writer_lease_invalid"},409);
      if(path==="/renew")s.lease.until=Date.now()+120000;else s.lease=null;
      this.write(s);return this.reply({ok:true,version:s.version});
    }
    if(path==="/checkpoint"){
      if(!this.validLease(s,d)||d.expected_version!==s.version)return this.reply({error:"writer_or_version_conflict"},409);
      if(!this.manifest(d.manifest))return this.reply({error:"invalid_manifest"},400);
      s.previous=s.checkpoint;s.checkpoint=d.manifest;s.version+=1;this.write(s);this.gc(s);
      return this.reply({stored:true,version:s.version});
    }
    if(path==="/promote"){
      if(!s.lease||s.lease.until<=Date.now()||s.lease.holder!==d.holder||s.version!==d.version)return this.reply({error:"writer_or_version_conflict"},409);
      s.active={holder:d.holder,url:d.url,film_id:d.film_id,sha256:d.sha256,verified_at:Date.now()};this.write(s);return this.reply({promoted:true,version:s.version});
    }
    return this.reply({error:"not_found"},404);
  }
}

export async function filmVaultRoute(request,env,path){
  const stub=env.FILM_VAULT.get(env.FILM_VAULT.idFromName("oiioii-production"));
  if(path.startsWith("/v1/film-vault/")) {
    if(!env.FILM_STORAGE_TOKEN || request.headers.get("Authorization")!=="Bearer "+env.FILM_STORAGE_TOKEN)return Response.json({error:"unauthorized"},{status:401});
    const action=path.slice("/v1/film-vault".length);
    if(action==="/promote"){
      const d=await request.json();
      const origin=new URL(d.url);
      if(origin.protocol!=="https:" || !origin.hostname.endsWith(".trycloudflare.com"))return Response.json({error:"invalid_candidate"},{status:400});
      if(!/^film_[a-f0-9]+$/.test(d.film_id||""))return Response.json({error:"invalid_film"},{status:400});
      const endpoint=origin.origin+"/api/v1/films/"+d.film_id+"/artifact";
      const denied=await fetch(endpoint,{redirect:"manual"});
      if(![401,403].includes(denied.status))return Response.json({error:"candidate_auth_gate_failed"},{status:409});
      const delivered=await fetch(endpoint,{headers:{Authorization:"Bearer "+d.owner_token},redirect:"manual"});
      if(delivered.status!==200 || !(delivered.headers.get("content-type")||"").startsWith("video/mp4"))return Response.json({error:"candidate_delivery_failed"},{status:409});
      const bytes=await delivered.arrayBuffer();
      if(bytes.byteLength>MAX_BYTES || bytes.byteLength!==d.bytes || await hash(bytes)!==d.sha256)return Response.json({error:"candidate_hash_failed"},{status:409});
      // Never persist the customer's bearer credential.
      const accepted={holder:d.holder,url:origin.origin,film_id:d.film_id,sha256:d.sha256,version:d.version};
      return stub.fetch("https://vault/promote",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(accepted)});
    }
    const headers=new Headers(request.headers);headers.delete("Authorization");
    return stub.fetch(new Request("https://vault"+action,{method:request.method,headers,body:["GET","HEAD"].includes(request.method)?undefined:request.body,redirect:"manual"}));
  }
  if(path==="/oiioii"||path.startsWith("/oiioii/")) {
    const state=await(await stub.fetch("https://vault/state")).json();
    if(!state.active || !state.writer)return Response.json({error:"film_service_not_ready"},{status:503});
    if(state.active.holder!==state.writer)return Response.json({error:"film_handover_in_progress"},{status:503});
    const incoming=new URL(request.url), suffix=path.slice("/oiioii".length)||"/";
    const target=state.active.url+suffix+incoming.search;
    const headers=new Headers(request.headers);headers.delete("host");headers.delete("x-film-storage-token");
    return fetch(target,{method:request.method,headers,body:["GET","HEAD"].includes(request.method)?undefined:request.body,redirect:"manual"});
  }
  return null;
}
