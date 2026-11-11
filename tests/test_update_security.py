#!/usr/bin/python3
"""Tests for the signed updater trust boundary."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "update_security.py"
SPEC = importlib.util.spec_from_file_location("update_security_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateSecurityTests(unittest.TestCase):
    def signed_manifest(self) -> tuple[dict[str, str], bytes]:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        payload = {
            "version": "9.9.9",
            "package_name": "tuxdisplay_9.9.9_all.deb",
            "package_url": "https://github.com/tpluharik/tuxdisplay/releases/download/v9.9.9/tuxdisplay_9.9.9_all.deb",
            "sha256": hashlib.sha256(b"package").hexdigest(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "release_url": "https://github.com/tpluharik/tuxdisplay/releases/tag/v9.9.9",
            "notes": "test",
        }
        payload["signature"] = base64.b64encode(private_key.sign(MODULE.canonical_manifest(payload))).decode()
        return payload, public_key

    def test_valid_signature_and_payload_are_required(self) -> None:
        payload, public_key = self.signed_manifest()
        with mock.patch.object(MODULE, "PUBLIC_KEY_B64", base64.b64encode(public_key).decode()):
            verified = MODULE.verify_manifest(payload, current_version="0.4.26")
            self.assertIsNotNone(verified)
            payload["package_url"] = "https://example.invalid/tuxdisplay.deb"
            with self.assertRaises(MODULE.UpdateSecurityError):
                MODULE.verify_manifest(payload, current_version="0.4.26")

    def test_package_bytes_must_match_signed_digest(self) -> None:
        manifest = {"sha256": hashlib.sha256(b"package").hexdigest()}
        self.assertEqual(MODULE.verify_package(manifest, b"package"), manifest["sha256"])
        with self.assertRaises(MODULE.UpdateSecurityError):
            MODULE.verify_package(manifest, b"tampered")


if __name__ == "__main__":
    unittest.main()
