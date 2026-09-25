#!/usr/bin/python3
"""OpenDisplay protocol v3 sender over Apple's usbmuxd transport.

This is an independent implementation of the public OpenDisplay wire protocol:
https://github.com/peetzweg/opendisplay/blob/main/PROTOCOL.md
"""

from __future__ import annotations

import json
import plistlib
import queue
import socket
import struct
import sys
import threading
import time
from typing import Any, Callable


OPENDISPLAY_PORT = 9000
PROTOCOL_VERSION = 3
MIN_PROTOCOL_VERSION = 1
USBMUX_HEADER = struct.Struct("<IIII")
FRAME_HEADER = struct.Struct("!I")
MAX_CONTROL_SIZE = (1 << 20) - 1


class USBMuxError(RuntimeError):
    """Raised when usbmuxd cannot create a connection to the receiver."""


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ConnectionError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _usbmux_socket(timeout: float = 5.0) -> socket.socket:
    last_error: OSError | None = None
    for path in ("/run/usbmuxd", "/var/run/usbmuxd"):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(timeout)
        try:
            connection.connect(path)
            return connection
        except OSError as error:
            last_error = error
            connection.close()
    raise USBMuxError(f"usbmuxd is unavailable: {last_error}")


def _usbmux_request(connection: socket.socket, request: dict[str, Any], tag: int = 1) -> dict[str, Any]:
    payload = plistlib.dumps(request, fmt=plistlib.FMT_XML, sort_keys=False)
    connection.sendall(USBMUX_HEADER.pack(16 + len(payload), 1, 8, tag) + payload)
    raw_header = _recv_exact(connection, USBMUX_HEADER.size)
    length, version, message, response_tag = USBMUX_HEADER.unpack(raw_header)
    if version != 1 or message != 8 or response_tag != tag or length < USBMUX_HEADER.size:
        raise USBMuxError("usbmuxd returned an invalid response")
    response = plistlib.loads(_recv_exact(connection, length - USBMUX_HEADER.size))
    if not isinstance(response, dict):
        raise USBMuxError("usbmuxd response was not a dictionary")
    return response


def list_usb_devices() -> list[dict[str, Any]]:
    """Return USB-connected Apple devices known to usbmuxd."""
    connection = _usbmux_socket()
    try:
        response = _usbmux_request(
            connection,
            {
                "MessageType": "ListDevices",
                "ClientVersionString": "tuxdisplay-0.4",
                "ProgName": "tuxdisplay",
                "kLibUSBMuxVersion": 3,
            },
        )
    finally:
        connection.close()
    devices = response.get("DeviceList", [])
    if not isinstance(devices, list):
        return []
    return [
        device
        for device in devices
        if isinstance(device, dict)
        and isinstance(device.get("DeviceID"), int)
        and isinstance(device.get("Properties"), dict)
        and device["Properties"].get("ConnectionType") == "USB"
    ]


def connect_usb_device(device_id: int, port: int = OPENDISPLAY_PORT) -> socket.socket:
    """Open a transparent TCP stream to a port on an iPad through usbmuxd."""
    connection = _usbmux_socket()
    try:
        response = _usbmux_request(
            connection,
            {
                "MessageType": "Connect",
                "ClientVersionString": "tuxdisplay-0.4",
                "ProgName": "tuxdisplay",
                "DeviceID": int(device_id),
                # usbmuxd's plist protocol carries the TCP port in network order.
                "PortNumber": socket.htons(port),
                "kLibUSBMuxVersion": 3,
            },
        )
        result = int(response.get("Number", -1))
        if result != 0:
            raise USBMuxError(f"OpenDisplay is not accepting USB connections (usbmuxd error {result})")
        return connection
    except Exception:
        connection.close()
        raise


def encode_frame(payload: bytes) -> bytes:
    return FRAME_HEADER.pack(len(payload)) + payload


def receive_frame(connection: socket.socket) -> bytes:
    length = FRAME_HEADER.unpack(_recv_exact(connection, FRAME_HEADER.size))[0]
    if not 0 < length <= MAX_CONTROL_SIZE:
        raise ConnectionError(f"invalid OpenDisplay control frame length: {length}")
    return _recv_exact(connection, length)


