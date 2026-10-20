#!/usr/bin/python3
"""Create a detached-key Ed25519 update manifest for a release package."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def canonical(payload: dict[str, str]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--notes", default="Security hardening release")
    arguments = parser.parse_args()
    package = arguments.package.read_bytes()
    package_name = f"tuxdisplay_{arguments.version}_all.deb"
    if arguments.package.name != package_name:
        parser.error(f"package must be named {package_name}")
    payload = {
        "version": arguments.version,
        "package_name": package_name,
        "package_url": f"https://github.com/tpluharik/tuxdisplay/releases/download/v{arguments.version}/{package_name}",
        "sha256": hashlib.sha256(package).hexdigest(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=366)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "release_url": f"https://github.com/tpluharik/tuxdisplay/releases/tag/v{arguments.version}",
        "notes": arguments.notes,
    }
    private_key = serialization.load_pem_private_key(arguments.key.read_bytes(), password=None)
    signature = private_key.sign(canonical(payload))
    signed = dict(payload)
    signed["signature"] = base64.b64encode(signature).decode("ascii")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
