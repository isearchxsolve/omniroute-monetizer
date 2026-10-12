@echo off
title OmniRoute Automation Chrome - Profile 4 (Port 9225)
echo ======================================================================
echo Launching Automation Chrome Profile 4 on Port 9225
echo Safe Directory: state/automation_profiles/profile_4
echo ======================================================================
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\profile_4" --remote-debugging-port=9225 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-position=160,120 --window-size=1280,850 "https://platform.openai.com"
pause
