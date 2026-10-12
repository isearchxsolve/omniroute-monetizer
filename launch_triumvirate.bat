@echo off
echo ======================================================================
echo Launching OmniRoute Triumvirate Persistent Autonomous Services
echo ======================================================================

:: 1. Launch OmniRoute Session Pool Shim (:8190)
start "OmniRoute-Shim-8190" /min cmd /c "cd /d D:\omniroute-monetizer && D:\omniroute-monetizer\.venv\Scripts\python.exe scripts\automation\session_pool_shim.py"

:: 2. Launch OiiOii Film Kit Studio (:8010)
start "OiiOii-Studio-8010" /min cmd /c "cd /d D:\god_ai\oioi\oioi\backend && D:\god_ai\oioi\oioi\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010"

:: 3. Launch Emergent SH NeonBuild (:8000)
start "EmergentSH-8000" /min cmd /c "cd /d D:\god_ai\emergentsh-standalone-clean && set DATABASE_URL=sqlite+aiosqlite:///./emergentsh-local.db&& set OMNIROUTE_BASE_URL=http://127.0.0.1:8190/v1&& set OMNIROUTE_API_KEY=sk-omni-mKb4KPg6b6LPlHrhtfyO2ppoBqQ1ciGQ&& set INFERENCE_PROVIDER=omniroute&& set PYTHONPATH=src;backend;.&& python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"

echo All services launched in independent persistent background processes.
