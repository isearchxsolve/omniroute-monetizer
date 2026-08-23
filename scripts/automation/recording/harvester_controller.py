"""
Main entry point for the API key harvesting recording/replay system.
Provides CLI interface for recording and replaying harvesting sessions.
"""

import argparse
import sys
from pathlib import Path

from .harvester_recorder import HarvesterRecorder
from .harvester_replayer import HarvesterReplayer
from omniroute_api import log


def main():
    parser = argparse.ArgumentParser(description="API Key Harvester Recording/Replay System")
    parser.add_argument(
        "mode",
        choices=["record", "replay"],
        help="Mode: record a new session or replay an existing session"
    )
    parser.add_argument(
        "--session-id",
        help="Session ID for recording (auto-generated if not provided)"
    )
    parser.add_argument(
        "--recording-file",
        type=Path,
        help="Path to recording file (for replay mode) or directory (for record mode)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Enable validation during replay (default: True)"
    )
    parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="Disable validation during replay"
    )
    
    args = parser.parse_args()
    
    if args.mode == "record":
        return _record_mode(args)
    elif args.mode == "replay":
        return _replay_mode(args)
    
    return 0


def _record_mode(args) -> int:
    """Record a new API key harvesting session."""
    log("Starting API key harvesting recording session...")
    
    # Initialize recorder
    recorder = HarvesterRecorder(session_id=args.session_id)
    recorder.start_recording()
    
    try:
        # Import and run the actual CLI token harvester with recording instrumentation
        from ..cli_token_harvester import harvest_all, verify_upstream, inject_and_test
        from ..cli_token_harvester import HarvestedToken
        
        recorder.record_log_message("Starting token harvesting process")
        
        # Harvest tokens from all sources
        tokens = harvest_all()
        recorder.record_log_message(f"Harvested {len(tokens)} raw tokens from sources")
        
        verified_count = 0
        injected_count = 0
        
        for token in tokens:
            provider = token.provider
            recorder.record_log_message(f"Processing token from {provider}")
            
            # Verify token upstream
            recorder.record_token_verification_start(provider)
            verify_upstream(token)
            
            if token.upstream_verified:
                recorder.record_token_verified(provider, token.upstream_status or 200)
                verified_count += 1
                
                # Find matching connection and inject
                recorder.record_token_injection_start(provider, "placeholder")
                # In real implementation, we would find the actual connection ID
                connection_id = f"conn-{provider}-placeholder"  # Simplified
                
                injection_success = inject_and_test(token, connection_id)
                recorder.record_token_injection(provider, connection_id, injection_success)
                
                if injection_success:
                    recorder.record_connection_test(provider, connection_id, True)
                    injected_count += 1
                else:
                    recorder.record_connection_test(provider, connection_id, False)
            else:
                recorder.record_token_verification_failed(provider)
        
        recorder.record_log_message(
            f"Harvesting complete: {verified_count}/{len(tokens)} tokens verified, "
            f"{injected_count} tokens injected"
        )
        
    except Exception as e:
        recorder.record_error(str(e), type(e).__name__)
        log(f"Error during harvesting: {e}", "error")
        return 1
    finally:
        recorder.end_recording()
        log(f"Recording saved to: {recorder.get_recording_path()}")
    
    return 0


def _replay_mode(args) -> int:
    """Replay an existing API key harvesting session."""
    if not args.recording_file:
        log("Error: --recording-file required for replay mode", "error")
        return 1
    
    if not args.recording_file.exists():
        log(f"Error: Recording file not found: {args.recording_file}", "error")
        return 1
    
    log(f"Starting replay of recording: {args.recording_file}")
    
    # Initialize replayer
    replayer = HarvesterReplayer(args.recording_file)
    
    # Execute replay
    success = replayer.replay(validate_each_step=args.validate)
    
    if success:
        log("Replay completed successfully")
        return 0
    else:
        log("Replay completed with errors", "warn")
        return 1


if __name__ == "__main__":
    sys.exit(main())