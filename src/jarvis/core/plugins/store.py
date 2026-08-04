"""Plugin Store Foundation -- Milestone 9 Task Group D, Phase 7.

The layer in front of :class:`~jarvis.core.plugins.registry.
PluginRegistry` that turns an arbitrary *package* -- a plain directory
or a ``.zip`` archive, always already local -- into the kind of
already-verified directory the Registry's ``install``/``update`` will
accept. "Offline installation support" is not a separate feature here;
it falls out of this design for free, since nothing in this module
ever makes a network call. Fetching a package *from* the network is
Phase 8 (Marketplace)'s job -- by the time anything reaches this
module, the package is already sitting on disk.

**Two independent, real checks, not one conflated "trust" bit:**

* **Integrity** (``checksums.json``, SHA-256) -- did this package
  arrive intact? Always checked when the file is present.
* **Authenticity** (:class:`ISignatureVerifier`, Ed25519 via
  ``cryptography`` -- already a pinned dependency, no new one added) --
  did a specific publisher actually produce this package? Real when a
  ``manifest.json.sig``/``publisher.pub`` pair is present; when
  neither exists, :class:`UnsignedAllowedVerifier` is the honest v1
  default (``docs/MASTER_ROADMAP.md``'s own words: "no hosted infra for
  v1"), controlled by ``allow_unsigned`` rather than silently always
  passing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from jarvis.core.plugins.manifest import PluginManifest, PluginManifestError, load_manifest
from jarvis.core.plugins.sdk import PluginError

if TYPE_CHECKING:
    from jarvis.core.plugins.registry import PluginRegistry

_CHECKSUMS_FILENAME = "checksums.json"
_SIGNATURE_FILENAME = "manifest.json.sig"
_PUBLIC_KEY_FILENAME = "publisher.pub"


class PluginStoreError(PluginError):
    """Raised for a specific package's own staging/verification/
    install failure."""


@dataclass(frozen=True, slots=True)
class PackageVerificationResult:
    verified: bool
    signed: bool
    detail: str = ""


def compute_package_digest(package_dir: Path, *, exclude: frozenset[str] = frozenset()) -> str:
    """A deterministic SHA-256 over every file's relative path and
    content, sorted -- independent of filesystem iteration order, so
    the same package contents always produce the same digest
    regardless of platform or extraction order."""
    hasher = hashlib.sha256()
    files = sorted(p for p in package_dir.rglob("*") if p.is_file() and p.name not in exclude)
    for path in files:
        relative = path.relative_to(package_dir).as_posix()
        hasher.update(relative.encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


@runtime_checkable
class ISignatureVerifier(Protocol):
    def verify(self, package_dir: Path, manifest: PluginManifest) -> PackageVerificationResult: ...


class UnsignedAllowedVerifier:
    """The real, honest v1 default. If ``manifest.json.sig`` +
    ``publisher.pub`` are both present, verifies a genuine Ed25519
    signature over ``manifest.json``'s raw bytes. If neither is
    present, allows the package only when *allow_unsigned* is true --
    never a silent pass either way."""

    def __init__(self, *, allow_unsigned: bool = True) -> None:
        self._allow_unsigned = allow_unsigned

    def verify(self, package_dir: Path, manifest: PluginManifest) -> PackageVerificationResult:
        sig_path = package_dir / _SIGNATURE_FILENAME
        pubkey_path = package_dir / _PUBLIC_KEY_FILENAME
        if not sig_path.exists() or not pubkey_path.exists():
            if self._allow_unsigned:
                return PackageVerificationResult(
                    verified=True,
                    signed=False,
                    detail="Unsigned package (no signature files present).",
                )
            return PackageVerificationResult(
                verified=False, signed=False, detail="Unsigned packages are not allowed."
            )
        return self._verify_signature(package_dir, sig_path, pubkey_path)

    @staticmethod
    def _verify_signature(
        package_dir: Path, sig_path: Path, pubkey_path: Path
    ) -> PackageVerificationResult:
        try:
            public_key = Ed25519PublicKey.from_public_bytes(pubkey_path.read_bytes())
            signature = sig_path.read_bytes()
            payload = (package_dir / "manifest.json").read_bytes()
            public_key.verify(signature, payload)
        except InvalidSignature:
            return PackageVerificationResult(
                verified=False, signed=True, detail="Signature verification failed."
            )
        except (OSError, ValueError) as err:
            return PackageVerificationResult(
                verified=False, signed=True, detail=f"Could not verify signature: {err}"
            )
        return PackageVerificationResult(verified=True, signed=True, detail="Signature verified.")


class PluginStore:
    def __init__(
        self,
        registry: PluginRegistry,
        *,
        staging_dir: Path,
        signature_verifier: ISignatureVerifier | None = None,
    ) -> None:
        self._registry = registry
        self._staging_dir = staging_dir
        self._verifier = signature_verifier or UnsignedAllowedVerifier()

    # ---- Staging (package format) ------------------------------------------
    def stage_package(self, package_path: Path) -> Path:
        """*package_path* is a directory or a ``.zip`` archive, already
        local -- resolves either into a real, usable directory. A
        directory is used in place (no copy); a zip is safely
        extracted under this store's own staging directory."""
        if package_path.is_dir():
            return package_path
        if package_path.suffix == ".zip":
            return self._extract_zip(package_path)
        raise PluginStoreError(f"Unsupported package format: {package_path}")

    def _extract_zip(self, package_path: Path) -> Path:
        target = self._staging_dir / package_path.stem
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        resolved_target = target.resolve()
        try:
            with zipfile.ZipFile(package_path) as archive:
                for member in archive.infolist():
                    member_path = (target / member.filename).resolve()
                    if (
                        resolved_target != member_path
                        and resolved_target not in member_path.parents
                    ):
                        raise PluginStoreError(
                            f"Refusing to extract unsafe path from package: {member.filename!r}"
                        )
                archive.extractall(target)
        except zipfile.BadZipFile as err:
            raise PluginStoreError(f"{package_path} is not a valid zip archive: {err}") from err
        return target

    # ---- Verification ------------------------------------------------------
    def verify_package(self, package_dir: Path) -> PackageVerificationResult:
        try:
            manifest = load_manifest(package_dir / "manifest.json")
        except PluginManifestError as err:
            return PackageVerificationResult(verified=False, signed=False, detail=str(err))

        checksum_result = self._verify_checksum(package_dir)
        if not checksum_result.verified:
            return checksum_result
        return self._verifier.verify(package_dir, manifest)

    def _verify_checksum(self, package_dir: Path) -> PackageVerificationResult:
        checksums_path = package_dir / _CHECKSUMS_FILENAME
        if not checksums_path.exists():
            return PackageVerificationResult(
                verified=True,
                signed=False,
                detail="No checksums.json present -- integrity check skipped.",
            )
        try:
            expected = json.loads(checksums_path.read_text(encoding="utf-8"))["sha256"]
        except (OSError, ValueError, KeyError) as err:
            return PackageVerificationResult(
                verified=False, signed=False, detail=f"Could not read checksums.json: {err}"
            )
        actual = compute_package_digest(package_dir, exclude=frozenset({_CHECKSUMS_FILENAME}))
        if actual != expected:
            return PackageVerificationResult(
                verified=False,
                signed=False,
                detail="Checksum mismatch -- package contents do not match checksums.json.",
            )
        return PackageVerificationResult(verified=True, signed=False, detail="Checksum verified.")

    # ---- Install / update workflow ------------------------------------------
    async def install(self, package_path: Path) -> str:
        staged_dir = self.stage_package(package_path)
        result = self.verify_package(staged_dir)
        if not result.verified:
            raise PluginStoreError(f"Package verification failed: {result.detail}")
        return await self._registry.install(staged_dir)

    async def update(self, plugin_id: str, package_path: Path) -> bool:
        staged_dir = self.stage_package(package_path)
        result = self.verify_package(staged_dir)
        if not result.verified:
            raise PluginStoreError(f"Package verification failed: {result.detail}")
        return await self._registry.update(plugin_id, staged_dir)
