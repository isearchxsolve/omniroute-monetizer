"""Package actual app, admitted seats and retained state into encrypted deployment."""
from __future__ import annotations
import ast,io,json,re,shutil,sqlite3,subprocess,sys,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=Path(r'D:/god_ai/oioi/oioi')
sys.path.insert(0,str(ROOT/'fleet/runtime'))
from film_cloud_runtime import FilmVaultClient
vault_config=json.loads(Path(r'D:/anonym/vault/oiioii-film-cloud.json').read_text())
DOOR='https://omniroute-relay.omniroute-fleet-kd.workers.dev'
client=FilmVaultClient(DOOR,vault_config['storage_token'],vault_config['encryption_key'])
stage=ROOT/'state/durable_film_deployment_20261017';stage.mkdir(exist_ok=True)
source=ROOT/'scripts/automation'
paths=subprocess.check_output(['git','ls-files','backend','frontend'],cwd=APP).decode().splitlines()
for name in paths:
    file=APP/name
    if not file.is_file() or any(x in Path(name).parts for x in ('tests','__pycache__','node_modules','storage','.venv')):continue
    if file.suffix in ('.db','.sqlite3','.mp4','.mp3','.png','.jpg','.jpeg','.wav','.zip') or file.name.startswith('.env'):continue
    dest=stage/'app'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
pending=['session_pool_shim'];seen=set()
while pending:
    name=pending.pop()
    if name in seen or not (source/(name+'.py')).is_file():continue
    seen.add(name);raw=(source/(name+'.py')).read_text(encoding='utf-8-sig')
    for node in ast.walk(ast.parse(raw)):
        if isinstance(node,ast.Import):pending.extend(a.name.split('.')[0] for a in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module:pending.append(node.module.split('.')[0])
    if re.search(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{25,})',raw):raise RuntimeError('embedded credential in code module '+name)
    dest=stage/'pool/scripts/automation'/(name+'.py');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(raw,encoding='utf-8')
for name in ('ltx_space_video_client','gradio_space_client','video_seat_health'):
    dest=stage/'pool/scripts/automation'/(name+'.py');shutil.copy2(source/(name+'.py'),dest)
seats=['session_ltx_space_public.json','session_digen_ai.json','session_rtst_ai_seat2.json','session_labs_google_flow_p2.json',
       'session_labs_google_flow_seat1.json','session_groq_chat.json','session_cohere_coral_web.json']
secret_root=stage/'pool/state/secrets';secret_root.mkdir(parents=True,exist_ok=True)
for name in seats:shutil.copy2(ROOT/'state/secrets'/name,secret_root/name)
tenants=json.loads((ROOT/'state/secrets/tenant_map.json').read_text(encoding='utf-8-sig'))
consumer_key=next(iter(tenants))
(secret_root/'tenant_map.json').write_text(json.dumps({consumer_key:tenants[consumer_key]}),encoding='utf-8')
for name in ('pure_python_replay_registry.json','replay_check.json','pool_quarantine.json'):
    if (ROOT/'state'/name).exists():shutil.copy2(ROOT/'state'/name,stage/'pool/state'/name)
(stage/'private-config.json').write_text(json.dumps({'consumer_key':consumer_key}),encoding='utf-8')
def backup(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    a=sqlite3.connect(src.resolve().as_uri()+'?mode=ro',uri=True);b=sqlite3.connect(dst)
    try:a.backup(b)
    finally:a.close();b.close()
backup(APP/'backend/test.db',stage/'data/accounts.sqlite3')
backup(ROOT/'state/api_e2e_20261018/store2/film_jobs.sqlite3',stage/'data/film/film_jobs.sqlite3')
shutil.copytree(ROOT/'state/api_e2e_20261018/objects2',stage/'data/objects',dirs_exist_ok=True)
shutil.copy2(ROOT/'fleet/runtime/film_cloud_runtime.py',stage/'film_cloud_runtime.py')
(stage/'serve_film.py').write_text("""import os,json
from pathlib import Path
from film_cloud_runtime import FilmVaultClient,DurableFilmHost
root=Path(__file__).resolve().parent
c=json.loads(os.environ['FILM_CLOUD_CONFIG'])
vault=FilmVaultClient(c['door'],c['storage_token'],c['encryption_key'])
app=DurableFilmHost(root/'data',c['holder'],vault,c['storage_token'],c['mode'])
""",encoding='utf-8')
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as tar:
    for file in stage.rglob('*'):
        if file.is_file():tar.add(file,arcname=str(file.relative_to(stage)),recursive=False)
manifest=client.upload(client.encrypt(stream.getvalue()))
client.call('deployment',{'manifest':manifest})
report={'source_app_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=APP).decode().strip(),
        'pool_code_modules':len(seen),'admitted_seat_files':len(seats),'encrypted_bytes':manifest['bytes'],'ciphertext_sha256':manifest['sha256']}
(ROOT/'state/durable_film_deployment_receipt_20261017.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
from door_client import TOKEN
for side,mode in [('a','active'),('b','standby')]:
    folder=ROOT/'state/durable_film_notebooks'/side;folder.mkdir(parents=True,exist_ok=True)
    holder='film-'+side+'-'+str(int(time.time()))
    config={**vault_config,'door':DOOR,'relay_token':TOKEN,'holder':holder,'mode':mode}
    code='FILM_CONFIG = '+repr(config)+chr(10)+(ROOT/'fleet/kernels/film_host_bootstrap.py').read_text(encoding='utf-8')
    compile(code,'private-film-bootstrap','exec')
    nb={'nbformat':4,'nbformat_minor':4,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'accelerator':'none'},
        'cells':[{'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':code}]}
    (folder/'film.ipynb').write_text(json.dumps(nb),encoding='utf-8')
    slug='oiioii-kaggle-web' if side=='a' else 'oiioii-kaggle-rotation-b'
    metadata={'id':'isearchxsolve/'+slug,'title':'OiiOii durable film '+side.upper(),'code_file':'film.ipynb','language':'python','kernel_type':'notebook',
              'is_private':True,'enable_gpu':False,'enable_internet':True,'dataset_sources':[],'competition_sources':[],'kernel_sources':[],'model_sources':[]}
    (folder/'kernel-metadata.json').write_text(json.dumps(metadata),encoding='utf-8')
    (folder/'control.json').write_text(json.dumps({'holder':holder,'slug':metadata['id'],'mode':mode}),encoding='utf-8')
print('Private CPU notebook artifacts prepared; no secrets printed.')
