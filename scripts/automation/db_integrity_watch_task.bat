@echo off
rem OmniRoute DB/WAL Integrity Watch (Fix P7) — daily 02:30. Read-only only.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\db_integrity_watch.py"
