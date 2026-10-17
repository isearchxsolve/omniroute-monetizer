"""Real public GET jobs through the live door; saves authentic fleet receipts."""
import base64,datetime,hashlib,json,os,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'state'/'live_execution_proof_20261017.json'
DOOR='https://omniroute-relay.omniroute-fleet-kd.workers.dev'
TOKEN=os.environ.get('OMNIROUTE_TOKEN','GOLD24')
def call(path,data=None):
 url=DOOR+path+('&' if '?' in path else '?')+'token='+TOKEN
 config='url = '+json.dumps(url)+'\n'
 cmd=['curl.exe','-sS','--max-time','25','--config','-']
 if data is not None:
  config+='request = "POST"\nheader = "content-type: application/json"\ndata = '+json.dumps(json.dumps(data))+'\n'
 p=subprocess.run(cmd,input=config,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
 if p.returncode:raise RuntimeError('curl transport failure '+str(p.returncode))
 return json.loads(p.stdout)
result={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jobs':[]}
def save():OUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
for mode,target in [('fleet','https://api.github.com/zen'),('playwright','https://example.com/')]:
 submitted=call('/v1/tools/web.execute',{'url':target,'method':'GET','mode':mode,'timeout_s':25})
 row={'mode':mode,'target':target,'submission':submitted}
 result['jobs'].append(row);save()
 print(json.dumps({'mode':mode,'submission':submitted}),flush=True)
 if not submitted.get('job_id') or submitted.get('stored') is False:raise RuntimeError('Submission not durably stored')
deadline=time.monotonic()+300
while time.monotonic()<deadline:
 pending=False
 for row in result['jobs']:
  if row.get('complete'):continue
  response=call('/v1/tools/web.result?job_id='+row['submission']['job_id'])
  row['response']=response
  status=response.get('status')
  if status in ('done','failed'):
   row['complete']=True
   raw=base64.b64decode(response.get('content_b64',''))
   row['body_sha256']=hashlib.sha256(raw).hexdigest()
   row['body_preview']=raw.decode('utf-8',errors='replace')[:1200]
   row['verified']=status=='done' and response.get('http_status')==200 and response.get('executed_by')==('kaggle:playwright' if row['mode']=='playwright' else 'kaggle:cloud-cell') and bool(raw)
  else:pending=True
  save()
  print(json.dumps({'mode':row['mode'],'status':status,'http':response.get('http_status'),'executed_by':response.get('executed_by'),'verified':row.get('verified')}),flush=True)
 if not pending:break
 time.sleep(15)
result['all_verified']=all(r.get('verified') for r in result['jobs']);save()
print(json.dumps({'all_verified':result['all_verified'],'receipt':str(OUT)}),flush=True)
raise SystemExit(0 if result['all_verified'] else 2)
