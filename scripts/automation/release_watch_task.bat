@echo off
rem OmniRoute Release Watcher — invoked by Windows Task Scheduler every 30 min.
rem Polls npm dist-tags for omniroute >= 3.8.50 (blocker #3 SWR fix) and alerts.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scratch\watch_omniroute_release.py"
