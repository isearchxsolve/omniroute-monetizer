### [2026-08-25 14:50] #1072 — SHUTDOWN SEATS & PREPARE VIDEO REPLAY HARNESS
**Status:** SUCCESS
**Context:** The operator noticed the Chrome background seats were consuming excessive CPU and Memory (~2GB each). The operator requested to shut down the seats and the keepalive service, prepare the code for the Video Harness (veoaifree style), and then perform the session grabs one by one to avoid resource exhaustion.

**Actions Taken:**
1. **Disabled Keepalive Service:** Executed `schtasks /Change /TN "OmniRoute Video Router (keepalive)" /Disable` to prevent the scheduled task from automatically relaunching Chrome.
2. **Killed Chrome Instances:** Executed `taskkill /F /IM chrome.exe /T` to aggressively free memory from the Session 0 background seats.
3. **Prepared Video Harness (`video_universal_replay.py`):** 
   - Wrote a new `UniversalVideoClient` adapter in `scripts/automation/video_universal_replay.py`.
   - Mimicked the "dirty and easy" string replacement style from `universal_replay.py` (which powers the VeoAIFree chat).
   - The script can load any `session_<host>.json`, identify the sentinel video prompt (e.g., "A cinematic 4k highly detailed video of a red fox running through snow"), inject the new prompt, and submit the POST request.

**Next Steps:**
- Launch the Chrome seats one-by-one.
- Execute the sweep and grab procedure on each seat individually (via `sweep_grab.py` or `auto_generate_agent.py`) to harvest `state/secrets/session_<host>.json`.
- Close the seat.
- Test the harvested sessions using the new `video_universal_replay.py` harness.
