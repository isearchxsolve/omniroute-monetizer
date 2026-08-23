"""
Recorder for API key harvesting process that captures discrete, verifiable actions
for later replay in a Selenium-like fashion.
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .action_types import HarvestActionType, ACTION_DESCRIPTIONS


class HarvesterRecorder:
    """Records API key harvesting actions for later replay."""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.recording_dir = Path(__file__).parent.parent.parent / "state" / "harvest_recordings"
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        self.recording_file = self.recording_dir / f"harvest_{self.session_id}.jsonl"
        self.start_time = None
        self.action_count = 0
        
    def start_recording(self):
        """Mark the start of a harvesting session."""
        self.start_time = time.time()
        self._record_action(
            HarvestActionType.HARVEST_START,
            {"session_id": self.session_id, "timestamp": datetime.now().isoformat()}
        )
        
    def end_recording(self):
        """Mark the end of a harvesting session."""
        duration = time.time() - self.start_time if self.start_time else 0
        self._record_action(
            HarvestActionType.HARVEST_END,
            {
                "session_id": self.session_id,
                "duration_seconds": duration,
                "total_actions": self.action_count,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    def _record_action(self, action_type: HarvestActionType, metadata: Dict[str, Any]):
        """Record a single action to the JSONL file."""
        action_record = {
            "id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "action_type": action_type.value,
            "action_description": ACTION_DESCRIPTIONS.get(action_type, str(action_type)),
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        }
        
        with open(self.recording_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(action_record) + "\n")
            
        self.action_count += 1
        
    # Convenience methods for recording specific actions
    def record_env_var_check(self, var_name: str, found: bool, value_preview: Optional[str] = None):
        """Record an environment variable check."""
        action_type = HarvestActionType.ENV_VAR_FOUND if found else HarvestActionType.ENV_VAR_MISSING
        self._record_action(
            action_type,
            {
                "variable_name": var_name,
                "found": found,
                "value_preview": value_preview[:10] + "..." if value_preview and len(value_preview) > 10 else value_preview
            }
        )
        
    def record_github_cli_check(self, available: bool):
        """Record GitHub CLI availability check."""
        action_type = HarvestActionType.GITHUB_CLI_AVAILABLE if available else HarvestActionType.GITHUB_CLI_UNAVAILABLE
        self._record_action(action_type, {"available": available})
        
    def record_github_token_harvest(self, success: bool, token_preview: Optional[str] = None):
        """Record GitHub token harvesting attempt."""
        action_type = HarvestActionType.GITHUB_TOKEN_HARVESTED if success else HarvestActionType.GITHUB_TOKEN_FAILED
        self._record_action(
            action_type,
            {
                "success": success,
                "token_preview": token_preview[:10] + "..." if token_preview and len(token_preview) > 10 else token_preview
            }
        )
        
    def record_qoder_cli_check(self, available: bool):
        """Record Qoder CLI availability check."""
        action_type = HarvestActionType.QODER_CLI_AVAILABLE if available else HarvestActionType.QODER_CLI_UNAVAILABLE
        self._record_action(action_type, {"available": available})
        
    def record_qoder_token_harvest(self, success: bool, token_preview: Optional[str] = None):
        """Record Qoder token harvesting attempt."""
        action_type = HarvestActionType.QODER_TOKEN_HARVESTED if success else HarvestActionType.QODER_TOKEN_FAILED
        self._record_action(
            action_type,
            {
                "success": success,
                "token_preview": token_preview[:10] + "..." if token_preview and len(token_preview) > 10 else token_preview
            }
        )
        
    def record_zed_config_check(self, found: bool):
        """Record Zed Editor config check."""
        action_type = HarvestActionType.ZED_CONFIG_FOUND if found else HarvestActionType.ZED_CONFIG_MISSING
        self._record_action(action_type, {"found": found})
        
    def record_zed_token_harvest(self, success: bool, token_preview: Optional[str] = None):
        """Record Zed Editor token harvesting attempt."""
        action_type = HarvestActionType.ZED_TOKEN_HARVESTED if success else HarvestActionType.ZED_TOKEN_FAILED
        self._record_action(
            action_type,
            {
                "success": success,
                "token_preview": token_preview[:10] + "..." if token_preview and len(token_preview) > 10 else token_preview
            }
        )
        
    def record_codex_config_check(self, found: bool):
        """Record Codex CLI config check."""
        action_type = HarvestActionType.CODEX_CONFIG_FOUND if found else HarvestActionType.CODEX_CONFIG_MISSING
        self._record_action(action_type, {"found": found})
        
    def record_codex_token_harvest(self, success: bool, token_preview: Optional[str] = None):
        """Record Codex CLI token harvesting attempt."""
        action_type = HarvestActionType.CODEX_TOKEN_HARVESTED if success else HarvestActionType.CODEX_TOKEN_FAILED
        self._record_action(
            action_type,
            {
                "success": success,
                "token_preview": token_preview[:10] + "..." if token_preview and len(token_preview) > 10 else token_preview
            }
        )
        
    def record_token_verification(self, provider: str, verified: bool, status_code: Optional[int] = None):
        """Record token verification attempt."""
        action_type = HarvestActionType.TOKEN_VERIFIED if verified else HarvestActionType.TOKEN_VERIFICATION_FAILED
        self._record_action(
            action_type,
            {
                "provider": provider,
                "verified": verified,
                "status_code": status_code
            }
        )
        
    def record_token_injection(self, provider: str, connection_id: str, success: bool):
        """Record token injection attempt."""
        action_type = HarvestActionType.TOKEN_INJECTED if success else HarvestActionType.TOKEN_INJECTION_FAILED
        self._record_action(
            action_type,
            {
                "provider": provider,
                "connection_id": connection_id,
                "success": success
            }
        )
        
    def record_connection_test(self, provider: str, connection_id: str, passed: bool):
        """Record connection test."""
        action_type = HarvestActionType.CONNECTION_TEST_PASSED if passed else HarvestActionType.CONNECTION_TEST_FAILED
        self._record_action(
            action_type,
            {
                "provider": provider,
                "connection_id": connection_id,
                "passed": passed
            }
        )
        
    def record_sleep(self, seconds: float):
        """Record a sleep/wait action."""
        self._record_action(
            HarvestActionType.SLEEP,
            {"seconds": seconds}
        )
        
    def record_log_message(self, message: str, level: str = "info"):
        """Record a log message."""
        self._record_action(
            HarvestActionType.LOG_MESSAGE,
            {
                "message": message,
                "level": level
            }
        )
        
    def record_error(self, error_msg: str, error_type: str = "general"):
        """Record an encountered error."""
        self._record_action(
            HarvestActionType.ERROR_ENCOUNTERED,
            {
                "error_message": error_msg,
                "error_type": error_type
            }
        )
        
    def get_recording_path(self) -> Path:
        """Get the path to the current recording file."""
        return self.recording_file
        
    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current recording session."""
        return {
            "session_id": self.session_id,
            "recording_file": str(self.recording_file),
            "start_time": self.start_time,
            "action_count": self.action_count,
            "duration": time.time() - self.start_time if self.start_time else 0
        }