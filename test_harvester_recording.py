#!/usr/bin/env python3
"""
Test script to demonstrate the API key harvester recording/replay system.
This script shows how to record a harvesting session and then replay it.
"""

import sys
import os

# Add the project root to path so we can import from scripts
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_recording_system():
    """Test the recording system by creating a mock recording."""
    # Import using the full path
    from scripts.automation.recording.harvester_recorder import HarvesterRecorder
    from scripts.automation.recording.action_types import HarvestActionType, ACTION_DESCRIPTIONS
    
    print("Testing API Key Harvester Recording System")
    print("=" * 50)
    
    # Create a recorder
    recorder = HarvesterRecorder("test-session-001")
    recorder.start_recording()
    
    # Record some sample actions
    recorder.record_log_message("Starting test harvest")
    recorder.record_env_var_check("OPENROUTER_API_KEY", True, "sk-or-v1-abc123...")
    recorder.record_github_cli_check(True)
    recorder.record_github_token_harvest(True, "ghp_abc123...")
    recorder.record_token_verification("github", True, 200)
    recorder.record_token_injection("github", "conn-github-001", True)
    recorder.record_connection_test("github", "conn-github-001", True)
    recorder.record_log_message("Test harvest completed")
    
    recorder.end_recording()
    
    print(f"Recording saved to: {recorder.get_recording_path()}")
    print(f"Session summary: {recorder.get_session_summary()}")
    
    # Show the recording content
    print("\nRecording content:")
    print("-" * 30)
    with open(recorder.get_recording_path(), 'r') as f:
        for line in f:
            print(line.strip())
    
    return recorder.get_recording_path()

def test_replay_system(recording_path):
    """Test the replay system by playing back a recording."""
    from scripts.automation.recording.harvester_replayer import HarvesterReplayer
    
    print("\nTesting API Key Harvester Replay System")
    print("=" * 50)
    
    # Create a replayer
    replayer = HarvesterReplayer(recording_path)
    
    # Load the recording
    if replayer.load_recording():
        print(f"Loaded recording for session: {replayer.session_id}")
        print(f"Number of actions to replay: {len(replayer.actions)}")
        
        # Show what actions will be replayed
        print("\nActions to be replayed:")
        for i, action in enumerate(replayer.actions):
            print(f"  {i+1}. {action['action_type']} - {action['action_description']}")
        
        # Actually run the replay (without validation for this test)
        print("\nExecuting replay...")
        success = replayer.replay(validate_each_step=False)  # Disable validation for test
        
        if success:
            print("Replay completed successfully")
        else:
            print("Replay completed with errors")
        
        return success
    else:
        print("Failed to load recording")
        return False

if __name__ == "__main__":
    # Test recording
    recording_file = test_recording_system()
    
    # Test replay
    print("\n" + "=" * 50)
    success = test_replay_system(recording_file)
    
    if success:
        print("\n" + "=" * 50)
        print("TEST COMPLETED SUCCESSFULLY")
        print("The recording/replay system is ready for use.")
        print("To use in practice:")
        print("  1. Record a session: python scripts/automation/recording/harvester_controller.py record")
        print("  2. Replay a session: python scripts/automation/recording/harvester_controller.py replay --recording-file <path>")
    else:
        print("\nTEST FAILED")
        sys.exit(1)