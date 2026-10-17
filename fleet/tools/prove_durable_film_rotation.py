"""Real owner API -> graduated video pool -> durable encrypted state -> session B."""
from __future__ import annotations
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'fleet/runtime'))
from film_cloud_runtime import FilmVaultClient
from door_client import request
APP=Path(r'D:/god_ai/oioi/oioi')
OUT=ROOT/'state/durable_film_rotation_proof_20261017';OUT.mkdir(exist_ok=True)
RECEIPT=OUT/'receipt.json'
data=json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {'scope':'real Kaggle CPU sessions, real authenticated API, live graduated pool render and encrypted cloud checkpoints'}
config=json.loads(Path(r'D:/anonym/vault/oiioii-film-cloud.json').read_text())
vault=FilmVaultClient('https://omniroute-relay.omniroute-fleet-kd.workers.dev',config['storage_token'],config['encryption_key'])
controls={s:json.loads((ROOT/'state/durable_film_notebooks'/s/'control.json').read_text()) for s in ('a','b')}
owner={}
for file in (APP/'.env',APP/'backend/.env'):
    if file.exists():owner.update(dotenv_values(file))
control_headers={'x-film-control':config['storage_token']}
client=httpx.Client(timeout=300,trust_env=False)

def save():RECEIPT.write_text(json.dumps(data,indent=2),encoding='utf-8')
def get_node(side):
    for _ in range(150):
        sessions=request('/v1/gateway').get('sessions') or []
        node=next((s for s in sessions if (s.get('meta') or {}).get('holder')==controls[side]['holder']),None)
        if node:
            url=node['url']
            r=client.get(url+'/internal/status',headers=control_headers)
            if r.status_code==200:
                data['node_'+side]={'holder':controls[side]['holder'],'url':url,'mode':r.json()['mode']};save()
                print('Node',side,'ready mode',r.json()['mode'],flush=True);return url
        print('Waiting for real Kaggle node',side,flush=True);time.sleep(8)
    raise TimeoutError('Kaggle node not registered; no fabricated availability')
def auth(url):
    r=client.post(url+'/api/v1/auth/login',json={'email':owner['OIOI_OWNER_EMAIL'],'password':owner['OIOI_OWNER_INITIAL_PASSWORD']})
    assert r.status_code==200, 'actual existing owner login failed HTTP'+str(r.status_code)
    return r.json()['access_token']
def download(url,token,label):
    fid=data['film_id'];headers={'Authorization':'Bearer '+token}
    unauth=client.get(url+f'/api/v1/films/{fid}/artifact')
    assert unauth.status_code in (401,403), 'owner artifact leaked without authentication'
    r=client.get(url+f'/api/v1/films/{fid}/artifact',headers=headers)
    assert r.status_code==200 and 'video/mp4' in r.headers.get('content-type',''), 'actual artifact missing'
    path=OUT/(label+'.mp4');path.write_bytes(r.content)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size','-show_entries','stream=codec_name,width,height','-of','json',str(path)]))
    duration=float(probe['format']['duration'])
    assert abs(duration-5)<=.2, 'real delivered duration does not meet five-second request'
    row={'http_status':r.status_code,'unauthenticated_status':unauth.status_code,'bytes':len(r.content),
         'sha256':hashlib.sha256(r.content).hexdigest(),'duration_seconds':duration,'probe':probe}
    data[label]=row;save();print(label,'HTTP200',row['bytes'],'bytes duration',duration,'sha256',row['sha256'],flush=True)
    return row

a=get_node('a')
if 'owner_token' not in locals():
    tokenfile=OUT/'owner-token.txt'
    token=tokenfile.read_text() if tokenfile.exists() else auth(a)
    if not tokenfile.exists():tokenfile.write_text(token)
