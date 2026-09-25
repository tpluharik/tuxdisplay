#!/usr/bin/python3
"""Protocol-level smoke tests for the OpenDisplay USB sender."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import unittest
from unittest import mock


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

    def test_cached_keyframe_primes_a_static_desktop_session(self) -> None:
        sender = MODULE.OpenDisplayUSB(1920, 1080, 30, lambda _message: None, lambda _connected, _status: None, lambda: None)
        keyframe = b"\x00\x00\x00\x01\x67sps\x00\x00\x00\x01\x68pps\x00\x00\x00\x01\x65idr"

        sender.submit_video(keyframe, 1)

        self.assertIsNotNone(sender.latest_keyframe)
        self.assertTrue(sender._prime_cached_keyframe())
        _generation, queued, captured_ms = sender.video_queue.get_nowait()
        self.assertIn(b"\x00\x00\x00\x01\x65idr", queued)
        self.assertGreater(captured_ms, 1)
        self.assertTrue(sender.waiting_for_idr)

    def test_cached_keyframe_keeps_delta_frames_gated_until_fresh_idr(self) -> None:
        sender = MODULE.OpenDisplayUSB(1920, 1080, 30, lambda _message: None, lambda _connected, _status: None, lambda: None)
        keyframe = b"\x00\x00\x00\x01\x67sps\x00\x00\x00\x01\x68pps\x00\x00\x00\x01\x65idr"
        delta = b"\x00\x00\x00\x01\x41delta"
        sender.submit_video(keyframe, 1)
        sender._reset_video_stream(prime_cached=True)
        with sender.connection_lock:
            sender.connection = object()

        sender.submit_video(delta, 2)
        self.assertEqual(sender.video_queue.qsize(), 1)
        sender.submit_video(keyframe, 3)

        self.assertEqual(sender.video_queue.qsize(), 2)
        self.assertFalse(sender.waiting_for_idr)

    def test_invalid_protocol_version_is_a_recoverable_connection_error(self) -> None:
        packet = MODULE.encode_frame(json.dumps({"type": "hello", "pv": None}).encode())

        class FakeConnection:
            def __init__(self, data: bytes) -> None:
                self.data = data

            def settimeout(self, _timeout: float) -> None:
                pass

            def recv(self, size: int) -> bytes:
                chunk, self.data = self.data[:size], self.data[size:]
                return chunk

        sender = MODULE.OpenDisplayUSB(1920, 1080, 30, lambda _message: None, lambda _connected, _status: None, lambda: None)
        with self.assertRaisesRegex(ConnectionError, "invalid protocol version"):
            sender._run_session(FakeConnection(packet), "test")

    def test_receiver_loss_requests_idr_then_reconnect(self) -> None:
        recoveries = []
        sender = MODULE.OpenDisplayUSB(
            1920,
            1080,
            30,
            lambda _message: None,
            lambda _connected, _status: None,
            lambda: recoveries.append("idr"),
        )
        self.assertTrue(sender._handle_stats({"fps": 0, "stalls": 4, "curLost": 1}))
        self.assertEqual(recoveries, ["idr"])
        sender.last_recovery -= 9
        self.assertTrue(sender._handle_stats({"fps": 0, "stalls": 4, "curLost": 1}))
        self.assertFalse(sender._handle_stats({"fps": 0, "stalls": 4, "curLost": 1}))
        self.assertTrue(sender.session_failed.is_set())

    def test_stall_counter_does_not_reconnect_a_healthy_stream(self) -> None:
        recoveries = []
        sender = MODULE.OpenDisplayUSB(
            1920,
            1080,
            15,
            lambda _message: None,
            lambda _connected, _status: None,
            lambda: recoveries.append("idr"),
        )
        sender.queued_video_since_stats = 75

        self.assertTrue(sender._handle_stats({"fps": 14, "stalls": 99, "curLost": 0}))
        self.assertEqual(sender.bad_stats_reports, 0)
        self.assertEqual(recoveries, [])

    def test_quiet_damage_driven_desktop_is_not_a_failed_stream(self) -> None:
        recoveries = []
        sender = MODULE.OpenDisplayUSB(
            1920,
            1080,
            30,
            lambda _message: None,
            lambda _connected, _status: None,
            lambda: recoveries.append("idr"),
        )

        self.assertTrue(sender._handle_stats({"fps": 0, "stalls": 20, "curLost": 0}))
        self.assertEqual(sender.bad_stats_reports, 0)
        self.assertEqual(recoveries, [])

    def test_connection_loop_tries_every_attached_apple_device(self) -> None:
        attempts = []

        class FakeConnection:
            def close(self) -> None:
                pass

        sender = MODULE.OpenDisplayUSB(1920, 1080, 30, lambda _message: None, lambda _connected, _status: None, lambda: None)

        def connect(device_id: int) -> FakeConnection:
            attempts.append(device_id)
            if device_id == 1:
                raise MODULE.USBMuxError("wrong device")
            return FakeConnection()

        def run_session(_connection: FakeConnection, _serial: str) -> None:
            sender.stop_event.set()

        devices = [
            {"DeviceID": 1, "Properties": {"SerialNumber": "phone"}},
            {"DeviceID": 2, "Properties": {"SerialNumber": "ipad"}},
        ]
        with mock.patch.object(MODULE, "list_usb_devices", return_value=devices), mock.patch.object(
            MODULE, "connect_usb_device", side_effect=connect
        ), mock.patch.object(sender, "_run_session", side_effect=run_session):
            sender._run()

        self.assertEqual(attempts, [1, 2])


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
