@echo off
title OmniRoute Visible Automation Chrome (Port 9222)
echo ======================================================================
echo Launching VISIBLE Automation Chrome on Port 9222
echo Safe Profile: D:\omniroute-monetizer\state\automation_profiles\providers
echo ======================================================================
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\providers" --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-position=100,60 --window-size=1280,850 "https://platform.openai.com"
pause
