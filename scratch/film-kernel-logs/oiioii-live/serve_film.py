import os,json
from pathlib import Path
from film_cloud_runtime import FilmVaultClient,DurableFilmHost
root=Path(__file__).resolve().parent
c=json.loads(os.environ['FILM_CLOUD_CONFIG'])
vault=FilmVaultClient(c['door'],c['storage_token'],c['encryption_key'])
app=DurableFilmHost(root/'data',c['holder'],vault,c['storage_token'],c['mode'])
