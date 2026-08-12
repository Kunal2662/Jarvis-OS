"""API Center domain models -- pure data, no I/O.

An :class:`ApiDefinition` covers both the 14 built-in templates (Gemini,
OpenAI, Claude, ...) and any custom API a user adds through the Generic
API Manager -- there is exactly one shape for both, which is what makes
"Add API" / "Edit API" work identically for built-ins and custom entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApiAuthType(str, Enum):
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    SECRET = "secret"
    OAUTH = "oauth"
    NONE = "none"


class ApiCategory(str, Enum):
    #: Stored and validated here permanently (M5/M11 boundary, Task
    #: Group A) -- credential *storage* for an LLM vendor is ordinary
    #: credential management, not AI routing, and M11's catalogue-backed
    #: Integration Platform never reads this category. See
    #: ``docs/M11_API_CENTER_ARCHITECTURE_DECISIONS.md`` §10.
    LLM = "llm"
    SEARCH = "search"
    DEVELOPER_TOOLS = "developer_tools"
    SMART_HOME = "smart_home"
    WEATHER = "weather"
    MAPPING = "mapping"
    VISION_OCR = "vision_ocr"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


class ApiHealthStatus(str, Enum):
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    AUTH_FAILED = "authentication_failed"
    NETWORK_ERROR = "network_error"
    INVALID_KEY = "invalid_key"
    DISABLED = "disabled"


@dataclass(slots=True)
class ApiDefinition:
    """One configured API -- built-in template instance or fully custom."""

    name: str
    provider: str
    category: ApiCategory
    auth_type: ApiAuthType = ApiAuthType.API_KEY
    base_url: str = ""
    api_key: str = ""
    bearer_token: str = ""
    secret: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    description: str = ""
    is_builtin: bool = False
    enabled: bool = True
    favorite: bool = False
    id: str = field(default_factory=_uuid)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    last_health: ApiHealthStatus = ApiHealthStatus.UNKNOWN
    last_response_time_ms: float | None = None


@dataclass(frozen=True, slots=True)
class ApiValidationResult:
    """Result of a (mock) health/auth check against one :class:`ApiDefinition`."""

    api_id: str
    status: ApiHealthStatus
    response_time_ms: float
    message: str = ""
    checked_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class ApiSuggestion:
    """One smart-detection suggestion shown while the user types an API name."""

    name: str
    provider: str
    category: ApiCategory
    score: float
