"""Private durable checkpoints and a single-writer ASGI host for disposable sessions.

Only encrypted bytes leave the node. Acknowledged mutations are checkpointed before
responding; standby nodes cannot mutate until restored and given a writer lease.
"""
from __future__ import annotations
import asyncio,base64,hashlib,io,json,os,shutil,sqlite3,tarfile,tempfile,threading,time
from pathlib import Path
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class FilmVaultClient:
    def __init__(self,door,token,key):
        self.door=door.rstrip('/')
        self.headers={"Authorization":"Bearer "+token,"User-Agent":"omniroute-kaggle-worker"}
        self.key=base64.urlsafe_b64decode(key)
        self.http=requests.Session()
    def call(self,action,data=None):
        r=self.http.request('POST' if data is not None else 'GET',self.door+'/v1/film-vault/'+action,
                            headers=self.headers,json=data,timeout=45)
        if not r.ok:raise RuntimeError('film_vault_'+action+'_'+str(r.status_code))
        return r.json()
    def encrypt(self,plain):
        nonce=os.urandom(12)
        return nonce+AESGCM(self.key).encrypt(nonce,plain,b'oiioii-checkpoint-v1')
    def decrypt(self,cipher):return AESGCM(self.key).decrypt(cipher[:12],cipher[12:],b'oiioii-checkpoint-v1')
    def upload(self,raw):
        if not raw or len(raw)>32*1024*1024:raise ValueError('checkpoint exceeds bounded 32 MiB pilot storage')
        parts=[]
        for start in range(0,len(raw),262144):
            chunk=raw[start:start+262144];sha=hashlib.sha256(chunk).hexdigest()
            r=self.http.put(self.door+'/v1/film-vault/blob/'+sha,headers=self.headers,data=chunk,timeout=45)
            if not r.ok:raise RuntimeError('film_blob_upload_'+str(r.status_code))
            parts.append(sha)
        return {'parts':parts,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'format':'aes256gcm-tar-gzip-v1'}
    def download(self,manifest):
        chunks=[]
        for sha in manifest['parts']:
            r=self.http.get(self.door+'/v1/film-vault/blob/'+sha,headers=self.headers,timeout=45)
            if not r.ok or hashlib.sha256(r.content).hexdigest()!=sha:raise RuntimeError('checkpoint_chunk_integrity_failed')
            chunks.append(r.content)
        raw=b''.join(chunks)
        if len(raw)!=manifest['bytes'] or hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise RuntimeError('checkpoint_integrity_failed')
        return self.decrypt(raw)
    @staticmethod
    def extract(raw,target):
        target=Path(target).resolve();target.mkdir(parents=True,exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            for member in archive.getmembers():
                path=(target/member.name).resolve()
                if target not in path.parents or member.issym() or member.islnk() or not(member.isfile() or member.isdir()):
                    raise ValueError('unsafe_checkpoint_entry')
            archive.extractall(target,filter='data')
    def checkpoint(self,root,holder,lease,version):
        root=Path(root)
        with tempfile.TemporaryDirectory(prefix='oiioii-checkpoint-') as tmp:
            stage=Path(tmp)/'data';stage.mkdir()
            for path in root.rglob('*'):
                if not path.is_file() or path.name.endswith(('-wal','-shm','.tmp')):continue
                rel=path.relative_to(root);dst=stage/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                if path.suffix in ('.sqlite3','.db'):
                    source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
                    dest=sqlite3.connect(dst)
                    try:source.backup(dest)
                    finally:dest.close();source.close()
                else:shutil.copy2(path,dst)
            output=io.BytesIO()
            with tarfile.open(fileobj=output,mode='w:gz') as archive:
                for path in stage.rglob('*'):
                    if path.is_file():archive.add(path,arcname=str(path.relative_to(stage)),recursive=False)
            manifest=self.upload(self.encrypt(output.getvalue()))
        return self.call('checkpoint',{'holder':holder,'lease':lease,'expected_version':version,'manifest':manifest})['version']
    def restore(self,target):
        state=self.call('state')
        if state.get('checkpoint'):
            self.extract(self.download(state['checkpoint']),target)
        return state['version']

class DurableFilmHost:
    def __init__(self,root,holder,vault,control_key,mode='standby'):
        self.root=Path(root);self.holder=holder;self.vault=vault;self.control_key=control_key
        self.app=None;self.lifespan=None;self.mode='standby';self.lease=None;self.version=0
        self.lock=asyncio.Lock();self.start_mode=mode;self.heartbeat_task=None
    async def activate(self):
        if self.mode=='active':return
        # Lease FIRST: another writer cannot mutate while the latest checkpoint restores.
        claim=None
        for attempt in range(25):
            try:
                claim=await asyncio.to_thread(self.vault.call,'acquire',{'holder':self.holder})
                break
            except Exception as exc:
                if attempt<24 and ('writer_exists' in str(exc) or '409' in str(exc)):
                    await asyncio.sleep(5)
                    continue
                raise
        self.lease=claim['lease']
        try:
            self.version=await asyncio.to_thread(self.vault.restore,self.root)
            if self.app is None:
                from app.main import app
                from fastapi.staticfiles import StaticFiles
                frontend=Path(__file__).resolve().parent / "app/frontend/dist"
                if frontend.is_dir():app.mount("/",StaticFiles(directory=str(frontend),html=True),name="frontend")
                self.app=app
                self.lifespan=app.router.lifespan_context(app)
                await self.lifespan.__aenter__()
            self.mode='active'
            self.version=await asyncio.to_thread(self.vault.checkpoint,self.root,self.holder,self.lease,self.version)
        except Exception:
            self.mode='standby'
            await asyncio.to_thread(self.vault.call,'release',{'holder':self.holder,'lease':self.lease})
            raise
    async def heartbeat(self):
        while True:
            await asyncio.sleep(20)
            if self.mode=='active':
                try:await asyncio.to_thread(self.vault.call,'renew',{'holder':self.holder,'lease':self.lease})
                except Exception:self.mode='lease_lost'
    async def respond(self,send,value,status=200):
        raw=json.dumps(value).encode()
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(raw)).encode())]})
        await send({'type':'http.response.body','body':raw})
    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':
            while True:
                message=await receive()
                if message['type']=='lifespan.startup':
                    try:
                        if self.start_mode=='active':await self.activate()
                        self.heartbeat_task=asyncio.create_task(self.heartbeat())
                        await send({'type':'lifespan.startup.complete'})
                    except Exception as exc:
                        import traceback; traceback.print_exc()
                        await send({'type':'lifespan.startup.failed','message':f'{type(exc).__name__}: {exc}'})
                elif message['type']=='lifespan.shutdown':
                    if self.heartbeat_task:self.heartbeat_task.cancel()
                    if self.mode=='active':
                        try:await asyncio.to_thread(self.vault.call,'release',{'holder':self.holder,'lease':self.lease})
                        except Exception:pass
                    if self.lifespan:await self.lifespan.__aexit__(None,None,None)
                    await send({'type':'lifespan.shutdown.complete'});return
            return
        if scope['type']!='http':return
        path=scope.get('path','');headers=dict(scope.get('headers') or [])
        if path.startswith('/internal/'):
            if headers.get(b'x-film-control',b'').decode()!=self.control_key:
                return await self.respond(send,{'error':'unauthorized'},401)
            if path=='/internal/diagnostics':
                base=Path(__file__).resolve().parent
                rows={}
                for name in ('api.log','pool.log'):
                    file=base/name
                    text=file.read_text(errors='replace')[-12000:] if file.exists() else ''
                    for secret in (self.control_key,base64.urlsafe_b64encode(self.vault.key).decode()):text=text.replace(secret,'[redacted]')
                    rows[name]=text
                return await self.respond(send,rows)
            async with self.lock:
                try:
                    if path=='/internal/activate':await self.activate()
                    elif path=='/internal/drain' and self.mode=='active':
                        self.mode='draining'
                        self.version=await asyncio.to_thread(self.vault.checkpoint,self.root,self.holder,self.lease,self.version)
                        await asyncio.to_thread(self.vault.call,'release',{'holder':self.holder,'lease':self.lease})
                    elif path=='/internal/shutdown':
                        if self.mode=='active':
                            self.mode='draining'
                            self.version=await asyncio.to_thread(self.vault.checkpoint,self.root,self.holder,self.lease,self.version)
                            await asyncio.to_thread(self.vault.call,'release',{'holder':self.holder,'lease':self.lease})
                        asyncio.get_event_loop().call_later(0.5, os._exit, 0)
                        return await self.respond(send,{'holder':self.holder,'mode':'shutting_down'})
                    return await self.respond(send,{'holder':self.holder,'mode':self.mode,'checkpoint_version':self.version})
                except Exception as exc:
                    return await self.respond(send,{'error':type(exc).__name__},503)
        if path=='/healthz' and self.app is None:
            return await self.respond(send,{'status':'standby','holder':self.holder},503)
        if self.app is None:return await self.respond(send,{'error':'standby'},503)
        if scope.get('method') in ('GET','HEAD','OPTIONS'):
            return await self.app(scope,receive,send)
        async with self.lock:
            if self.mode!='active':return await self.respond(send,{'error':'writer_not_active'},503)
            try:await asyncio.to_thread(self.vault.call,'renew',{'holder':self.holder,'lease':self.lease})
            except Exception:
                self.mode='lease_lost';return await self.respond(send,{'error':'writer_lease_lost'},503)
            messages=[]
            async def collect(message):messages.append(message)
            try:
                await self.app(scope,receive,collect)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                return await self.respond(send,{'error':'application_execution_failed','error_type':type(exc).__name__},500)
            try:self.version=await asyncio.to_thread(self.vault.checkpoint,self.root,self.holder,self.lease,self.version)
            except Exception:return await self.respond(send,{'error':'durability_checkpoint_failed; operation outcome retained locally, reconcile before retry'},503)
            for message in messages:await send(message)
