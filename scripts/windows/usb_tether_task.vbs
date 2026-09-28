' Codex USB Tether Failover zero-popup launcher
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""D:\omniroute-monetizer\scripts\windows\usb_tethering_selfheal.ps1"" -IntervalSeconds 15", 0, False
