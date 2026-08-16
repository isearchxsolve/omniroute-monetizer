@echo off
rem OmniRoute OAuth Keep-Alive — invoked by Windows Task Scheduler every 15 min.
rem Runs one refresh pass over all active OAuth connections via the native
rem POST /api/providers/{id}/refresh endpoint (anti-pattern #1 + #6 compliant).
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\oauth_keepalive.py" --once
