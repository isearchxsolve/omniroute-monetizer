@echo off
title OmniRoute Automation Chrome - Profile 1 (Port 9222)
echo ======================================================================
echo Launching Automation Chrome Profile 1 on Port 9222
echo Safe Directory: state/automation_profiles/profile_1
echo ======================================================================
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\profile_1" --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-position=100,60 --window-size=1280,850 "https://platform.openai.com"
pause
