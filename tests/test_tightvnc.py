#!/usr/bin/python3
"""Protocol tests for the Android AVNC compatibility transport."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import struct
import threading
import time
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "tightvnc_usb.py"
SPEC = importlib.util.spec_from_file_location("tightvnc_usb", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TightVNCProtocolTests(unittest.TestCase):
    def test_compact_lengths_round_trip_boundaries(self) -> None:
        self.assertEqual(MODULE.tight_length(0), b"\x00")
        self.assertEqual(MODULE.tight_length(127), b"\x7f")
        self.assertEqual(MODULE.tight_length(128), b"\x80\x01")
        self.assertEqual(MODULE.tight_length(16384), b"\x80\x80\x01")

    def test_android_reverse_is_device_scoped(self) -> None:
        result = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", return_value=result) as run:
            MODULE.create_android_reverse("ABC123", 5900)

        self.assertEqual(
            run.call_args.args[0],
            ["adb", "-s", "ABC123", "reverse", "tcp:5900", "tcp:5900"],
        )

    def test_tight_jpeg_rejects_a_rectangle_wider_than_the_protocol_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "widths up to 2048"):
            MODULE.TightVNCServer(
                2160,
                1620,
                0,
                threading.Condition(),
                lambda: (0, b""),
                lambda _connected: None,
                lambda _event: None,
            )

    def test_avnc_handshake_tight_jpeg_and_pointer_translation(self) -> None:
        condition = threading.Condition()
        jpeg = b"\xff\xd8tuxdisplay\xff\xd9"
        server = MODULE.TightVNCServer(
            1024,
            768,
            0,
            condition,
            lambda: (1, jpeg),
            lambda _connected: None,
            lambda _event: None,
        )

        class FakeConnection:
            def __init__(self) -> None:
                self.incoming = MODULE.RFB_VERSION + b"\x01\x01"
                self.sent = bytearray()

            def recv(self, length: int) -> bytes:
                chunk, self.incoming = self.incoming[:length], self.incoming[length:]
                return chunk

            def sendall(self, data: bytes) -> None:
                self.sent.extend(data)

        connection = FakeConnection()
        server._handshake(connection)
        self.assertTrue(connection.sent.startswith(MODULE.RFB_VERSION + b"\x01\x01\x00\x00\x00\x00"))
        server_init = bytes(connection.sent[-(24 + len(b"TuxDisplay Android USB")) :])
        self.assertEqual(struct.unpack("!HH", server_init[:4]), (1024, 768))

        connection.sent.clear()
        server._send_frame(connection, jpeg)
        self.assertEqual(bytes(connection.sent[:4]), b"\x00\x00\x00\x01")
        self.assertEqual(struct.unpack("!HHHHi", connection.sent[4:16]), (0, 0, 1024, 768, MODULE.ENCODING_TIGHT))
        self.assertEqual(bytes(connection.sent[16:18]), b"\x90\x0e")
        self.assertEqual(bytes(connection.sent[18:]), jpeg)

        pressed = server._pointer_events(0, 1, 100, 200)
        released = server._pointer_events(1, 0, 100, 200)
        self.assertIn({"type": "button", "button": 0, "down": True, "x": 100, "y": 200}, pressed)
        self.assertIn({"type": "button", "button": 0, "down": False, "x": 100, "y": 200}, released)

    def test_complete_rfb_session_sends_jpeg_and_accepts_pointer_input(self) -> None:
        jpeg = b"\xff\xd8usb-session\xff\xd9"
        clients: list[bool] = []
        events: list[dict[str, object]] = []
        server = MODULE.TightVNCServer(
            1024,
            768,
            0,
            threading.Condition(),
            lambda: (1, jpeg),
            clients.append,
            events.append,
        )
        host, viewer = socket.socketpair()
        viewer.settimeout(2)
        worker = threading.Thread(target=server._client, args=(host,), daemon=True)
        worker.start()
        try:
            self.assertEqual(MODULE.recv_exact(viewer, 12), MODULE.RFB_VERSION)
            viewer.sendall(MODULE.RFB_VERSION)
            self.assertEqual(MODULE.recv_exact(viewer, 2), b"\x01\x01")
            viewer.sendall(b"\x01")
            self.assertEqual(MODULE.recv_exact(viewer, 4), b"\x00\x00\x00\x00")
            viewer.sendall(b"\x01")
            width, height = struct.unpack("!HH", MODULE.recv_exact(viewer, 4))
            self.assertEqual((width, height), (1024, 768))
            MODULE.recv_exact(viewer, 16)
            name_length = struct.unpack("!I", MODULE.recv_exact(viewer, 4))[0]
            self.assertEqual(MODULE.recv_exact(viewer, name_length), b"TuxDisplay Android USB")

            viewer.sendall(struct.pack("!BBHii", 2, 0, 2, MODULE.ENCODING_TIGHT, -32))
            viewer.sendall(struct.pack("!BBHHHH", 3, 0, 0, 0, 1024, 768))
            update = MODULE.recv_exact(viewer, 18 + len(jpeg))
            self.assertEqual(update[-len(jpeg) :], jpeg)

            viewer.sendall(struct.pack("!BBHH", 5, 1, 111, 222))
            viewer.sendall(struct.pack("!BBHH", 5, 0, 111, 222))
            deadline = time.monotonic() + 1
            while len(events) < 4 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIn({"type": "button", "button": 0, "down": True, "x": 111, "y": 222}, events)
            self.assertIn({"type": "button", "button": 0, "down": False, "x": 111, "y": 222}, events)
        finally:
            server.stop_event.set()
            viewer.close()
            worker.join(timeout=2)
        self.assertEqual(clients, [True, False])


if __name__ == "__main__":
    unittest.main()
