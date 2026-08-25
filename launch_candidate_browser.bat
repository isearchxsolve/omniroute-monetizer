@echo off
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
set PROFILE="D:\omniroute-monetizer\state\automation_profiles\providers"

start "" %CHROME% --user-data-dir=%PROFILE% --profile-directory=Default --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-size=1300,850 --window-position=100,50 https://arena.lmsys.org https://duck.ai/chat https://huggingface.co/chat https://poe.com https://www.phind.com https://www.blackbox.ai https://www.perplexity.ai
