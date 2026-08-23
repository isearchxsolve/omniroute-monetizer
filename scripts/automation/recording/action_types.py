"""
Standardized action types for API key harvesting recording/replay system.
Defines the discrete, verifiable actions that make up the harvesting process.
"""

from enum import Enum


class HarvestActionType(Enum):
    """Types of actions that can be recorded and replayed in the harvesting process."""
    
    # Initialization and setup
    HARVEST_START = "harvest_start"
    HARVEST_END = "harvest_end"
    
    # Environment variable harvesting
    CHECK_ENV_VAR = "check_env_var"
    ENV_VAR_FOUND = "env_var_found"
    ENV_VAR_MISSING = "env_var_missing"
    
    # GitHub CLI harvesting
    GITHUB_CLI_AVAILABLE = "github_cli_available"
    GITHUB_CLI_UNAVAILABLE = "github_cli_unavailable"
    GITHUB_TOKEN_HARVESTED = "github_token_harvested"
    GITHUB_TOKEN_FAILED = "github_token_failed"
    
    # Qoder CLI harvesting
    QODER_CLI_AVAILABLE = "qoder_cli_available"
    QODER_CLI_UNAVAILABLE = "qoder_cli_unavailable"
    QODER_TOKEN_HARVESTED = "qoder_token_harvested"
    QODER_TOKEN_FAILED = "qoder_token_failed"
    
    # Zed Editor harvesting
    ZED_CONFIG_FOUND = "zed_config_found"
    ZED_CONFIG_MISSING = "zed_config_missing"
    ZED_TOKEN_HARVESTED = "zed_token_harvested"
    ZED_TOKEN_FAILED = "zed_token_failed"
    
    # Codex CLI harvesting
    CODEX_CONFIG_FOUND = "codex_config_found"
    CODEX_CONFIG_MISSING = "codex_config_missing"
    CODEX_TOKEN_HARVESTED = "codex_token_harvested"
    CODEX_TOKEN_FAILED = "codex_token_failed"
    
    # Verification and injection
    TOKEN_VERIFICATION_START = "token_verification_start"
    TOKEN_VERIFIED = "token_verified"
    TOKEN_VERIFICATION_FAILED = "token_verification_failed"
    TOKEN_INJECTION_START = "token_injection_start"
    TOKEN_INJECTED = "token_injected"
    TOKEN_INJECTION_FAILED = "token_injection_failed"
    CONNECTION_TEST_START = "connection_test_start"
    CONNECTION_TEST_PASSED = "connection_test_passed"
    CONNECTION_TEST_FAILED = "connection_test_failed"
    
    # Utility actions
    SLEEP = "sleep"
    LOG_MESSAGE = "log_message"
    ERROR_ENCOUNTERED = "error_encountered"


# Mapping for human-readable descriptions
ACTION_DESCRIPTIONS = {
    HarvestActionType.HARVEST_START: "Starting API key harvesting process",
    HarvestActionType.HARVEST_END: "Completed API key harvesting process",
    HarvestActionType.CHECK_ENV_VAR: "Checking environment variable for API key",
    HarvestActionType.ENV_VAR_FOUND: "Found API key in environment variable",
    HarvestActionType.ENV_VAR_MISSING: "Environment variable not set or empty",
    HarvestActionType.GITHUB_CLI_AVAILABLE: "GitHub CLI is available",
    HarvestActionType.GITHUB_CLI_UNAVAILABLE: "GitHub CLI not available",
    HarvestActionType.GITHUB_TOKEN_HARVESTED: "Successfully harvested token from GitHub CLI",
    HarvestActionType.GITHUB_TOKEN_FAILED: "Failed to harvest token from GitHub CLI",
    HarvestActionType.QODER_CLI_AVAILABLE: "Qoder CLI is available",
    HarvestActionType.QODER_CLI_UNAVAILABLE: "Qoder CLI not available",
    HarvestActionType.QODER_TOKEN_HARVESTED: "Successfully harvested token from Qoder CLI",
    HarvestActionType.QODER_TOKEN_FAILED: "Failed to harvest token from Qoder CLI",
    HarvestActionType.ZED_CONFIG_FOUND: "Zed Editor configuration file found",
    HarvestActionType.ZED_CONFIG_MISSING: "Zed Editor configuration file not found",
    HarvestActionType.ZED_TOKEN_HARVESTED: "Successfully harvested token from Zed Editor config",
    HarvestActionType.ZED_TOKEN_FAILED: "Failed to harvest token from Zed Editor config",
    HarvestActionType.CODEX_CONFIG_FOUND: "Codex CLI configuration file found",
    HarvestActionType.CODEX_CONFIG_MISSING: "Codex CLI configuration file not found",
    HarvestActionType.CODEX_TOKEN_HARVESTED: "Successfully harvested token from Codex CLI config",
    HarvestActionType.CODEX_TOKEN_FAILED: "Failed to harvest token from Codex CLI config",
    HarvestActionType.TOKEN_VERIFICATION_START: "Starting token verification against upstream provider",
    HarvestActionType.TOKEN_VERIFIED: "Token successfully verified with upstream provider (200 OK)",
    HarvestActionType.TOKEN_VERIFICATION_FAILED: "Token verification failed with upstream provider",
    HarvestActionType.TOKEN_INJECTION_START: "Starting token injection into OmniRoute connection",
    HarvestActionType.TOKEN_INJECTED: "Token successfully injected into OmniRoute connection",
    HarvestActionType.TOKEN_INJECTION_FAILED: "Failed to inject token into OmniRoute connection",
    HarvestActionType.CONNECTION_TEST_START: "Starting connection test for injected token",
    HarvestActionType.CONNECTION_TEST_PASSED: "Connection test passed for injected token",
    HarvestActionType.CONNECTION_TEST_FAILED: "Connection test failed for injected token",
    HarvestActionType.SLEEP: "Waiting for specified duration",
    HarvestActionType.LOG_MESSAGE: "Logging informational message",
    HarvestActionType.ERROR_ENCOUNTERED: "Error encountered during harvesting process"
}