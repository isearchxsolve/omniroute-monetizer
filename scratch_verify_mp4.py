import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(r"d:\omniroute-monetizer\scripts\automation")))
import googleflow_client as gf

media_id = "3a362870-6c49-4531-b771-99ffe3e3b6e9"
dest = pathlib.Path(r"d:\omniroute-monetizer\state\proof_flow_mp4.mp4")
p = gf.download(media_id, dest=dest, port=9222)
print(f"saved: {p}")
print(f"size : {p.stat().st_size} bytes")
# verify MP4 magic bytes (ftyp)
head = p.read_bytes()[:16]
print(f"head : {head!r}")
is_mp4 = b"ftyp" in head
print(f"MP4  : {is_mp4}")
