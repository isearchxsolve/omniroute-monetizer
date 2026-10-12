@echo off
title OmniRoute Automation Chrome - Profile 3 (Port 9224)
echo ======================================================================
echo Launching Automation Chrome Profile 3 on Port 9224
echo Safe Directory: state/automation_profiles/profile_3
echo ======================================================================
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\profile_3" --remote-debugging-port=9224 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-position=140,100 --window-size=1280,850 "https://platform.openai.com"
pause
