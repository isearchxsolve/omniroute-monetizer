# Laptop health check under heavy load

Checked 6 September 2026 around 13:02–13:05 IST.

## Findings and mitigation

- Task Manager screenshot: CPU 95%, memory 78%, disk 2%. The two Bun-labelled applications are Kilo CLI executables, not unrelated unknown Bun processes.
- Live five-second process sample: Kilo PID 15580 used 31.7% CPU and PID 12108 used 13.9%, about 46% combined. Both were Normal priority. Their parent processes are Node, and they began at 11:18 and 10:54 respectively. This establishes CPU competition; it does not establish a Kilo software defect.
- Changed only these two verified Kilo processes from Normal to BelowNormal priority. Both remained running and responding, and the new priority was independently verified. This gives normal-priority interactive work preference under contention; it does not cap CPU use or prove reduced heat. Coding jobs can take longer. The change lasts for these process lifetimes. To undo, select the corresponding Kilo process in Task Manager Details and set priority to Normal; verify its identity because process IDs can be reused.
- Subsequent three CPU samples: 100%, 89%, 80%. Workload varies, so these are not proof that the priority change caused a reduction. CPU load remains high.
- Available RAM approximately 3.2–3.3 GB; committed memory 57% at the earlier sample. Pages input/sec samples 18.3, 6.7, 65.2, with disk queue zero throughout. No sustained disk bottleneck established in this short check.
- C: free 35,702,304,768 bytes (33.25 GiB); D: free 66,528,264,192 bytes (61.96 GiB). No cleanup needed for current free space.
- Intel SSD reported OK. This is a basic Windows status, not a full SMART or remaining-life assessment.
- Balanced power plan active. Battery status indicated AC power, charge 100%. Charge percentage does not reverse the prior measured battery wear.
- Initial thermal query returned Access denied. After the operator authorized UAC, the elevated read-only query succeeded at 13:07: ACPI zone THM0_0 reported 59.1 degrees Celsius. This is not necessarily the hottest CPU core. Fan performance and absence of throttling remain unverified. Script: scripts/check_laptop_thermal_elevated.ps1. Raw result: state/thermal_check_2026_09_06.json.

## Overnight power interruption

Windows booted at 09:22 on 6 September. Kernel-Power 41 and EventLog 6008 recorded an unclean prior shutdown, with bugcheck code zero. The operator confirmed that mains power failed overnight while asleep. Record this as operator-confirmed power interruption, not evidence of a processor crash. The previous battery assessment showed heavily reduced capacity; it cannot be relied upon to bridge an overnight outage.

The recent System error sample also contained VirtualBox network-filter events (VBoxNetLwf, ID 12). Their root cause was not investigated in this CPU-focused check; no adapter/filter was disabled.

## Practical operating plan

Keep the cooler and vents unobstructed and use stable AC power. Save and sync work frequently. For sustained responsiveness on this two-core laptop, run one heavy coding job at a time where practical; allow an active job to finish before starting another. The current jobs were preserved. Nothing was terminated, suspended, restarted, uninstalled, or changed in Chrome, services, security software, or power configuration.

Priority semantics verified against Microsoft's documentation: https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/setpriority-method-in-class-win32-process
