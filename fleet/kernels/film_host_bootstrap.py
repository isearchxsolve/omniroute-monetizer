"""Kaggle CPU bootstrap. Deployment config is injected only into private notebooks."""
import base64,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile,threading,time,urllib.request
from pathlib import Path

BASE=Path('/kaggle/working/oiioii-live')
BASE.mkdir(exist_ok=True)
# FILM_CONFIG is supplied by the private notebook generator, never by the repository.
config=FILM_CONFIG
DOOR=config['door'];HEAD={'Authorization':'Bearer '+config['storage_token'],'User-Agent':'omniroute-kaggle-worker'}

def fetch(path):
    req=urllib.request.Request(DOOR+'/v1/film-vault/'+path,headers=HEAD)
    try:return urllib.request.urlopen(req,timeout=45).read()
    except urllib.error.HTTPError as exc:
        print('Actual storage fetch status',exc.code,'body',exc.read(300).decode('utf-8','replace'),flush=True)
        raise

print('Film bootstrap Python',sys.version.split()[0],flush=True)
subprocess.run([sys.executable,'-m','pip','install','-q','--prefer-binary','--no-input','fastapi>=0.115,<1','uvicorn','pydantic>=2.10,<3',
    'pydantic-settings>=2.6,<3','sqlalchemy>=2,<3','aiosqlite','slowapi','email-validator',
    'python-multipart','python-dotenv','httpx>=0.27,<1','openai>=1.65,<3','groq','cohere',
    'requests','cryptography','curl_cffi','selenium','websocket-client','pycryptodome'],check=True,timeout=240)
print('Film bootstrap dependencies ready',flush=True)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
state=json.loads(fetch('state'));manifest=state['deployment']
parts=[]
for sha in manifest['parts']:
    chunk=fetch('blob/'+sha)
    assert hashlib.sha256(chunk).hexdigest()==sha,'deployment chunk integrity'
    parts.append(chunk)
raw=b''.join(parts)
assert hashlib.sha256(raw).hexdigest()==manifest['sha256'],'deployment integrity'
plain=AESGCM(base64.urlsafe_b64decode(config['encryption_key'])).decrypt(raw[:12],raw[12:],b'oiioii-checkpoint-v1')
with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as archive:
    for member in archive.getmembers():
        target=(BASE/member.name).resolve()
        assert BASE in target.parents and not member.issym() and not member.islnk(),'unsafe deployment entry'
    archive.extractall(BASE,filter='data')
print('Encrypted deployment verified and restored:',manifest['sha256'],flush=True)
front=BASE/'app/frontend'
try:
    if shutil.which('npm'):
        subprocess.run(['npm','install','--no-audit','--no-fund'],cwd=front,check=True,timeout=180,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
        build_env={**os.environ,'VITE_API_URL':'/oiioii/api/v1'}
        subprocess.run(['npm','run','build','--','--base=/oiioii/'],cwd=front,env=build_env,check=True,timeout=120,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
except Exception as exc:print('Frontend build needs attention:',type(exc).__name__,flush=True)
# The actual app and provider pool run on the same disposable node; persistent data
# live in encrypted checkpoints owned by the permanent FilmVault.
private=json.loads((BASE/'private-config.json').read_text())
env={**os.environ,'PYTHONPATH':str(BASE/'app/backend')+os.pathsep+str(BASE),
    'DATABASE_URL':'sqlite+aiosqlite:///'+str(BASE/'data/accounts.sqlite3'),
    'FILM_PIPELINE_STORAGE_PATH':str(BASE/'data/film'),'FILM_PIPELINE_OBJECT_STORE_PATH':str(BASE/'data/objects'),
    'FILM_PIPELINE_CONSUMER_BASE_URL':'http://127.0.0.1:8190','FILM_PIPELINE_VIDEO_MODEL':'video/auto',
    'OMNI_CONSUMER_API_KEY':private['consumer_key'],'OMNI_VIDEO_CONFIRM_SPEND':'1','OMNI_VIDEO_MAX_SPEND':'0',
    'OMNI_VIDEO_JOB_STORE':str(BASE/'data/video_jobs.json'),'APP_ENV':'production','DEBUG':'false',
    'OIOI_SINGLE_NODE_MODE':'true','FILM_CLOUD_CONFIG':json.dumps(config),'PYTHONUNBUFFERED':'1'}
# Real API and pool subprocess output goes to private local files, never a public notebook.
shim_log=(BASE/'pool.log').open('ab')
shim=subprocess.Popen([sys.executable,str(BASE/'pool/scripts/automation/session_pool_shim.py'),'8190'],env=env,stdout=shim_log,stderr=subprocess.STDOUT)
api_log=(BASE/'api.log').open('ab')
api=subprocess.Popen([sys.executable,'-m','uvicorn','serve_film:app','--host','0.0.0.0','--port','8010'],cwd=BASE,env=env,stdout=api_log,stderr=subprocess.STDOUT)
cfl=BASE/'cloudflared'
if not cfl.exists():
    data=urllib.request.urlopen('https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64',timeout=60).read()
    cfl.write_bytes(data);cfl.chmod(0o700)
tunnel=subprocess.Popen([str(cfl),'tunnel','--url','http://127.0.0.1:8010','--no-autoupdate'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
url=None
for line in tunnel.stdout:
    match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
    if match:
        url=match.group(0);break
if not url:raise RuntimeError('cloud tunnel did not produce URL')
print('FILM_NODE',config['holder'],'MODE',config['mode'],'URL',url,flush=True)
# Drain the tunnel's pipe to avoid blocking the process on logs.
threading.Thread(target=lambda:[None for _ in tunnel.stdout],daemon=True).start()
while True:
    if api.poll() is not None:
        print('Actual API exited; diagnostics:',(BASE/'api.log').read_text(errors='replace')[-1600:],flush=True)
        raise RuntimeError('actual film API exited')
    if shim.poll() is not None:
        print('Actual pool exited; diagnostics:',(BASE/'pool.log').read_text(errors='replace')[-1200:],flush=True)
        raise RuntimeError('actual graduated pool exited')
    payload=json.dumps({'service':'oiioii-'+config['holder'],'url':url,'meta':{'holder':config['holder'],'mode':config['mode']}}).encode()
    req=urllib.request.Request(DOOR+'/v1/gateway/register?token='+config['relay_token'],data=payload,headers={'Content-Type':'application/json'})
    urllib.request.urlopen(req,timeout=30).read()
    print('FILM_NODE_ALIVE',config['holder'],flush=True)
    time.sleep(60)
