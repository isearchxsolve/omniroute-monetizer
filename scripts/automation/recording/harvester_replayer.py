"""
Replayer for API key harvesting process that executes recorded actions
with validation in a Selenium-like fashion.
"""

import json
import time
import subprocess
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .action_types import HarvestActionType
from omniroute_api import OmniRouteAPI, log, mask_token


class HarvesterReplayer:
    """Replays recorded API key harvesting actions with validation."""
    
    def __init__(self, recording_file: Path):
        self.recording_file = recording_file
        self.api = OmniRouteAPI()
        self.session_id = None
        self.start_time = None
        self.actions: List[Dict[str, Any]] = []
        self.action_index = 0
        self.verification_cache = {}  # Cache verification results to avoid duplicate upstream calls
        
    def load_recording(self) -> bool:
        """Load the recorded actions from JSONL file."""
        try:
            with open(self.recording_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.actions.append(json.loads(line))
            
            # Extract session ID from first action
            if self.actions:
                self.session_id = self.actions[0].get("session_id")
                
            # Sort actions by timestamp to ensure proper order
            self.actions.sort(key=lambda x: x.get("timestamp", ""))
            
            log(f"Loaded {len(self.actions)} actions from recording session {self.session_id}")
            return True
        except Exception as e:
            log(f"Failed to load recording: {e}", "error")
            return False
    
    def replay(self, validate_each_step: bool = True) -> bool:
        """Replay the recorded harvesting process."""
        if not self.load_recording():
            return False
            
        self.start_time = time.time()
        log(f"Starting replay of harvest session {self.session_id}")
        
        # Record the start of replay in worklog
        self._worklog_entry(
            "REPLAY_START",
            f"Starting replay of API key harvesting session {self.session_id}",
            {"actions_to_replay": len(self.actions)}
        )
        
        success = True
        for i, action_record in enumerate(self.actions):
            self.action_index = i
            action_type = HarvestActionType(action_record["action_type"])
            
            try:
                # Execute the action with validation
                action_success = self._execute_action(action_record, validate_each_step)
                
                if not action_success:
                    log(f"Action {i+1}/{len(self.actions)} failed: {action_record['action_type']}", "error")
                    success = False
                    # Decide whether to continue or fail fast based on action criticality
                    if self._is_critical_action(action_type):
                        break
                else:
                    log(f"Action {i+1}/{len(self.actions)} completed: {action_record['action_type']}")
                    
            except Exception as e:
                log(f"Exception during action {i+1}/{len(self.actions)}: {e}", "error")
                success = False
                if self._is_critical_action(action_type):
                    break
        
        # Record the end of replay in worklog
        duration = time.time() - self.start_time
        self._worklog_entry(
            "REPLAY_END",
            f"Completed replay of API key harvesting session {self.session_id}",
            {
                "success": success,
                "duration_seconds": duration,
                "actions_processed": self.action_index + 1,
                "total_actions": len(self.actions)
            }
        )
        
        return success
    
    def _execute_action(self, action_record: Dict[str, Any], validate: bool) -> bool:
        """Execute a single recorded action with validation."""
        action_type = HarvestActionType(action_record["action_type"])
        metadata = action_record.get("metadata", {})
        
        # Pre-condition validation (if enabled)
        if validate:
            if not self._validate_preconditions(action_type, metadata):
                log(f"Precondition failed for action {action_type.value}", "warn")
                return False
        
        # Execute the action
        start_time = time.time()
        try:
            result = self._perform_action(action_type, metadata)
            execution_time = time.time() - start_time
            
            # Post-condition validation (if enabled)
            if validate and result is not None:
                if not self._validate_postconditions(action_type, metadata, result):
                    log(f"Postcondition failed for action {action_type.value}", "warn")
                    return False
            
            # Log to worklog
            self._worklog_entry(
                f"ACTION_{action_type.value}",
                f"Executed {action_type.value}",
                {
                    "action_index": self.action_index,
                    "execution_time_seconds": execution_time,
                    "result": result
                }
            )
            
            return result if result is not None else True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self._worklog_entry(
                f"ACTION_{action_type.value}_FAILED",
                f"Failed to execute {action_type.value}",
                {
                    "action_index": self.action_index,
                    "execution_time_seconds": execution_time,
                    "error": str(e)
                }
            )
            raise
    
    def _perform_action(self, action_type: HarvestActionType, metadata: Dict[str, Any]) -> Any:
        """Perform the actual action based on type."""
        if action_type == HarvestActionType.HARVEST_START:
            return self._harvest_start(metadata)
        elif action_type == HarvestActionType.HARVEST_END:
            return self._harvest_end(metadata)
        elif action_type == HarvestActionType.CHECK_ENV_VAR:
            return self._check_env_var(metadata)
        elif action_type == HarvestActionType.ENV_VAR_FOUND:
            return self._env_var_found(metadata)
        elif action_type == HarvestActionType.ENV_VAR_MISSING:
            return self._env_var_missing(metadata)
        elif action_type == HarvestActionType.GITHUB_CLI_AVAILABLE:
            return self._github_cli_available(metadata)
        elif action_type == HarvestActionType.GITHUB_CLI_UNAVAILABLE:
            return self._github_cli_unavailable(metadata)
        elif action_type == HarvestActionType.GITHUB_TOKEN_HARVESTED:
            return self._github_token_harvested(metadata)
        elif action_type == HarvestActionType.GITHUB_TOKEN_FAILED:
            return self._github_token_failed(metadata)
        elif action_type == HarvestActionType.QODER_CLI_AVAILABLE:
            return self._qoder_cli_available(metadata)
        elif action_type == HarvestActionType.QODER_CLI_UNAVAILABLE:
            return self._qoder_cli_unavailable(metadata)
        elif action_type == HarvestActionType.QODER_TOKEN_HARVESTED:
            return self._qoder_token_harvested(metadata)
        elif action_type == HarvestActionType.QODER_TOKEN_FAILED:
            return self._qoder_token_failed(metadata)
        elif action_type == HarvestActionType.ZED_CONFIG_FOUND:
            return self._zed_config_found(metadata)
        elif action_type == HarvestActionType.ZED_CONFIG_MISSING:
            return self._zed_config_missing(metadata)
        elif action_type == HarvestActionType.ZED_TOKEN_HARVESTED:
            return self._zed_token_harvested(metadata)
        elif action_type == HarvestActionType.ZED_TOKEN_FAILED:
            return self._zed_token_failed(metadata)
        elif action_type == HarvestActionType.CODEX_CONFIG_FOUND:
            return self._codex_config_found(metadata)
        elif action_type == HarvestActionType.CODEX_CONFIG_MISSING:
            return self._codex_config_missing(metadata)
        elif action_type == HarvestActionType.CODEX_TOKEN_HARVESTED:
            return self._codex_token_harvested(metadata)
        elif action_type == HarvestActionType.CODEX_TOKEN_FAILED:
            return self._codex_token_failed(metadata)
        elif action_type == HarvestActionType.TOKEN_VERIFICATION_START:
            return self._token_verification_start(metadata)
        elif action_type == HarvestActionType.TOKEN_VERIFIED:
            return self._token_verified(metadata)
        elif action_type == HarvestActionType.TOKEN_VERIFICATION_FAILED:
            return self._token_verification_failed(metadata)
        elif action_type == HarvestActionType.TOKEN_INJECTION_START:
            return self._token_injection_start(metadata)
        elif action_type == HarvestActionType.TOKEN_INJECTED:
            return self._token_injected(metadata)
        elif action_type == HarvestActionType.TOKEN_INJECTION_FAILED:
            return self._token_injection_failed(metadata)
        elif action_type == HarvestActionType.CONNECTION_TEST_START:
            return self._connection_test_start(metadata)
        elif action_type == HarvestActionType.CONNECTION_TEST_PASSED:
            return self._connection_test_passed(metadata)
        elif action_type == HarvestActionType.CONNECTION_TEST_FAILED:
            return self._connection_test_failed(metadata)
        elif action_type == HarvestActionType.SLEEP:
            return self._sleep(metadata)
        elif action_type == HarvestActionType.LOG_MESSAGE:
            return self._log_message(metadata)
        elif action_type == HarvestActionType.ERROR_ENCOUNTERED:
            return self._error_encountered(metadata)
        else:
            log(f"Unknown action type: {action_type}", "warn")
            return True
    
    # Action implementations
    def _harvest_start(self, metadata: Dict[str, Any]) -> bool:
        """Handle harvest start action."""
        self.session_id = metadata.get("session_id")
        log(f"Harvest session started: {self.session_id}")
        return True
    
    def _harvest_end(self, metadata: Dict[str, Any]) -> bool:
        """Handle harvest end action."""
        duration = metadata.get("duration_seconds", 0)
        log(f"Harvest session ended: {self.session_id} (duration: {duration:.2f}s)")
        return True
    
    def _check_env_var(self, metadata: Dict[str, Any]) -> bool:
        """Check if environment variable exists."""
        var_name = metadata.get("variable_name")
        value = os.environ.get(var_name, "")
        found = bool(value and value.strip())
        
        # Cache the value for later use if found
        if found:
            self._env_var_cache = getattr(self, '_env_var_cache', {})
            self._env_var_cache[var_name] = value
            
        return found  # Return whether var was found (matches recording)
    
    def _env_var_found(self, metadata: Dict[str, Any]) -> bool:
        """Handle environment variable found action."""
        var_name = metadata.get("variable_name")
        value = getattr(self, '_env_var_cache', {}).get(var_name, "")
        log(f"Environment variable {var_name} found: {mask_token(value)}")
        return True
    
    def _env_var_missing(self, metadata: Dict[str, Any]) -> bool:
        """Handle environment variable missing action."""
        var_name = metadata.get("variable_name")
        log(f"Environment variable {var_name} not found or empty")
        return True
    
    def _github_cli_available(self, metadata: Dict[str, Any]) -> bool:
        """Check if GitHub CLI is available."""
        try:
            result = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _github_cli_unavailable(self, metadata: Dict[str, Any]) -> bool:
        """Handle GitHub CLI unavailable action."""
        return not self._github_cli_available({})
    
    def _github_token_harvested(self, metadata: Dict[str, Any]) -> bool:
        """Handle GitHub token harvested action."""
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                token = result.stdout.strip()
                if token:
                    # Cache for verification step
                    self._github_token = token
                    log(f"GitHub token harvested: {mask_token(token)}")
                    return True
            log("Failed to harvest GitHub token", "warn")
            return False
        except Exception as e:
            log(f"Exception harvesting GitHub token: {e}", "error")
            return False
    
    def _github_token_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle GitHub token failed action."""
        return not self._github_token_harvested({})
    
    def _qoder_cli_available(self, metadata: Dict[str, Any]) -> bool:
        """Check if Qoder CLI is available."""
        qoder_path = r"C:\Users\Admin\.qoder\bin\qodercli"
        return os.path.exists(qoder_path)
    
    def _qoder_cli_unavailable(self, metadata: Dict[str, Any]) -> bool:
        """Handle Qoder CLI unavailable action."""
        return not self._qoder_cli_available({})
    
    def _qoder_token_harvested(self, metadata: Dict[str, Any]) -> bool:
        """Handle Qoder token harvested action."""
        try:
            qoder_path = r"C:\Users\Admin\.qoder\bin\qodercli"
            if os.path.exists(qoder_path):
                result = subprocess.run([qoder_path, "auth", "token"], 
                                      capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    token = result.stdout.strip()
                    if token:
                        self._qoder_token = token
                        log(f"Qoder token harvested: {mask_token(token)}")
                        return True
            log("Failed to harvest Qoder token", "warn")
            return False
        except Exception as e:
            log(f"Exception harvesting Qoder token: {e}", "error")
            return False
    
    def _qoder_token_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle Qoder token failed action."""
        return not self._qoder_token_harvested({})
    
    def _zed_config_found(self, metadata: Dict[str, Any]) -> bool:
        """Handle Zed Editor config found action."""
        zed_path = os.path.expandvars(r"%APPDATA%\Zed\settings.json")
        found = os.path.exists(zed_path)
        if found:
            try:
                with open(zed_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Extract token if present
                    if "api_key" in config or "token" in config:
                        self._zed_token = config.get("api_key") or config.get("token")
                        log(f"Zed Editor token found in config: {mask_token(self._zed_token)}")
            except Exception as e:
                log(f"Error reading Zed config: {e}", "warn")
        return found
    
    def _zed_config_missing(self, metadata: Dict[str, Any]) -> bool:
        """Handle Zed Editor config missing action."""
        return not self._zed_config_found({})
    
    def _zed_token_harvested(self, metadata: Dict[str, Any]) -> bool:
        """Handle Zed Editor token harvested action."""
        return hasattr(self, '_zed_token') and bool(self._zed_token)
    
    def _zed_token_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle Zed Editor token failed action."""
        return not self._zed_token_harvested({})
    
    def _codex_config_found(self, metadata: Dict[str, Any]) -> bool:
        """Handle Codex CLI config found action."""
        codex_path = os.path.expanduser("~\\.codex\\config.json")
        found = os.path.exists(codex_path)
        if found:
            try:
                with open(codex_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Extract token if present
                    if "token" in config:
                        self._codex_token = config["token"]
                        log(f"Codex CLI token found in config: {mask_token(self._codex_token)}")
            except Exception as e:
                log(f"Error reading Codex config: {e}", "warn")
        return found
    
    def _codex_config_missing(self, metadata: Dict[str, Any]) -> bool:
        """Handle Codex CLI config missing action."""
        return not self._codex_config_found({})
    
    def _codex_token_harvested(self, metadata: Dict[str, Any]) -> bool:
        """Handle Codex CLI token harvested action."""
        return hasattr(self, '_codex_token') and bool(self._codex_token)
    
    def _codex_token_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle Codex CLI token failed action."""
        return not self._codex_token_harvested({})
    
    def _token_verification_start(self, metadata: Dict[str, Any]) -> bool:
        """Handle token verification start action."""
        provider = metadata.get("provider")
        log(f"Starting token verification for provider: {provider}")
        return True
    
    def _token_verified(self, metadata: Dict[str, Any]) -> bool:
        """Handle token verified action."""
        provider = metadata.get("provider")
        status_code = metadata.get("status_code")
        
        # Use cached verification if available
        cache_key = f"{provider}_{metadata.get('token_preview', '')}"
        if cache_key in self.verification_cache:
            verified = self.verification_cache[cache_key]
        else:
            # Perform actual verification
            token = self._get_cached_token(provider)
            if token:
                verified = self._verify_token_with_provider(provider, token)
                self.verification_cache[cache_key] = verified
            else:
                verified = False
        
        log(f"Token verification for {provider}: {'PASSED' if verified else 'FAILED'} (status: {status_code})")
        return verified
    
    def _token_verification_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle token verification failed action."""
        provider = metadata.get("provider")
        log(f"Token verification failed for provider: {provider}", "warn")
        return not self._token_verified(metadata)
    
    def _token_injection_start(self, metadata: Dict[str, Any]) -> bool:
        """Handle token injection start action."""
        provider = metadata.get("provider")
        connection_id = metadata.get("connection_id")
        log(f"Starting token injection for {provider} (connection: {connection_id})")
        return True
    
    def _token_injected(self, metadata: Dict[str, Any]) -> bool:
        """Handle token injected action."""
        provider = metadata.get("provider")
        connection_id = metadata.get("connection_id")
        success = metadata.get("success", False)
        
        if success:
            # Perform actual injection
            token = self._get_cached_token(provider)
            if token:
                injection_success = self._inject_token_to_connection(provider, connection_id, token)
                log(f"Token injection for {provider}: {'SUCCESS' if injection_success else 'FAILED'}")
                return injection_success
            else:
                log(f"No token available for {provider} injection", "error")
                return False
        else:
            log(f"Token injection for {provider} was marked as failed in recording")
            return False
    
    def _token_injection_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle token injection failed action."""
        return not self._token_injected(metadata)
    
    def _connection_test_start(self, metadata: Dict[str, Any]) -> bool:
        """Handle connection test start action."""
        provider = metadata.get("provider")
        connection_id = metadata.get("connection_id")
        log(f"Starting connection test for {provider} (connection: {connection_id})")
        return True
    
    def _connection_test_passed(self, metadata: Dict[str, Any]) -> bool:
        """Handle connection test passed action."""
        provider = metadata.get("provider")
        connection_id = metadata.get("connection_id")
        passed = metadata.get("passed", False)
        
        if passed:
            # Perform actual connection test
            test_success = self._test_connection(provider, connection_id)
            log(f"Connection test for {provider}: {'PASSED' if test_success else 'FAILED'}")
            return test_success
        else:
            log(f"Connection test for {provider} was marked as failed in recording")
            return False
    
    def _connection_test_failed(self, metadata: Dict[str, Any]) -> bool:
        """Handle connection test failed action."""
        return not self._connection_test_passed(metadata)
    
    def _sleep(self, metadata: Dict[str, Any]) -> bool:
        """Handle sleep action."""
        seconds = metadata.get("seconds", 1)
        log(f"Sleeping for {seconds} seconds")
        time.sleep(seconds)
        return True
    
    def _log_message(self, metadata: Dict[str, Any]) -> bool:
        """Handle log message action."""
        message = metadata.get("message", "")
        level = metadata.get("level", "info")
        log(f"[{level.upper()}] {message}")
        return True
    
    def _error_encountered(self, metadata: Dict[str, Any]) -> bool:
        """Handle error encountered action."""
        error_msg = metadata.get("error_message", "Unknown error")
        error_type = metadata.get("error_type", "general")
        log(f"Error encountered ({error_type}): {error_msg}", "error")
        return True  # Recording of error doesn't mean replay should fail
    
    # Helper methods
    def _get_cached_token(self, provider: str) -> Optional[str]:
        """Get cached token for a provider."""
        token_attrs = {
            "github": "_github_token",
            "qoder": "_qoder_token", 
            "zed": "_zed_token",
            "codex": "_codex_token"
        }
        
        attr_name = token_attrs.get(provider)
        if attr_name and hasattr(self, attr_name):
            return getattr(self, attr_name)
        
        # Check environment variables
        env_var_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY"
        }
        
        env_var = env_var_map.get(provider)
        if env_var:
            return os.environ.get(env_var)
        
        return None
    
    def _verify_token_with_provider(self, provider: str, token: str) -> bool:
        """Verify token with provider's upstream endpoint."""
        # Check cache first
        cache_key = f"verify_{provider}_{hash(token) % 10000}"
        if cache_key in self.verification_cache:
            return self.verification_cache[cache_key]
        
        try:
            # Use OmniRouteAPI to test the token against provider's upstream
            # This is a simplified version - in reality would call provider's actual API
            test_result = self.api.test_provider_connection(provider, token)
            verified = test_result.get("status") == "success"
            self.verification_cache[cache_key] = verified
            return verified
        except Exception as e:
            log(f"Error verifying token with {provider}: {e}", "warn")
            self.verification_cache[cache_key] = False
            return False
    
    def _inject_token_to_connection(self, provider: str, connection_id: str, token: str) -> bool:
        """Inject token into OmniRoute connection."""
        try:
            # Update the provider's API key in OmniRoute
            update_result = self.api.update_provider_apikey(connection_id, token)
            if update_result.get("status") == "success":
                # Test the connection after injection
                test_result = self.api.test_provider_connection(connection_id)
                return test_result.get("status") == "success"
            return False
        except Exception as e:
            log(f"Error injecting token to {provider} connection: {e}", "error")
            return False
    
    def _test_connection(self, provider: str, connection_id: str) -> bool:
        """Test the connection for a provider."""
        try:
            test_result = self.api.test_provider_connection(connection_id)
            return test_result.get("status") == "success"
        except Exception as e:
            log(f"Error testing {provider} connection: {e}", "warn")
            return False
    
    def _validate_preconditions(self, action_type: HarvestActionType, metadata: Dict[str, Any]) -> bool:
        """Validate preconditions for an action."""
        # Most actions don't have strict preconditions, but we can add specific ones
        if action_type in [HarvestActionType.GITHUB_TOKEN_HARVESTED, HarvestActionType.QODER_TOKEN_HARVESTED,
                          HarvestActionType.ZED_TOKEN_HARVESTED, HarvestActionType.CODEX_TOKEN_HARVESTED]:
            # For token harvesting, we should check that the source is available
            source_checks = {
                HarvestActionType.GITHUB_TOKEN_HARVESTED: self._github_cli_available,
                HarvestActionType.QODER_TOKEN_HARVESTED: self._qoder_cli_available,
                HarvestActionType.ZED_TOKEN_HARVESTED: self._zed_config_found,
                HarvestActionType.CODEX_TOKEN_HARVESTED: self._codex_config_found
            }
            
            check_func = source_checks.get(action_type)
            if check_func:
                return check_func({})
        
        elif action_type in [HarvestActionType.TOKEN_VERIFIED, HarvestActionType.TOKEN_INJECTED,
                          HarvestActionType.CONNECTION_TEST_PASSED]:
            # For verification/injection/testing, we should have a token
            provider = metadata.get("provider")
            if provider:
                token = self._get_cached_token(provider)
                return bool(token and token.strip())
        
        return True  # Default to allowing action
    
    def _validate_postconditions(self, action_type: HarvestActionType, metadata: Dict[str, Any], result: Any) -> bool:
        """Validate postconditions for an action."""
        # Most actions validate through their return value, but we can add specific checks
        expected_success = metadata.get("success", True) if "success" in metadata else None
        
        if expected_success is not None:
            # Action expects a specific success/failure outcome
            return bool(result) == expected_success
        
        return True  # Default to allowing any result
    
    def _is_critical_action(self, action_type: HarvestActionType) -> bool:
        """Determine if an action is critical (should stop replay on failure)."""
        critical_actions = {
            HarvestActionType.HARVEST_START,
            HarvestActionType.HARVEST_END,
            HarvestActionType.GITHUB_CLI_AVAILABLE,
            HarvestActionType.QODER_CLI_AVAILABLE,
            HarvestActionType.ZED_CONFIG_FOUND,
            HarvestActionType.CODEX_CONFIG_FOUND,
            HarvestActionType.TOKEN_VERIFIED,
            HarvestActionType.TOKEN_INJECTED,
            HarvestActionType.CONNECTION_TEST_PASSED
        }
        return action_type in critical_actions
    
    def _worklog_entry(self, action_type: str, description: str, metadata: Dict[str, Any] = None):
        """Create a worklog entry following AGENTS.md requirements."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        worklog_path = Path(__file__).parent.parent.parent / "MASTER_WORKLOG.md"
        
        entry = f"\n### [{timestamp}] #REPLAY-{self.action_index+1} — {action_type}\n"
        entry += f"- **Action**: {description}\n"
        
        if metadata:
            entry += f"- **Details**: {json.dumps(metadata, indent=2)}\n"
        
        # Append to worklog
        with open(worklog_path, "a", encoding="utf-8") as f:
            f.write(entry)