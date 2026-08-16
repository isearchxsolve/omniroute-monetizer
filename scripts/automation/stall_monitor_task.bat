@echo off
rem OmniRoute Stall Monitor — invoked by Windows Task Scheduler every 15 min.
rem Probes /v1/models for the periodic catalog-rebuild freeze (blocker #3).
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\stall_monitor.py"
