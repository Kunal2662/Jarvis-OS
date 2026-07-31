"""Unit tests for :class:`ApiCenterService` -- Milestone 5, section 10B."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.core.exceptions import ApiCenterError, ApiNotFoundError, DuplicateApiError
from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition
from jarvis.services.api_center_service import ApiCenterService


@pytest.fixture()
def service(tmp_path: Path) -> ApiCenterService:
    settings = Settings(data_dir=tmp_path)
    return ApiCenterService(settings)


def test_seeds_all_fourteen_builtin_templates(service: ApiCenterService) -> None:
    apis = service.list_apis()
    assert len(apis) == 14
    names = {a.name for a in apis}
    assert "Google Gemini" in names
    assert "Tesseract OCR" in names


def test_add_custom_api(service: ApiCenterService) -> None:
    custom = ApiDefinition(
        name="My Custom API",
        provider="Acme",
        category=ApiCategory.CUSTOM,
        auth_type=ApiAuthType.API_KEY,
        base_url="https://api.acme.test",
        api_key="secret123",
    )
    service.add_api(custom)
    fetched = service.get(custom.id)
    assert fetched.name == "My Custom API"
    assert fetched.api_key == "secret123"


def test_add_duplicate_name_raises(service: ApiCenterService) -> None:
    with pytest.raises(DuplicateApiError):
        service.add_api(ApiDefinition(name="OpenAI", provider="x", category=ApiCategory.CUSTOM))


def test_delete_builtin_raises(service: ApiCenterService) -> None:
    openai = next(a for a in service.list_apis() if a.name == "OpenAI")
    with pytest.raises(ApiCenterError):
        service.delete_api(openai.id)


def test_delete_custom_api(service: ApiCenterService) -> None:
    custom = service.add_api(
        ApiDefinition(name="Temp API", provider="x", category=ApiCategory.CUSTOM)
    )
    service.delete_api(custom.id)
    with pytest.raises(ApiNotFoundError):
        service.get(custom.id)


def test_enable_disable_and_favorite(service: ApiCenterService) -> None:
    api = service.list_apis()[0]
    service.set_enabled(api.id, False)
    assert service.get(api.id).enabled is False
    service.set_favorite(api.id, True)
    assert service.get(api.id).favorite is True


def test_secrets_are_encrypted_at_rest(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    from cryptography.fernet import Fernet

    settings.security.secret_key = __import__("pydantic").SecretStr(Fernet.generate_key().decode())
    service = ApiCenterService(settings)
    custom = service.add_api(
        ApiDefinition(
            name="Secret API",
            provider="x",
            category=ApiCategory.CUSTOM,
            api_key="super-secret-value",
        )
    )
    raw = service._store_path.read_text(encoding="utf-8")
    assert "super-secret-value" not in raw

    # A fresh service instance (simulating app restart) must decrypt correctly.
    reloaded = ApiCenterService(settings)
    assert reloaded.get(custom.id).api_key == "super-secret-value"


@pytest.mark.asyncio
async def test_validate_updates_last_health(service: ApiCenterService) -> None:
    api = service.list_apis()[0]
    result = await service.validate(api.id)
    assert service.get(api.id).last_health == result.status


def test_export_and_import_roundtrip(service: ApiCenterService, tmp_path: Path) -> None:
    export_path = tmp_path / "export.json"
    service.export_all(export_path)
    assert export_path.exists()

    other_settings = Settings(data_dir=tmp_path / "other")
    other_service = ApiCenterService(other_settings)
    imported = other_service.import_from(export_path)
    assert imported == 14


def test_mark_used_tracks_recents(service: ApiCenterService) -> None:
    api = service.list_apis()[0]
    service.mark_used(api.id)
    suggestions = service.suggest("")
    assert suggestions[0].name == api.name
