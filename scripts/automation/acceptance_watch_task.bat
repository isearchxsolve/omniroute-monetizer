@echo off
rem OmniRoute Acceptance Watch — invoked by Windows Task Scheduler every 6 hours.
rem Runs acceptance_tests.py; writes state\acceptance_latest.md + history.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\acceptance_watch.py"
