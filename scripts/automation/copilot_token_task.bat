@echo off

rem OmniRoute Copilot Bearer keepalive -- invoked by Windows Task Scheduler every 6 hours.

rem Refreshes the auth0 Bearer (24h server-side expiry) from the durable refresh_token in
rem state/secrets/copilot_auth0.json BEFORE it expires, and persists the rotated refresh
rem token. Status: state/copilot_token_status.json. Log: logs/copilot_token.log.

cd /d D:\omniroute-monetizer

"D:\omniroute-monetizer\.venv\Scripts\python.exe" "D:\omniroute-monetizer\scripts\automation\copilot_token_keepalive.py" >> "D:\omniroute-monetizer\logs\copilot_token.log" 2>&1
