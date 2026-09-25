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


class OpenDisplayPointerTranslatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = MODULE.OpenDisplayPointerTranslator()

    def test_duplicate_touch_phases_produce_one_button_pair(self) -> None:
        events = []
        events += self.translator.translate({"type": "touch", "phase": "began", "x": 0.25, "y": 0.5}, 1000, 800)
        events += self.translator.translate({"type": "touch", "phase": "began", "x": 0.3, "y": 0.6}, 1000, 800)
        events += self.translator.translate({"type": "touch", "phase": "moved", "x": 0.4, "y": 0.7}, 1000, 800)
        events += self.translator.translate({"type": "touch", "phase": "ended", "x": 0.4, "y": 0.7}, 1000, 800)
        events += self.translator.translate({"type": "touch", "phase": "ended", "x": 0.4, "y": 0.7}, 1000, 800)

        self.assertEqual([event["type"] for event in events], ["button", "motion", "motion", "button"])
        self.assertEqual([event["down"] for event in events if event["type"] == "button"], [True, False])
        self.assertFalse(any(event["type"].startswith("touch_") for event in events))

    def test_release_clears_a_stuck_pointer_once(self) -> None:
        self.translator.translate({"type": "touch", "phase": "began", "x": 0.1, "y": 0.2}, 1000, 500)

        self.assertEqual(
            self.translator.release(),
            [{"type": "button", "button": 0, "down": False, "x": 100.0, "y": 100.0}],
        )
        self.assertEqual(self.translator.release(), [])

    def test_coordinates_are_clamped_and_scaled(self) -> None:
        events = self.translator.translate(
            {"type": "scroll", "x": -1, "y": 2, "dx": 30, "dy": -40},
            1920,
            1080,
        )

        self.assertEqual(events[0]["x"], 0.0)
        self.assertEqual(events[0]["y"], 1080.0)
        self.assertEqual(events[0]["dx"], 30.0)
        self.assertEqual(events[0]["dy"], -40.0)

    def test_duplicate_pencil_phases_are_guarded(self) -> None:
        events = []
        events += self.translator.translate({"type": "pencil", "phase": "down", "x": 0.5, "y": 0.5}, 800, 600)
        events += self.translator.translate({"type": "pencil", "phase": "down", "x": 0.6, "y": 0.6}, 800, 600)
        events += self.translator.translate({"type": "pencil", "phase": "up", "x": 0.6, "y": 0.6}, 800, 600)
        events += self.translator.translate({"type": "pencil", "phase": "up", "x": 0.6, "y": 0.6}, 800, 600)

        self.assertEqual([event["type"] for event in events], ["button", "motion", "button"])
        self.assertEqual([event["down"] for event in events if event["type"] == "button"], [True, False])


if __name__ == "__main__":
    unittest.main()
