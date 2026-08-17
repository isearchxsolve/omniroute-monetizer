# Run AFTER power returns: relaunch the 4-mission Codex fleet.
# All work was git-checkpointed before the power cut, so agents resume
# on top of committed state. Their FLEET_WORKLOG.md files tell them where
# they left off (goal files mandate reading existing worklog first).
python d:\omniroute-monetizer\scratch\launch_codex_fleet.py monetizer neon crypto ases
Write-Output ""
Write-Output "Fleet relaunched. Monitor with:"
Write-Output "  python d:\omniroute-monetizer\scratch\fleet_monitor.py"
