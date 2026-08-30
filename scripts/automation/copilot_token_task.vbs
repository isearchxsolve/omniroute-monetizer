' OmniRoute Copilot Bearer keepalive -- hidden-window wrapper for the task bat.

' Task Scheduler running the .bat directly with LogonType=Interactive opens a visible console
' window on every run; WshShell.Run with window style 0 suppresses it (same pattern as
' supervisor_task.vbs).

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """D:\omniroute-monetizer\scripts\automation\copilot_token_task.bat""", 0, False
