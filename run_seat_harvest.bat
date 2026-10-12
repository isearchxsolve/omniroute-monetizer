@echo off
title OmniRoute 100-Provider Seat Harvest Cycler
cd /d D:\omniroute-monetizer
echo ======================================================================
echo OmniRoute 100-Provider 1-by-1 Tab Graduation ^& Replay Cycler
echo Safe isolated profile: state/automation_profiles/providers
echo ======================================================================
D:\omniroute-monetizer\.venv\Scripts\python.exe D:\omniroute-monetizer\scripts\automation\seat_harvest_cycler.py
echo ======================================================================
echo Cycler execution finished.
echo ======================================================================
pause
