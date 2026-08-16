@echo off
rem OmniRoute Health Watch — invoked by Windows Task Scheduler every 15 min.
rem Single-pass provider health check; writes state\health_log.json.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\health_watch.py"
