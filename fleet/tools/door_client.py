"""Bounded authenticated requests to the user's existing Worker, without secret logging."""
import json,os,subprocess,urllib.parse
DOOR=os.environ.get('OMNIROUTE_DOOR','https://omniroute-relay.omniroute-fleet-kd.workers.dev')
TOKEN=os.environ.get('OMNIROUTE_TOKEN','GOLD24')

def request(path, data=None, params=None):
    query=urllib.parse.urlencode({**(params or {}),'token':TOKEN})
    config='url = '+json.dumps(DOOR+path+'?'+query)+'\n'
    if data is not None:
        config+='request = "POST"\nheader = "content-type: application/json"\ndata = '+json.dumps(json.dumps(data))+'\n'
    result=subprocess.run(['curl.exe' if os.name=='nt' else 'curl','-sS','--max-time','25','--config','-'],input=config,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    if result.returncode:raise RuntimeError('door_transport_failed_'+str(result.returncode))
    return json.loads(result.stdout)
