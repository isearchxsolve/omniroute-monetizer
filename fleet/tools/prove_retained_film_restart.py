"""Exercise an actual retained film through two real API processes, never a fake rotation."""
from __future__ import annotations
import hashlib,json,os,shutil,socket,sqlite3,subprocess,time,datetime
from pathlib import Path
import httpx,psutil
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[2]
APP=Path(r"D:/god_ai/oioi/oioi")
SOURCE=ROOT/"state/api_e2e_20261018"
FID="film_6a88ff76a59b469796f06d413db6ec67"
OUT=ROOT/"state"/f"retained_film_restart_{int(time.time())}"
OUT.mkdir()
config={}
for path in (APP/".env",APP/"backend/.env"):
    if path.exists():config.update({k:v for k,v in dotenv_values(path).items() if v is not None})
assert config.get("OIOI_OWNER_EMAIL") and config.get("OIOI_OWNER_INITIAL_PASSWORD"), "existing owner config required"

def backup(source,destination):
    read=sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)
    target=sqlite3.connect(destination)
    try:read.backup(target)
    finally:target.close();read.close()

(OUT/"store").mkdir()
backup(SOURCE/"store2/film_jobs.sqlite3",OUT/"store/film_jobs.sqlite3")
backup(APP/"backend/test.db",OUT/"accounts.sqlite3")
c=sqlite3.connect((OUT/"store/film_jobs.sqlite3").resolve().as_uri()+"?mode=ro",uri=True)
c.row_factory=sqlite3.Row
film=dict(c.execute("SELECT id,target_seconds,status FROM films WHERE id=?",(FID,)).fetchone())
artifact=dict(c.execute("SELECT object_key,sha256,stored_bytes FROM film_artifacts WHERE film_id=?",(FID,)).fetchone());c.close()
obj=OUT/"objects"/artifact["object_key"];obj.parent.mkdir(parents=True)
shutil.copy2(SOURCE/"objects2"/artifact["object_key"],obj)
assert hashlib.sha256(obj.read_bytes()).hexdigest()==artifact["sha256"]
with socket.socket() as s:
    s.settimeout(.5)
    assert s.connect_ex(("127.0.0.1",8111))!=0, "isolated proof port already occupied"
env={**os.environ,**config,"DATABASE_URL":"sqlite+aiosqlite:///"+(OUT/"accounts.sqlite3").as_posix(),
    "FILM_PIPELINE_STORAGE_PATH":str(OUT/"store"),"FILM_PIPELINE_OBJECT_STORE_PATH":str(OUT/"objects"),
    "FILM_PIPELINE_MIGRATE_LEGACY_ARTIFACTS":"false","DEBUG":"false","APP_ENV":"development",
    "PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"}
report={"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "scope":"actual owner-authenticated delivery across two local API processes using copies of real retained data; NOT Kaggle rotation",
    "film":film,"artifact_sha256":artifact["sha256"],"rounds":[],"kaggle_rotation_proven":False}
token=None
for round_id in (1,2):
    log=(OUT/f"api{round_id}.log").open("wb")
    proc=subprocess.Popen([str(APP/".venv/Scripts/python.exe"),"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8111","--log-level","warning"],cwd=APP/"backend",env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        with httpx.Client(base_url="http://127.0.0.1:8111",trust_env=False,timeout=15) as client:
            for _ in range(100):
                if proc.poll() is not None:raise RuntimeError("actual API exited; private diagnostics retained locally")
                try:
                    if client.get("/healthz").status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise TimeoutError("actual API not ready")
            denied=client.get(f"/api/v1/films/{FID}/artifact")
            assert denied.status_code in (401,403), "unauthenticated artifact unexpectedly accessible"
            login_status=None
            if token is None:
                login=client.post("/api/v1/auth/login",json={"email":config["OIOI_OWNER_EMAIL"],"password":config["OIOI_OWNER_INITIAL_PASSWORD"]})
                login_status=login.status_code
                assert login_status==200, "existing owner login failed"
                token=login.json()["access_token"]
            headers={"Authorization":"Bearer "+token}
            status=client.get(f"/api/v1/films/{FID}",headers=headers);status.raise_for_status()
            download=client.get(f"/api/v1/films/{FID}/artifact",headers=headers);download.raise_for_status()
            digest=hashlib.sha256(download.content).hexdigest()
            assert digest==artifact["sha256"] and len(download.content)==artifact["stored_bytes"]
            (OUT/f"download{round_id}.mp4").write_bytes(download.content)
            report["rounds"].append({"round":round_id,"unauthenticated_http_status":denied.status_code,
                "login_http_status":login_status,"reused_persisted_session":round_id==2,
                "film_status_http":status.status_code,"artifact_http":download.status_code,
                "content_type":download.headers.get("content-type"),"bytes":len(download.content),"sha256":digest})
            print("Actual API round",round_id,"artifact",download.status_code,"bytes",len(download.content),"sha256",digest,flush=True)
    finally:
        try:
            parent=psutil.Process(proc.pid)
            children=parent.children(recursive=True)
            for child in reversed(children):
                try:child.terminate()
                except psutil.NoSuchProcess:pass
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=10)
        except (psutil.NoSuchProcess,subprocess.TimeoutExpired):
            if proc.poll() is None:proc.kill();proc.wait(timeout=5)
        log.close()
    (OUT/"receipt.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
report["local_delivery_restart_verified"]=True
(OUT/"receipt.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print("ACTUAL_LOCAL_RESTART_RECEIPT",str(OUT/"receipt.json"),flush=True)
