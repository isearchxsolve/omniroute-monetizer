Set shell = CreateObject("WScript.Shell")
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""D:\omniroute-monetizer\scripts\windows\battery_ac_guard.ps1"""
shell.Run command, 0, False
