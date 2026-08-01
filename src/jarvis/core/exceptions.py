"""Cross-cutting exception hierarchy.

Every exception raised inside JARVIS OS must inherit from
:class:`JarvisError` so that upper layers can catch a single base type.
"""

from __future__ import annotations


class JarvisError(Exception):
    """Base class for every JARVIS OS exception."""


# --- Configuration ----------------------------------------------------------
class ConfigError(JarvisError):
    """Raised when configuration is missing, invalid or inconsistent."""


class MissingSecretError(ConfigError):
    """Raised when a required secret is not set in the environment/keyring."""


# --- Infrastructure ---------------------------------------------------------
class InfrastructureError(JarvisError):
    """Base class for adapter-level failures."""


class LLMProviderError(InfrastructureError):
    """Any failure raised by an LLM provider adapter."""


class STTProviderError(InfrastructureError):
    """Any failure raised by a speech-to-text adapter."""


class TTSProviderError(InfrastructureError):
    """Any failure raised by a text-to-speech adapter."""


class WakeWordError(InfrastructureError):
    """Any failure raised by a wake-word detector adapter."""


class AudioDeviceError(InfrastructureError):
    """Raised when a required microphone/speaker device is unavailable."""


class VectorStoreError(InfrastructureError):
    """Any failure raised by the vector-store adapter."""


class DatabaseError(InfrastructureError):
    """Any failure raised by the SQL database adapter."""


class BrowserAutomationError(InfrastructureError):
    """Any failure raised by the browser (Playwright) adapter."""


class OSAutomationError(InfrastructureError):
    """Any failure raised by the OS-automation (pywinauto) adapter."""


class VisionProviderError(InfrastructureError):
    """Any failure raised by a vision provider adapter."""


class OCRProviderError(InfrastructureError):
    """Any failure raised by an OCR provider adapter."""


# --- Agents / services ------------------------------------------------------
class AgentError(JarvisError):
    """Base class for LangGraph agent / orchestration failures."""


class AgentTimeoutError(AgentError):
    """Raised when an agent exceeds its configured timeout."""


class AgentStepLimitExceededError(AgentError):
    """Raised when an agent run hits ``AgentSettings.max_steps`` without completing."""


class ToolExecutionError(AgentError):
    """Raised when an agent tool call fails in a way the graph cannot recover from."""


class CheckpointError(AgentError):
    """Raised when the agent's checkpoint store cannot be opened or closed."""


class InvalidStateTransitionError(JarvisError):
    """Raised by ModuleStateMachine when asked to move to a state that
    isn't reachable from the current one (see domain/app_state)."""


class ServiceError(JarvisError):
    """Base class for application-service failures."""


# --- Automation engine (Milestone 4) ----------------------------------------
class AutomationError(ServiceError):
    """Base class for AI Automation Engine failures."""


class IntentParseError(AutomationError):
    """Raised when the parser cannot extract any usable intent."""


class AutomationValidationError(AutomationError):
    """Raised when the safety validator blocks an instruction outright."""


class AutomationPermissionDeniedError(AutomationError):
    """Raised when a dangerous action is denied or not confirmed by the user."""


class ActionNotFoundError(AutomationError):
    """Raised when no registered action class handles an :class:`ActionType`."""


class ActionExecutionError(AutomationError):
    """Raised when a concrete action fails after exhausting its retries."""


class UndoNotSupportedError(AutomationError):
    """Raised when undo is requested for a non-reversible action."""


class RecipeError(AutomationError):
    """Raised for invalid or missing automation recipes."""


# --- API Center / Update Center / Developer Mode (Milestone 5) --------------
class ApiCenterError(ServiceError):
    """Base class for API Center failures."""


class ApiNotFoundError(ApiCenterError):
    """Raised when an API id/name lookup fails."""


class DuplicateApiError(ApiCenterError):
    """Raised when adding an API whose name already exists."""


class UpdateError(ServiceError):
    """Base class for Update Center / rollback failures."""


class RollbackError(UpdateError):
    """Raised when the automatic rollback pipeline itself fails."""


class DeveloperModeError(ServiceError):
    """Base class for Developer Mode gate failures."""


class DeveloperModeLockedError(DeveloperModeError):
    """Raised when a Developer Mode action is attempted without unlocking."""


class InvalidAdminPasswordError(DeveloperModeError):
    """Raised when the supplied administrator password does not match."""


# --- UI ---------------------------------------------------------------------
class UIError(JarvisError):
    """Base class for UI-level failures (theme loading, widget wiring, ...)."""


class ThemeNotFoundError(UIError):
    """Raised when a requested theme cannot be located on disk."""