def _find_start_codes(data: bytes) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    index = 0
    while index + 3 <= len(data):
        if data[index : index + 4] == b"\x00\x00\x00\x01":
            positions.append((index, 4))
            index += 4
        elif data[index : index + 3] == b"\x00\x00\x01":
            positions.append((index, 3))
            index += 3
        else:
            index += 1
    return positions


def normalize_annex_b(data: bytes) -> tuple[bytes, bool]:
    """Normalize every Annex-B NAL start code to four bytes and report IDR."""
    starts = _find_start_codes(data)
    if not starts:
        return b"", False
    output = bytearray()
    is_idr = False
    for item_index, (position, marker_size) in enumerate(starts):
        payload_start = position + marker_size
        payload_end = starts[item_index + 1][0] if item_index + 1 < len(starts) else len(data)
        nalu = data[payload_start:payload_end]
        while nalu.endswith(b"\x00"):
            nalu = nalu[:-1]
        if not nalu:
            continue
        is_idr = is_idr or (nalu[0] & 0x1F) == 5
        output.extend(b"\x00\x00\x00\x01")
        output.extend(nalu)
    return bytes(output), is_idr


class OpenDisplayUSB:
    """Reconnectable OpenDisplay sender for one directly attached iPad."""

    def __init__(
        self,
        width: int,
        height: int,
        frames_per_second: int,
        on_control: Callable[[dict[str, Any]], None],
        on_connected: Callable[[bool, str], None],
        request_keyframe: Callable[[], None],
    ) -> None:
        self.width = width
        self.height = height
        self.frames_per_second = frames_per_second
        self.on_control = on_control
        self.on_connected = on_connected
        self.request_keyframe = request_keyframe
        self.stop_event = threading.Event()
        self.session_failed = threading.Event()
        self.video_queue: queue.Queue[tuple[bytes, int]] = queue.Queue(maxsize=2)
        self.connection: socket.socket | None = None
        self.connection_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.waiting_for_idr = True
        self.dropped_frames = 0

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="tuxdisplay-opendisplay-usb", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.connection_lock:
            connection = self.connection
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        if self.thread:
            self.thread.join(timeout=3)

    def submit_video(self, access_unit: bytes, captured_ms: int) -> None:
        normalized, is_idr = normalize_annex_b(access_unit)
        if not normalized:
            return
        with self.connection_lock:
            connected = self.connection is not None
        if not connected:
            return
        if self.waiting_for_idr:
            if not is_idr:
                return
            self.waiting_for_idr = False
        item = (normalized, captured_ms)
        try:
            self.video_queue.put_nowait(item)
        except queue.Full:
            try:
                self.video_queue.get_nowait()
            except queue.Empty:
                pass
            self.dropped_frames += 1
            try:
                self.video_queue.put_nowait(item)
            except queue.Full:
                self.dropped_frames += 1

    def _send_packet(self, payload: bytes) -> None:
        with self.connection_lock:
            connection = self.connection
        if connection is None:
            raise ConnectionError("OpenDisplay is disconnected")
        try:
            with self.send_lock:
                connection.sendall(encode_frame(payload))
        except OSError:
            self.session_failed.set()
            raise

    def _send_control(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(payload) >= 32768 or not payload.startswith(b"{") or b"\x00" in payload:
            raise ValueError("invalid OpenDisplay control message")
        self._send_packet(payload)

    def _writer(self) -> None:
        while not self.stop_event.is_set() and not self.session_failed.is_set():
            try:
                access_unit, captured_ms = self.video_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            sent_ms = int(time.time() * 1000)
            telemetry = json.dumps({"cap": captured_ms, "snd": sent_ms}, separators=(",", ":")).encode("ascii")
            try:
                self._send_packet(telemetry + access_unit)
            except (ConnectionError, OSError):
                return

    def _handle_message(self, message: dict[str, Any]) -> bool:
        kind = str(message.get("type", ""))
        if kind == "ping":
            self._send_control({"type": "pong", "t": message.get("t", 0), "mt": int(time.time() * 1000)})
        elif kind == "kf":
            self.waiting_for_idr = True
            self.request_keyframe()
        elif kind == "stats":
            print("PHONE-STATS " + json.dumps(message, separators=(",", ":")), file=sys.stderr, flush=True)
        elif kind in {"sleeping", "closing"}:
            return False
        try:
            self.on_control(message)
        except Exception as error:
            print(f"TuxDisplay OpenDisplay input error: {error}", file=sys.stderr, flush=True)
        return True

    def _receive_hello(self, connection: socket.socket) -> dict[str, Any]:
        payload = receive_frame(connection)
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConnectionError(f"OpenDisplay did not send a valid hello: {error}") from error
        if not isinstance(message, dict) or message.get("type") != "hello":
            raise ConnectionError("OpenDisplay hello was not the first message")
        return message

    def _run_session(self, connection: socket.socket, serial: str) -> None:
        connection.settimeout(5.0)
        hello = self._receive_hello(connection)
        receiver_version = int(hello.get("pv", 1))
        with self.connection_lock:
            self.connection = connection
        self.session_failed.clear()
        self.waiting_for_idr = True
        while not self.video_queue.empty():
            try:
                self.video_queue.get_nowait()
            except queue.Empty:
                break
        self.on_connected(True, serial)
        self.on_control(hello)
        self._send_control({"type": "welcome", "pv": PROTOCOL_VERSION, "min": MIN_PROTOCOL_VERSION})
        if receiver_version >= 3:
            self._send_control(
                {
                    "type": "streamConfig",
                    "codec": "h264",
                    "width": self.width,
                    "height": self.height,
                    "framesPerSecond": self.frames_per_second,
                }
            )
        self.request_keyframe()
        writer = threading.Thread(target=self._writer, name="tuxdisplay-opendisplay-writer", daemon=True)
        writer.start()
        connection.settimeout(0.5)
        last_received = time.monotonic()
        last_ping = 0.0
        try:
            while not self.stop_event.is_set() and not self.session_failed.is_set():
                now = time.monotonic()
                if now - last_ping >= 2.0:
                    self._send_control(
                        {
                            "type": "ping",
                            "drops": self.dropped_frames,
                            "netDrops": self.dropped_frames,
                            "pending": self.video_queue.qsize(),
                            "capFps": self.frames_per_second,
                        }
                    )
                    last_ping = now
                try:
                    payload = receive_frame(connection)
                except socket.timeout:
                    if now - last_received > 6.0:
                        raise ConnectionError("OpenDisplay receiver stopped responding")
                    continue
                last_received = time.monotonic()
                try:
                    message = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(message, dict) and not self._handle_message(message):
                    return
        finally:
            self.session_failed.set()
            writer.join(timeout=2)

    def _run(self) -> None:
        last_status = ""
        while not self.stop_event.is_set():
            connection: socket.socket | None = None
            serial = "iPad"
            try:
                devices = list_usb_devices()
                if not devices:
                    status = "Waiting for a trusted iPad USB cable"
                    if status != last_status:
                        self.on_connected(False, status)
                        last_status = status
                    self.stop_event.wait(1.0)
                    continue
                device = devices[0]
                properties = device.get("Properties", {})
                serial = str(properties.get("SerialNumber", "iPad"))
                connection = connect_usb_device(int(device["DeviceID"]))
                last_status = ""
                self._run_session(connection, serial)
            except (OSError, ConnectionError, USBMuxError, ValueError, plistlib.InvalidFileException) as error:
                status = f"Open OpenDisplay on the iPad ({error})"
                if status != last_status:
                    self.on_connected(False, status)
                    last_status = status
                self.stop_event.wait(1.0)
            finally:
                with self.connection_lock:
                    if self.connection is connection:
                        self.connection = None
                if connection is not None:
                    connection.close()
                self.on_connected(False, "Waiting for OpenDisplay")
