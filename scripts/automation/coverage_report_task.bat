@echo off
rem OmniRoute Provider Coverage Classifier — daily 04:00.
rem Classifies all catalog providers (VERIFIED / SUPPRESSED / HARVESTABLE /
rem ACCOUNT_REQUIRED) and writes the human-blocked worklist.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\coverage_report.py" --apply
