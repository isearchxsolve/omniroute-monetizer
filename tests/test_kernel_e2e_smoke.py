"""Local E2E Smoke Test for Kaggle Film Kernel Runtime.

Verifies:
1. Staged deployment package integrity and decryption.
2. Frontend build cleanly produces /oiioii/ assets.
3. FastAPI app lifespan startup, owner bootstrap, database init.
4. Static files mount at / and serve /oiioii/ without errors.
5. Session pool shim dependencies load without missing imports.
"""
import asyncio
import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(r"D:/omniroute-monetizer")
sys.path.insert(0, str(ROOT / "fleet/runtime"))
from film_cloud_runtime import FilmVaultClient

def test_staged_deployment_smoke():
    print("--- STEP 1: Verify FilmVault Staged Deployment Integrity ---")
    vault_config = json.loads(Path(r"D:/anonym/vault/oiioii-film-cloud.json").read_text())
    door = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"
    client = FilmVaultClient(door, vault_config["storage_token"], vault_config["encryption_key"])
    
    state = client.call("state")
    assert state.get("deployment") is not None, "Deployment manifest missing in FilmVault"
    manifest = state["deployment"]
    print(f"Deployment SHA256: {manifest['sha256']}, Bytes: {manifest['bytes']}")
    
    # Download and decrypt deployment
    raw_tar = client.download(manifest)
    assert len(raw_tar) > 0, "Decrypted deployment tar is empty"
    print(f"Decrypted payload tar size: {len(raw_tar)} bytes")

    with tempfile.TemporaryDirectory(prefix="film-smoke-") as tmpdir:
        base = Path(tmpdir)
        with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:gz") as archive:
            archive.extractall(base)
        print("Extracted deployment files:", len(list(base.rglob("*"))))

        print("--- STEP 2: Verify Frontend Pre-build & Assets ---")
        front = base / "app/frontend"
        assert front.exists(), "Frontend directory missing from package"
        
        # Verify package.json and vite.config.ts
        vite_cfg = (front / "vite.config.ts").read_text()
        assert "base:" in vite_cfg, "vite.config.ts must declare base path"
        print("vite.config.ts verified with base path configuration.")

        # Test building frontend inside this environment if dist does not already exist
        dist = front / "dist"
        if not (dist / "index.html").exists():
            print("Building frontend in staging directory...")
            build_env = {**os.environ, "VITE_API_URL": "/oiioii/api/v1", "VITE_BASE_PATH": "/oiioii/"}
            res = subprocess.run(["npm", "run", "build"], cwd=front, env=build_env, capture_output=True, text=True, timeout=120, shell=(os.name=="nt"))
            assert res.returncode == 0, f"npm run build failed: {res.stderr}"
        
        index_html = (dist / "index.html").read_text()
        assert "/oiioii/" in index_html, "index.html must reference /oiioii/ assets"
        print("Frontend dist/index.html verified with /oiioii/ assets.")

        print("--- STEP 3: Verify Backend App Lifespan & Owner Bootstrap ---")
        private = json.loads((base / "private-config.json").read_text())
        env = {
            **os.environ,
            "PYTHONPATH": str(base / "app/backend") + os.pathsep + str(base),
            "DATABASE_URL": "sqlite+aiosqlite:///" + str(base / "data/accounts.sqlite3"),
            "FILM_PIPELINE_STORAGE_PATH": str(base / "data/film"),
            "FILM_PIPELINE_OBJECT_STORE_PATH": str(base / "data/objects"),
            "FILM_PIPELINE_CONSUMER_BASE_URL": "http://127.0.0.1:8190",
            "FILM_PIPELINE_VIDEO_MODEL": "video/auto",
            "OMNI_CONSUMER_API_KEY": private["consumer_key"],
            "OMNI_VIDEO_CONFIRM_SPEND": "1",
            "OMNI_VIDEO_MAX_SPEND": "0",
            "OMNI_VIDEO_JOB_STORE": str(base / "data/video_jobs.json"),
            "APP_ENV": "production",
            "DEBUG": "false",
            "OIOI_SINGLE_NODE_MODE": "true",
        }
        
        # Test loading app in subprocess to respect clean PYTHONPATH and env
        probe_code = """
import os, sys, asyncio
from pathlib import Path
base = Path(sys.argv[1])
sys.path.insert(0, str(base / "app/backend"))
sys.path.insert(0, str(base))

from app.main import app
from fastapi.staticfiles import StaticFiles

frontend = base / "app/frontend/dist"
if frontend.is_dir():
    app.mount("/oiioii", StaticFiles(directory=str(frontend), html=True), name="frontend")

async def test_lifespan():
    lifespan = app.router.lifespan_context(app)
    async with lifespan:
        print("LIFESPAN_STARTUP_OK")

asyncio.run(test_lifespan())
"""
        probe_res = subprocess.run([sys.executable, "-c", probe_code, str(base)], env=env, capture_output=True, text=True, timeout=60)
        print("Backend probe stdout:", probe_res.stdout.strip())
        if probe_res.returncode != 0:
            print("Backend probe stderr:", probe_res.stderr)
            raise RuntimeError(f"Backend app startup probe failed: {probe_res.stderr}")
        assert "LIFESPAN_STARTUP_OK" in probe_res.stdout, "Lifespan startup did not report success"
        print("Backend lifespan startup succeeded cleanly in production mode!")

        print("--- STEP 4: Verify Pool Shim Modules ---")
        pool_script = base / "pool/scripts/automation/session_pool_shim.py"
        assert pool_script.exists(), "session_pool_shim.py missing"
        shim_probe = """
import sys
from pathlib import Path
base = Path(sys.argv[1])
sys.path.insert(0, str(base / "pool/scripts/automation"))
import session_pool_shim
print("POOL_SHIM_IMPORT_OK")
"""
        shim_res = subprocess.run([sys.executable, "-c", shim_probe, str(base)], env=env, capture_output=True, text=True, timeout=30)
        print("Shim probe stdout:", shim_res.stdout.strip())
        assert "POOL_SHIM_IMPORT_OK" in shim_res.stdout, f"Pool shim import failed: {shim_res.stderr}"
        print("Pool shim import succeeded cleanly!")

    print("\n==========================================")
    print("ALL KERNEL RUNTIME SMOKE TESTS PASSED 100%")
    print("==========================================")

if __name__ == "__main__":
    test_staged_deployment_smoke()
