"""Read-only live fleet preflight. Never deploys, starts kernels, or prints secrets."""
import datetime,json,os,pathlib,subprocess,sys

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'state'/'fleet_preflight_20261017_curl.json'
DOOR='https://omniroute-relay.omniroute-fleet-kd.workers.dev'
TOKEN=os.environ.get('OMNIROUTE_TOKEN','GOLD24')
VAULT=pathlib.Path(r'D:\anonym\vault')
ACCOUNT_FILES={'isearchxsolve':None,'n42888':'kaggle_token_2.txt','kunaldas3104':'kaggle_token_3.txt','kdas19999':'kaggle_token_4.txt'}
SLUGS={'cloud-cell':'omniroute-cloud-cell-cpu-worker','fleet-worker':'kaggle-fleet-worker-cpu-only','oiioii-web':'oiioii-kaggle-web','emergentsh-web':'emergentsh-kaggle-web','relay-backup':'omniroute-relay','playwright':'omniroute-playwright-executor'}
result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'door':{},'kernels':[]}
def persist():OUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
def emit(obj):print(json.dumps(obj),flush=True)
def redact(obj):
 if isinstance(obj,dict):return {k:('[REDACTED]' if any(s in k.lower() for s in ('token','secret','cookie','authorization','password','recipe')) else redact(v)) for k,v in obj.items()}
 if isinstance(obj,list):return [redact(v) for v in obj]
 if isinstance(obj,str):return obj.replace(TOKEN,'[REDACTED]')
 return obj
for label,path in [('health','/health'),('gateway','/v1/gateway'),('capture-status','/v1/captures/status?capture_id=github.auto_zen.v1')]:
 url=DOOR+path+('&' if '?' in path else '?')+'token='+TOKEN
 try:
  # The rig's documented curl/urllib difference also applies to the Worker.
  # A normal curl client is used; no browser impersonation or security change.
  config='url = '+json.dumps(url)+'\n'
  proc=subprocess.run(['curl.exe','--silent','--show-error','--max-time','20','--write-out','\n%{http_code}','--config','-'],input=config,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
  body,_,code=proc.stdout.rpartition('\n')
  try:data=json.loads(body)
  except ValueError:data=body[:300]
  row={'http':int(code) if code.isdigit() else None,'returncode':proc.returncode,'data':redact(data),'transport':'curl.exe'}
 except Exception as exc:row={'error_type':type(exc).__name__}
 result['door'][label]=row;persist();emit({label:row})
if '--door-only' in sys.argv:
 emit({'receipt':str(OUT)})
 sys.exit(0)
state=json.loads(pathlib.Path(r'C:\kaggle\working\rotation_state.json').read_text(encoding='utf-8'))
for name,slug in SLUGS.items():
 owner=state.get(name,{}).get('current')
 if owner not in ACCOUNT_FILES:
  row={'name':name,'owner':owner,'error':'unrecognized_owner'}
 else:
  env=dict(os.environ)
  for key in ('KAGGLE_USERNAME','KAGGLE_KEY','KAGGLE_API_TOKEN'):env.pop(key,None)
  file=ACCOUNT_FILES[owner]
  token=(VAULT/file).read_text().strip() if file else None
  if token:env['KAGGLE_API_TOKEN']=token
  try:
   proc=subprocess.run(['kaggle','kernels','status',owner+'/'+slug],capture_output=True,text=True,encoding='utf-8',errors='replace',env=env,timeout=35)
   text=(proc.stdout+' '+proc.stderr).strip()
   if token:text=text.replace(token,'[REDACTED]')
   row={'name':name,'owner':owner,'slug':slug,'returncode':proc.returncode,'output':text[:1000]}
  except subprocess.TimeoutExpired:row={'name':name,'owner':owner,'slug':slug,'error':'status_timeout_35s'}
 result['kernels'].append(row);persist();emit(row)
emit({'receipt':str(OUT)})
