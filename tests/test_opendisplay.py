#!/usr/bin/python3
"""Protocol-level smoke tests for the OpenDisplay USB sender."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "opendisplay_usb.py"
SPEC = importlib.util.spec_from_file_location("opendisplay_usb", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OpenDisplayProtocolTests(unittest.TestCase):
    def test_frame_prefix_is_big_endian(self) -> None:
        encoded = MODULE.encode_frame(b"hello")
        self.assertEqual(encoded[:4], struct.pack("!I", 5))
        self.assertEqual(encoded[4:], b"hello")

    def test_receive_frame_reassembles_fragmented_payload(self) -> None:
        packet = MODULE.encode_frame(json.dumps({"type": "hello"}).encode())

        class FragmentedConnection:
            def __init__(self, data: bytes) -> None:
                self.data = data

            def recv(self, _size: int) -> bytes:
                if not self.data:
                    return b""
                chunk, self.data = self.data[:1], self.data[1:]
                return chunk

        self.assertEqual(MODULE.receive_frame(FragmentedConnection(packet)), packet[4:])

    def test_annex_b_normalizes_start_codes_and_detects_idr(self) -> None:
        raw = (
            b"\x00\x00\x01\x67sps"
            b"\x00\x00\x00\x01\x68pps"
            b"\x00\x00\x01\x65idr"
        )
        normalized, is_idr = MODULE.normalize_annex_b(raw)
        self.assertTrue(is_idr)
        self.assertEqual(normalized.count(b"\x00\x00\x00\x01"), 3)
        self.assertNotIn(b"\x00\x00\x01", normalized.replace(b"\x00\x00\x00\x01", b""))

    def test_non_h264_payload_is_rejected(self) -> None:
        normalized, is_idr = MODULE.normalize_annex_b(b"not h264")
        self.assertEqual(normalized, b"")
        self.assertFalse(is_idr)


if __name__ == "__main__":
    unittest.main()
