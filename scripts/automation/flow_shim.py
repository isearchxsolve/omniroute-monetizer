"""flow_shim.py -- deprecated name for what is now video_router.py.

The engine moved to scripts/automation/video_router.py when it stopped being Flow-only: it now
rotates Google Flow AND rtst.ai accounts behind one job store and one pair of HTTP faces.

This forwarder exists because every command in worklog #1063/#1064 -- and any shortcut, service
definition or note the operator wrote from them -- names THIS path. Deleting it would break working
invocations for a rename, so the name stays and delegates. Argument parsing, env vars
(FLOW_SHIM_TOKEN and FLOW_SHIM_TRACE are still honoured by video_router) and exit codes are all the
new module's, unchanged.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import video_router  # noqa: E402


def main() -> int:
    print("!! flow_shim.py is deprecated: this is now video_router.py, which routes Google Flow "
          "AND rtst.ai. Forwarding unchanged -- prefer "
          "`python scripts/automation/video_router.py ...`.", flush=True)
    return video_router.main()


if __name__ == "__main__":
    sys.exit(main())
