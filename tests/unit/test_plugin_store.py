"""Unit tests for ``jarvis.core.plugins.store`` (Milestone 9 Task Group
D, Phase 7)."""

from __future__ import annotations

import json
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.plugins.loader import PluginLoader
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.core.plugins.registry import PluginRegistry, PluginState
from jarvis.core.plugins.sandbox import PluginSandbox
from jarvis.core.plugins.store import (
    PluginStore,
    PluginStoreError,
    UnsignedAllowedVerifier,
    compute_package_digest,
)

_GOOD_PLUGIN_PY = """
class HelloPlugin:
    async def on_load(self, context) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass
"""


class _FakePlatformAdapter:
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            family=PlatformFamily.WINDOWS,
            os_release="test",
            architecture="x86_64",
            python_version="3.13.0",
        )

    def has_capability(self, capability: str) -> bool:
        return False

    def resolve_entry_point(self, entry_point, *, default_key="default"):
        return entry_point if isinstance(entry_point, str) else entry_point.get(default_key)


def _write_package(root, plugin_id, *, name=None):
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name or plugin_id,
        "display_name": plugin_id.title(),
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(_GOOD_PLUGIN_PY, encoding="utf-8")
    return plugin_dir


def _zip_dir(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w") as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
    return zip_path


class _Harness:
    def __init__(self, tmp_path, *, allow_unsigned=True, signature_verifier=None):
        self.tmp_path = tmp_path
        self.plugins_dir = tmp_path / "plugins"
        self.plugins_dir.mkdir()
        event_bus = EventBus()
        loader = PluginLoader(
            self.plugins_dir, platform_adapter=_FakePlatformAdapter(), app_version="0.10.0"
        )
        permission_model = PermissionModel(event_bus, store_path=tmp_path / "permissions.json")
        self.registry = PluginRegistry(
            loader=loader,
            sandbox=PluginSandbox(),
            permission_model=permission_model,
            event_bus=event_bus,
            platform_adapter=_FakePlatformAdapter(),
            plugin_data_root=tmp_path / "plugin-data",
        )
        self.store = PluginStore(
            self.registry,
            staging_dir=tmp_path / "staging",
            signature_verifier=signature_verifier
            or UnsignedAllowedVerifier(allow_unsigned=allow_unsigned),
        )


# ---- compute_package_digest ----------------------------------------------------
def test_digest_is_deterministic(tmp_path):
    pkg = _write_package(tmp_path / "src", "hello")
    assert compute_package_digest(pkg) == compute_package_digest(pkg)


def test_digest_changes_when_content_changes(tmp_path):
    pkg = _write_package(tmp_path / "src", "hello")
    before = compute_package_digest(pkg)
    (pkg / "plugin.py").write_text(_GOOD_PLUGIN_PY + "\n# changed\n", encoding="utf-8")
    after = compute_package_digest(pkg)
    assert before != after


def test_digest_excludes_named_file(tmp_path):
    pkg = _write_package(tmp_path / "src", "hello")
    (pkg / "checksums.json").write_text("{}", encoding="utf-8")
    with_checksums = compute_package_digest(pkg, exclude=frozenset({"checksums.json"}))
    (pkg / "checksums.json").unlink()
    without_checksums = compute_package_digest(pkg)
    assert with_checksums == without_checksums


# ---- staging (package format) ----------------------------------------------------
def test_stage_package_directory_used_in_place(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello")
    assert h.store.stage_package(pkg) == pkg


def test_stage_package_extracts_zip(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello")
    zip_path = _zip_dir(pkg, tmp_path / "hello.zip")

    staged = h.store.stage_package(zip_path)

    assert (staged / "manifest.json").exists()
    assert (staged / "plugin.py").exists()


def test_stage_package_rejects_bad_zip(tmp_path):
    h = _Harness(tmp_path)
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a real zip")
    with pytest.raises(PluginStoreError):
        h.store.stage_package(bad_zip)


def test_stage_package_rejects_unsupported_extension(tmp_path):
    h = _Harness(tmp_path)
    weird = tmp_path / "package.rar"
    weird.write_bytes(b"data")
    with pytest.raises(PluginStoreError):
        h.store.stage_package(weird)


def test_stage_package_rejects_zip_slip(tmp_path):
    h = _Harness(tmp_path)
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../../evil.txt", "pwned")
    with pytest.raises(PluginStoreError):
        h.store.stage_package(zip_path)


# ---- verification ----------------------------------------------------------
def test_verify_unsigned_allowed_by_default(tmp_path):
    h = _Harness(tmp_path, allow_unsigned=True)
    pkg = _write_package(tmp_path / "src", "hello")
    result = h.store.verify_package(pkg)
    assert result.verified is True
    assert result.signed is False


def test_verify_unsigned_rejected_when_not_allowed(tmp_path):
    h = _Harness(tmp_path, allow_unsigned=False)
    pkg = _write_package(tmp_path / "src", "hello")
    result = h.store.verify_package(pkg)
    assert result.verified is False


def test_verify_rejects_invalid_manifest(tmp_path):
    h = _Harness(tmp_path)
    pkg = tmp_path / "src" / "hello"
    pkg.mkdir(parents=True)
    (pkg / "manifest.json").write_text("{not valid json", encoding="utf-8")
    result = h.store.verify_package(pkg)
    assert result.verified is False


def test_verify_checksum_match_passes(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello")
    digest = compute_package_digest(pkg, exclude=frozenset({"checksums.json"}))
    (pkg / "checksums.json").write_text(json.dumps({"sha256": digest}), encoding="utf-8")
    result = h.store.verify_package(pkg)
    assert result.verified is True


def test_verify_checksum_mismatch_fails(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello")
    (pkg / "checksums.json").write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    result = h.store.verify_package(pkg)
    assert result.verified is False
    assert "mismatch" in result.detail.lower()


def test_verify_valid_signature_passes(tmp_path):
    h = _Harness(tmp_path, allow_unsigned=False)
    pkg = _write_package(tmp_path / "src", "hello")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    manifest_bytes = (pkg / "manifest.json").read_bytes()
    signature = private_key.sign(manifest_bytes)
    (pkg / "manifest.json.sig").write_bytes(signature)
    (pkg / "publisher.pub").write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
    )

    result = h.store.verify_package(pkg)
    assert result.verified is True
    assert result.signed is True


def test_verify_tampered_signature_fails(tmp_path):
    h = _Harness(tmp_path, allow_unsigned=False)
    pkg = _write_package(tmp_path / "src", "hello")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    signature = private_key.sign(b"different payload entirely")
    (pkg / "manifest.json.sig").write_bytes(signature)
    (pkg / "publisher.pub").write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
    )

    result = h.store.verify_package(pkg)
    assert result.verified is False
    assert result.signed is True


# ---- install / update workflow ----------------------------------------------------
@pytest.mark.asyncio
async def test_install_from_directory(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello-world")
    plugin_id = await h.store.install(pkg)
    assert plugin_id == "hello-world"
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value


@pytest.mark.asyncio
async def test_install_from_zip(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello-world")
    zip_path = _zip_dir(pkg, tmp_path / "hello-world.zip")
    plugin_id = await h.store.install(zip_path)
    assert plugin_id == "hello-world"
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value


@pytest.mark.asyncio
async def test_install_refuses_unverified_package(tmp_path):
    h = _Harness(tmp_path, allow_unsigned=False)
    pkg = _write_package(tmp_path / "src", "hello-world")
    with pytest.raises(PluginStoreError):
        await h.store.install(pkg)
    assert h.registry.is_registered("hello-world") is False


@pytest.mark.asyncio
async def test_update_via_store(tmp_path):
    h = _Harness(tmp_path)
    pkg = _write_package(tmp_path / "src", "hello-world")
    await h.store.install(pkg)

    new_pkg = tmp_path / "new-src" / "hello-world"
    new_pkg.mkdir(parents=True)
    manifest = {
        "name": "hello-world",
        "display_name": "Hello World",
        "version": "2.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (new_pkg / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (new_pkg / "plugin.py").write_text(_GOOD_PLUGIN_PY, encoding="utf-8")

    ok = await h.store.update("hello-world", new_pkg)
    assert ok is True
    assert h.registry.status("hello-world").detail["version"] == "2.0.0"
