@echo off
title OmniRoute Automation Chrome - Profile 2 (Port 9223)
echo ======================================================================
echo Launching Automation Chrome Profile 2 on Port 9223
echo Safe Directory: state/automation_profiles/profile_2
echo ======================================================================
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\profile_2" --remote-debugging-port=9223 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-position=120,80 --window-size=1280,850 "https://platform.openai.com"
pause