headers={'Authorization':'Bearer '+token}
if 'film_id' not in data:
    payload={'script':'A copper lantern glows inside a rain-wet stone arcade at dawn. A slow camera pan reveals reflections on the paving. One uninterrupted five-second moving shot.',
             'target_seconds':5,'backend':'live','live':True,'max_clips':1,'seed':int(time.time()),'style':'cinematic'}
    pending=OUT/'admission-request.json'
    if pending.exists():payload=json.loads(pending.read_text())
    else:pending.write_text(json.dumps(payload))
    r=client.post(a+'/api/v1/films/',json=payload,headers=headers)
    if r.status_code!=200:
        data['admission_failure']={'http_status':r.status_code,'content_type':r.headers.get('content-type'),'body_prefix':r.text[:250]};save();raise RuntimeError('real film admission failed; private receipt retained')
    body=r.json();assert body.get('accepted'), 'real film not admitted'
    data['film_id']=body['film']['id'];save();print('Real live film admitted',data['film_id'],flush=True)
fid=data['film_id']
for _ in range(140):
    r=client.post(a+f'/api/v1/films/{fid}/tick',params={'live':'true','max_clips':1},headers=headers)
    if r.status_code!=200:
        data['tick_failure']={'http_status':r.status_code,'content_type':r.headers.get('content-type'),'body_prefix':r.text[:250]};save();raise RuntimeError('actual live tick failed')
    status=client.get(a+f'/api/v1/films/{fid}',headers=headers);status.raise_for_status();film=status.json()
    data['film_status']=film['status'];data['cost']=film.get('cost');data['job_states']=film.get('job_states');save()
    print('Actual film status',film['status'],film.get('job_states'),flush=True)
    if film['status']=='completed':break
    if film['status'] in ('failed','assembly_error','delivery_duration_mismatch','quality_blocked_slates'):
        data['delivery_error']=film.get('last_error');save();raise RuntimeError('actual film did not satisfy quality gate')
    time.sleep(8)
else:raise TimeoutError('real film incomplete; receipt preserved without resubmission')
assert (data['cost'] or {}).get('fallback_jobs')==0,'a fallback is not graduated provider proof'
a_artifact=download(a,token,'session_a_artifact')
# Have the Worker verify bytes and the auth gate itself before publishing A.
state=vault.call('state')
assert state['checkpoint'] and state['writer']==controls['a']['holder']
vault.call('promote',{'holder':controls['a']['holder'],'url':a,'film_id':fid,'sha256':a_artifact['sha256'],
                      'bytes':a_artifact['bytes'],'owner_token':token,'version':state['version']})
data['a_checkpoint_version']=state['version'];save()
# A's last mutation checkpoint persists login, film graph, actual object and job provenance.
b=get_node('b')
r=client.post(a+'/internal/drain',headers=control_headers);assert r.status_code==200,r.status_code
data['drain_a']=r.json();save()
r=client.post(b+'/internal/activate',headers=control_headers);assert r.status_code==200,r.status_code
data['activate_b']=r.json();save()
b_artifact=download(b,token,'session_b_artifact')
assert b_artifact['sha256']==a_artifact['sha256'] and b_artifact['bytes']==a_artifact['bytes']
state=vault.call('state')
assert state['writer']==controls['b']['holder']
vault.call('promote',{'holder':controls['b']['holder'],'url':b,'film_id':fid,'sha256':b_artifact['sha256'],
                      'bytes':b_artifact['bytes'],'owner_token':token,'version':state['version']})
data['b_checkpoint_version']=state['version'];data['b_promoted']=True;save()
public='https://omniroute-relay.omniroute-fleet-kd.workers.dev/oiioii'
public_artifact=download(public,token,'permanent_route_artifact')
assert public_artifact['sha256']==a_artifact['sha256']
data['handover_download_verified']=True
# Session A must be stopped and public download rechecked before rotation is certified.
data['rotation_proven']=False;data['awaiting_stop_session_a']=True;save()
print('REAL_HANDOVER_DOWNLOAD_VERIFIED; stop old Kaggle A and rerun final permanent download check.',flush=True)
