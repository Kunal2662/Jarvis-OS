"""API Center service -- CRUD + smart suggestion + mock validation.

Persists to ``<data_dir>/config/api_center.json``. Secret fields
(``api_key``, ``bearer_token``, ``secret``, ``oauth_client_secret``) are
encrypted at rest with the app's Fernet key (see
:mod:`jarvis.utils.crypto`) whenever a real key is configured, so the JSON
file on disk never holds plaintext credentials.

**M5 / M11 boundary (Task Group A).** This service is the permanent,
sole owner of *generic and uncatalogued* API credentials -- every
:class:`~jarvis.domain.api_center.models.ApiCategory`, including
``LLM`` (Gemini/OpenAI/Claude keys stored here as ordinary
:class:`~jarvis.domain.api_center.models.ApiDefinition` rows). It is not
merged into, migrated to, or superseded by M11's catalogue-backed
Integration Platform (:mod:`jarvis.core.integrations`,
:class:`~jarvis.services.integration_service.IntegrationService`), which
owns only vendors with a hand-written
:class:`~jarvis.core.integrations.models.IntegrationSpec` (Google
Workspace today). Nothing in that engine reads, writes, or migrates an
``ApiDefinition``, and nothing here reads, writes, or migrates a
``Credential``. See ``docs/M11_API_CENTER_ARCHITECTURE_DECISIONS.md``
§2 and §10 for the approved boundary and its AI-provider-credential
carve-out.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.core.config import paths as _paths
from jarvis.core.exceptions import ApiCenterError, ApiNotFoundError, DuplicateApiError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.api_center.models import (
    ApiAuthType,
    ApiCategory,
    ApiDefinition,
    ApiHealthStatus,
    ApiSuggestion,
    ApiValidationResult,
)
from jarvis.features.api_center.registry import builtin_templates
from jarvis.features.api_center.suggester import ApiSuggester, SuggestionContext
from jarvis.features.api_center.validator import MockApiValidator
from jarvis.utils.crypto import decrypt, encrypt

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

_logger = get_logger("jarvis.services.api_center")

_SECRET_FIELDS = ("api_key", "bearer_token", "secret", "oauth_client_secret")
_MAX_RECENTS = 10


class ApiCenterService:
    def __init__(
        self,
        settings: Settings,
        *,
        suggester: ApiSuggester | None = None,
        validator: MockApiValidator | None = None,
    ) -> None:
        self._settings = settings
        self._suggester = suggester or ApiSuggester()
        self._validator = validator or MockApiValidator()
        self._store_path = _paths.config_dir(settings.resolved_data_dir) / "api_center.json"
        self._apis: dict[str, ApiDefinition] = {}
        self._recent_ids: list[str] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._store_path.exists():
            for template in builtin_templates():
                self._apis[template.id] = template
            self._save()
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as err:
            raise ApiCenterError(f"Cannot read API Center store: {err}") from err

        self._recent_ids = list(raw.get("recent_ids", []))
        for row in raw.get("apis", []):
            api = self._row_to_api(row)
            self._apis[api.id] = api

    def _save(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "recent_ids": self._recent_ids[-_MAX_RECENTS:],
            "apis": [self._api_to_row(a) for a in self._apis.values()],
        }
        self._store_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _fernet_key(self) -> str | None:
        key = self._settings.security.secret_key.get_secret_value()
        return key if key and key != "CHANGE_ME_TO_A_FERNET_KEY" else None

    def _api_to_row(self, api: ApiDefinition) -> dict:
        row = asdict(api)
        row["category"] = api.category.value
        row["auth_type"] = api.auth_type.value
        row["last_health"] = api.last_health.value
        fernet_key = self._fernet_key()
        if fernet_key:
            for field_name in _SECRET_FIELDS:
                value = row.get(field_name) or ""
                row[field_name] = encrypt(fernet_key, value) if value else ""
        return row

    def _row_to_api(self, row: dict) -> ApiDefinition:
        row = dict(row)
        fernet_key = self._fernet_key()
        if fernet_key:
            for field_name in _SECRET_FIELDS:
                value = row.get(field_name) or ""
                if value:
                    try:
                        row[field_name] = decrypt(fernet_key, value)
                    except Exception:
                        row[field_name] = ""
        row["category"] = ApiCategory(row["category"])
        row["auth_type"] = ApiAuthType(row["auth_type"])
        row["last_health"] = ApiHealthStatus(row.get("last_health", "unknown"))
        for dt_field in ("created_at", "updated_at", "last_used_at"):
            if row.get(dt_field):
                row[dt_field] = datetime.fromisoformat(row[dt_field])
        return ApiDefinition(**row)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list_apis(self, *, category: ApiCategory | None = None) -> list[ApiDefinition]:
        self._ensure_loaded()
        apis = list(self._apis.values())
        if category is not None:
            apis = [a for a in apis if a.category is category]
        return sorted(apis, key=lambda a: (not a.favorite, a.name.lower()))

    def list_connected(self) -> list[ApiDefinition]:
        return [
            a for a in self.list_apis() if a.enabled and a.last_health == ApiHealthStatus.CONNECTED
        ]

    def list_installed(self) -> list[ApiDefinition]:
        return self.list_apis()

    def get(self, api_id: str) -> ApiDefinition:
        self._ensure_loaded()
        try:
            return self._apis[api_id]
        except KeyError as err:
            raise ApiNotFoundError(f"No API with id {api_id!r}.") from err

    def add_api(self, api: ApiDefinition) -> ApiDefinition:
        self._ensure_loaded()
        if any(a.name.lower() == api.name.lower() for a in self._apis.values()):
            raise DuplicateApiError(f"An API named {api.name!r} already exists.")
        self._apis[api.id] = api
        self._save()
        _logger.info("Added API {} ({}).", api.name, api.provider)
        return api

    def update_api(self, api_id: str, **changes) -> ApiDefinition:
        self._ensure_loaded()
        current = self.get(api_id)
        updated = replace(current, **changes, updated_at=datetime.now(UTC))
        self._apis[api_id] = updated
        self._save()
        return updated

    def delete_api(self, api_id: str) -> None:
        self._ensure_loaded()
        api = self.get(api_id)
        if api.is_builtin:
            raise ApiCenterError("Built-in API templates cannot be deleted, only disabled.")
        del self._apis[api_id]
        self._save()

    def set_enabled(self, api_id: str, enabled: bool) -> ApiDefinition:
        return self.update_api(api_id, enabled=enabled)

    def set_favorite(self, api_id: str, favorite: bool) -> ApiDefinition:
        return self.update_api(api_id, favorite=favorite)

    def mark_used(self, api_id: str) -> None:
        self._ensure_loaded()
        self.get(api_id)  # raises if missing
        self._recent_ids = [i for i in self._recent_ids if i != api_id] + [api_id]
        self.update_api(api_id, last_used_at=datetime.now(UTC))

    # ------------------------------------------------------------------
    # Import / export
    # ------------------------------------------------------------------
    def export_all(self, output_path: Path) -> Path:
        self._ensure_loaded()
        payload = {
            "recent_ids": self._recent_ids,
            "apis": [self._api_to_row(a) for a in self._apis.values()],
        }
        output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return output_path

    def import_from(self, input_path: Path) -> int:
        self._ensure_loaded()
        raw = json.loads(input_path.read_text(encoding="utf-8"))
        count = 0
        for row in raw.get("apis", []):
            api = self._row_to_api(row)
            if api.id in self._apis:
                api.id = api.id + "-imported"
            self._apis[api.id] = api
            count += 1
        self._save()
        return count

    # ------------------------------------------------------------------
    # Smart detection + validation
    # ------------------------------------------------------------------
    def suggest(self, query: str, *, limit: int = 8) -> list[ApiSuggestion]:
        self._ensure_loaded()
        favorites = tuple(a.name for a in self._apis.values() if a.favorite)
        recent_names = tuple(
            self._apis[i].name for i in reversed(self._recent_ids) if i in self._apis
        )
        context = SuggestionContext(recent_names=recent_names, favorite_names=favorites)
        return self._suggester.suggest(
            query, list(self._apis.values()), context=context, limit=limit
        )

    async def validate(self, api_id: str) -> ApiValidationResult:
        api = self.get(api_id)
        result = await self._validator.validate(api)
        self.update_api(
            api_id, last_health=result.status, last_response_time_ms=result.response_time_ms
        )
        return result

    async def validate_all(self) -> list[ApiValidationResult]:
        self._ensure_loaded()
        return [await self.validate(a.id) for a in self._apis.values()]
