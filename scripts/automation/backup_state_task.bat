@echo off
rem OmniRoute State Backup — invoked by Windows Task Scheduler daily.
rem Backs up storage.sqlite + repo state\ to d:\omniroute-backups\<date>.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\backup_state.py"
