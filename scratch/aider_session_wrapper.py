"""Per-session wrapper that keeps the aider console window open after the task.

The launcher writes a small JSON spec (no secrets - the API key travels via
environment variables) and spawns this wrapper in a fresh console. The wrapper:
  1. runs aider with the exact argv from the spec (goal delivered via -m),
  2. prints the exit code,
  3. blocks on input() so the window NEVER vanishes on its own.

This fixes the "terminal opened and vanished" problem: even when aider exits
(which it does by design after a -m one-shot message), the window stays open
showing the full result until the user closes it.
"""
import json
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: aider_session_wrapper.py <spec.json>")
        input("Press Enter to close...")
        return 1

    spec_path = sys.argv[1]
    try:
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not read spec {spec_path}: {e}")
        input("Press Enter to close...")
        return 1

    slot = spec.get("slot", "?")
    cmd = spec["cmd"]
    cwd = spec.get("cwd")
    stdout_log = spec.get("stdout_log")  # optional: redirect stdout (codex --json)

    print(f"=== [{slot}] starting agent ===")
    print(f"    project: {cwd}")
    if stdout_log:
        print(f"    event log: {stdout_log}")
    print()

    rc = 0
    try:
        # Key/base are already in os.environ (inherited from the launcher).
        # stdin=DEVNULL is CRITICAL for aider runs: aider is launched WITHOUT
        # --yes-always (which auto-REJECTS model-suggested shell commands via
        # explicit_yes_required). With --no-fancy-input, aider's confirm_ask
        # falls back to plain input(); EOF on stdin is treated as "press
        # Enter" -> the default answer, which is "y" for every confirmation
        # aider raises (run shell command? add output? fix test errors?).
        # Result: fully unattended auto-approval of shell commands.
        # For codex runs the wrapper also captures the --json event stream,
        # but TEES it: every line goes to BOTH the console window (live view)
        # and the event log file (persistent record). Without this the
        # console shows nothing and the user thinks the agent is dead.
        if stdout_log:
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8",
                                    errors="replace")
            with open(stdout_log, "w", encoding="utf-8") as lf:
                for line in proc.stdout:
                    lf.write(line)
                    lf.flush()
                    sys.stdout.write(line)
                    sys.stdout.flush()
            rc = proc.wait()
        else:
            rc = subprocess.call(cmd, cwd=cwd, stdin=subprocess.DEVNULL)
    except KeyboardInterrupt:
        rc = 130
    except Exception as e:  # noqa: BLE001
        print(f"\nERROR launching aider: {e}")
        rc = 1

    print()
    print("=" * 60)
    print(f"[{slot}] aider finished with exit code {rc}.")
    print("Window kept open on purpose - it will NOT vanish.")
    print("=" * 60)
    try:
        input("Press Enter to close this window...")
    except Exception:  # noqa: BLE001
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
