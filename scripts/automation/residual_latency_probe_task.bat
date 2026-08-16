@echo off
rem OmniRoute Residual-Latency Probe (Fix P4) — scheduled 6-hourly.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\residual_latency_probe.py"
