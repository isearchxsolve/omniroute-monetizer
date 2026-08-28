' Hidden-window wrapper for the Rig Supervisor keepalive bat (worklog #1134).
' Task Scheduler running the .bat directly with LogonType=Interactive opens a visible
' console window every 5 minutes -- the "pop" the operator sees. Running the bat through
' WshShell.Run with window style 0 (hidden) suppresses it. Same pattern as oauth_keepalive.
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """D:\omniroute-monetizer\scripts\automation\supervisor_task.bat""", 0, False
