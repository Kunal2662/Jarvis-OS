"""Mock API validation (Milestone 5, section 10B).

Deliberately deterministic-ish rather than truly random, so the same API
definition tends to validate the same way across repeated clicks (nicer
demo/test experience) while still varying enough to show every status the
UI needs to render.
"""

from __future__ import annotations

import hashlib
import random

from jarvis.domain.api_center.models import (
    ApiAuthType,
    ApiDefinition,
    ApiHealthStatus,
    ApiValidationResult,
)


class MockApiValidator:
    """Simulates a health/auth check without making any real network call."""

    async def validate(self, api: ApiDefinition) -> ApiValidationResult:
        if not api.enabled:
            return ApiValidationResult(
                api_id=api.id,
                status=ApiHealthStatus.DISABLED,
                response_time_ms=0.0,
                message="API is disabled.",
            )

        rng = random.Random(int(hashlib.sha256(api.id.encode()).hexdigest(), 16) % (2**32))
        response_time_ms = round(rng.uniform(45, 650), 1)

        requires_secret = api.auth_type in (
            ApiAuthType.API_KEY,
            ApiAuthType.BEARER_TOKEN,
            ApiAuthType.SECRET,
        )
        has_secret = bool(api.api_key or api.bearer_token or api.secret)

        if requires_secret and not has_secret:
            return ApiValidationResult(
                api_id=api.id,
                status=ApiHealthStatus.INVALID_KEY,
                response_time_ms=response_time_ms,
                message="No API key/token configured.",
            )

        roll = rng.random()
        if roll < 0.78:
            status, message = ApiHealthStatus.CONNECTED, "Reachable and authenticated."
        elif roll < 0.88:
            status, message = ApiHealthStatus.AUTH_FAILED, "Credentials were rejected."
        elif roll < 0.95:
            status, message = ApiHealthStatus.NETWORK_ERROR, "Could not reach the endpoint."
        else:
            status, message = ApiHealthStatus.INVALID_KEY, "Key format looks invalid."

        return ApiValidationResult(
            api_id=api.id,
            status=status,
            response_time_ms=response_time_ms,
            message=message,
        )
