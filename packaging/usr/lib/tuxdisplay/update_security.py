#!/usr/bin/python3
"""Independent update-manifest verification shared by UI and root helper."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import urllib.parse
import urllib.request
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MANIFEST_URL = "https://raw.githubusercontent.com/tpluharik/tuxdisplay/main/update/latest.json"
PUBLIC_KEY_B64 = "E0/GXunX6HczFQjM5zNWOKPCNK0FO4wTE4YeGuiNwrs="
ALLOWED_DOWNLOAD_HOSTS = {
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
MAX_MANIFEST_SIZE = 64 * 1024
MAX_PACKAGE_SIZE = 100 * 1024 * 1024
VERSION_RE = re.compile(r"v?([0-9]+)\.([0-9]+)\.([0-9]+)")


class UpdateSecurityError(RuntimeError):
    """Raised when update metadata or payload verification fails."""


def version_tuple(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version.strip())
    if match is None:
        raise UpdateSecurityError(f"unsupported version: {version}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def download_url(url: str, maximum_size: int, timeout: int = 20) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateSecurityError("The update metadata contains an unsafe download address.")
    request = urllib.request.Request(url, headers={"User-Agent": "TuxDisplay secure updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise UpdateSecurityError("The update download was redirected to an unsafe server.")
        length = response.headers.get("Content-Length")
        try:
            declared_size = int(length) if length is not None else None
        except ValueError as error:
            raise UpdateSecurityError("The update server returned an invalid size.") from error
        if declared_size is not None and declared_size > maximum_size:
            raise UpdateSecurityError("The update download is unexpectedly large.")
        payload = response.read(maximum_size + 1)
    if len(payload) > maximum_size:
        raise UpdateSecurityError("The update download is unexpectedly large.")
    return payload


def canonical_manifest(payload: dict[str, Any]) -> bytes:
    signed = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def verify_manifest(
    payload: object,
    *,
    current_version: str | None = None,
    expected_version: str | None = None,
    now: datetime | None = None,
) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        raise UpdateSecurityError("The signed update manifest is invalid.")
    required = ("version", "package_name", "package_url", "sha256", "expires_at", "signature")
    if any(not isinstance(payload.get(key), str) or not payload.get(key) for key in required):
        raise UpdateSecurityError("The signed update manifest is incomplete.")
    version = str(payload["version"])
    version_tuple(version)
    if expected_version is not None and version != expected_version:
        raise UpdateSecurityError("The privileged installer received a different update version.")
    if current_version is not None and version_tuple(version) <= version_tuple(current_version):
        return None
    package_name = str(payload["package_name"])
    if package_name != f"tuxdisplay_{version}_all.deb":
        raise UpdateSecurityError("The signed manifest has an unexpected package name.")
    digest = str(payload["sha256"]).lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise UpdateSecurityError("The signed manifest has an invalid package checksum.")
    package_url = str(payload["package_url"])
    parsed = urllib.parse.urlparse(package_url)
    expected_path = f"/tpluharik/tuxdisplay/releases/download/v{version}/{package_name}"
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.path != expected_path:
        raise UpdateSecurityError("The signed manifest has an unexpected package address.")
    try:
        expires = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise UpdateSecurityError("The signed manifest has an invalid expiry time.") from error
    if expires.tzinfo is None:
        raise UpdateSecurityError("The signed manifest expiry must include a timezone.")
    if expires <= (now or datetime.now(timezone.utc)):
        raise UpdateSecurityError("The signed update manifest has expired.")
    try:
        signature = base64.b64decode(str(payload["signature"]), validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64, validate=True))
        public_key.verify(signature, canonical_manifest(payload))
    except (ValueError, InvalidSignature) as error:
        raise UpdateSecurityError("The update manifest signature is invalid.") from error
    return {
        "version": version,
        "package_name": package_name,
        "package_url": package_url,
        "sha256": digest,
        "expires_at": str(payload["expires_at"]),
        "release_url": str(payload.get("release_url", "")),
        "notes": str(payload.get("notes", ""))[:4000],
    }


def fetch_manifest(*, current_version: str | None = None, expected_version: str | None = None) -> dict[str, str] | None:
    raw = download_url(MANIFEST_URL, MAX_MANIFEST_SIZE)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateSecurityError("The signed update manifest is unreadable.") from error
    return verify_manifest(payload, current_version=current_version, expected_version=expected_version)


def verify_package(manifest: dict[str, str], package_data: bytes) -> str:
    actual = hashlib.sha256(package_data).hexdigest()
    if not secrets.compare_digest(actual, manifest["sha256"]):
        raise UpdateSecurityError("The downloaded package failed signed checksum verification.")
    return actual
