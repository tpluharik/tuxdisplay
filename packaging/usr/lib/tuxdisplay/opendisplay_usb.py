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
MAX_USBMUX_MESSAGE_SIZE = 1 << 20


class USBMuxError(RuntimeError):
    """Raised when usbmuxd cannot create a connection to the receiver."""


class OpenDisplayPointerTranslator:
    """Turn OpenDisplay's slot-less touch stream into safe pointer events.

    Mutter's RemoteDesktop touch API requires perfectly paired, unique touch
    slots. OpenDisplay protocol v3 carries no slot identifier and may repeat a
    began phase after reconnects or gesture changes. Pointer/button injection
    preserves tap, drag, hover, Pencil, and scroll without risking a duplicate
    touch-slot assertion inside the compositor.
    """

    def __init__(self) -> None:
        self.button_down = False
        self.last_x = 0.0
        self.last_y = 0.0

    def translate(self, message: dict[str, Any], width: int, height: int) -> list[dict[str, Any]]:
        kind = str(message.get("type", ""))
        normalized_x = min(1.0, max(0.0, float(message.get("x", 0.0))))
        normalized_y = min(1.0, max(0.0, float(message.get("y", 0.0))))
        self.last_x = normalized_x * width
        self.last_y = normalized_y * height

        if kind == "scroll":
            return [
                {
                    "type": "wheel",
                    "dx": float(message.get("dx", 0.0)),
                    "dy": float(message.get("dy", 0.0)),
                    "x": self.last_x,
                    "y": self.last_y,
                }
            ]

        if kind == "touch":
            phase = str(message.get("phase", ""))
            if phase == "began":
                if self.button_down:
                    return [self._motion()]
                self.button_down = True
                return [self._button(True)]
            if phase == "moved":
                return [self._motion()]
            if phase in {"ended", "cancelled"}:
                if not self.button_down:
                    return []
                self.button_down = False
                return [self._button(False)]
            return []

        if kind == "pencil":
            phase = str(message.get("phase", ""))
            if phase == "down":
                if self.button_down:
                    return [self._motion()]
                self.button_down = True
                return [self._button(True)]
            if phase in {"move", "hover"}:
                return [self._motion()]
            if phase == "up":
                if not self.button_down:
                    return []
                self.button_down = False
                return [self._button(False)]
        return []

    def release(self) -> list[dict[str, Any]]:
        if not self.button_down:
            return []
        self.button_down = False
        return [self._button(False)]

    def _motion(self) -> dict[str, Any]:
        return {"type": "motion", "x": self.last_x, "y": self.last_y}

    def _button(self, down: bool) -> dict[str, Any]:
        return {"type": "button", "button": 0, "down": down, "x": self.last_x, "y": self.last_y}


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
    if (
        version != 1
        or message != 8
        or response_tag != tag
        or length < USBMUX_HEADER.size
        or length > MAX_USBMUX_MESSAGE_SIZE
    ):
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
                "ClientVersionString": "tuxdisplay-0.4.7",
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
                "ClientVersionString": "tuxdisplay-0.4.7",
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
        self.video_queue: queue.Queue[tuple[int, bytes, int]] = queue.Queue(maxsize=2)
        self.connection: socket.socket | None = None
        self.connection_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.video_state_lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.waiting_for_idr = True
        self.latest_keyframe: bytes | None = None
        self.video_generation = 0
        self.last_video_submitted = 0.0
        self.last_video_sent = 0.0
        self.queued_video_since_stats = 0
        self.bad_stats_reports = 0
        self.last_recovery = 0.0
        self.dropped_frames = 0

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="tuxdisplay-opendisplay-usb", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.session_failed.set()
        with self.connection_lock:
            connection = self.connection
            self.connection = None
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
        now = time.monotonic()
        with self.connection_lock:
            connected = self.connection is not None
        with self.video_state_lock:
            self.last_video_submitted = now
            if is_idr:
                self.latest_keyframe = normalized
            if not connected:
                return
            if self.waiting_for_idr:
                if not is_idr:
                    return
                self.waiting_for_idr = False
            generation = self.video_generation
            self.queued_video_since_stats += 1
            self._queue_video_locked((generation, normalized, captured_ms))

    def _queue_video_locked(self, item: tuple[int, bytes, int]) -> None:
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

    def _clear_video_queue_locked(self) -> None:
        while not self.video_queue.empty():
            try:
                self.video_queue.get_nowait()
            except queue.Empty:
                return

    def _prime_cached_keyframe(self) -> bool:
        """Show a static desktop while still waiting for a fresh session IDR."""
        with self.video_state_lock:
            keyframe = self.latest_keyframe
            if keyframe is None:
                self.waiting_for_idr = True
                return False
            self._queue_video_locked((self.video_generation, keyframe, int(time.time() * 1000)))
            return True

    def _reset_video_stream(self, prime_cached: bool) -> None:
        """Atomically discard the old prediction chain and require a fresh IDR."""
        with self.video_state_lock:
            self.video_generation += 1
            self.waiting_for_idr = True
            self._clear_video_queue_locked()
            keyframe = self.latest_keyframe if prime_cached else None
            if keyframe is not None:
                self._queue_video_locked((self.video_generation, keyframe, int(time.time() * 1000)))

    def _request_recovery_keyframe(self, prime_cached: bool = False) -> None:
        self._reset_video_stream(prime_cached=prime_cached)
        self.request_keyframe()

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
                generation, access_unit, captured_ms = self.video_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.video_state_lock:
                if generation != self.video_generation:
                    continue
            sent_ms = int(time.time() * 1000)
            telemetry = json.dumps({"cap": captured_ms, "snd": sent_ms}, separators=(",", ":")).encode("ascii")
            try:
                self._send_packet(telemetry + access_unit)
                self.last_video_sent = time.monotonic()
            except (ConnectionError, OSError):
                return

    def _handle_stats(self, message: dict[str, Any]) -> bool:
        """Use receiver health as a staged IDR-then-reconnect watchdog."""
        now = time.monotonic()
        try:
            receiver_fps = float(message.get("fps", 0))
            lost = int(message.get("curLost", 0))
        except (TypeError, ValueError, OverflowError):
            return True
        with self.video_state_lock:
            queued_frames = self.queued_video_since_stats
            self.queued_video_since_stats = 0
        # OpenDisplay's `stalls` field counts decoder starvation while a
        # damage-driven desktop is quiet; it is not evidence of a broken USB
        # session. Only compare FPS when the sender actually queued at least
        # two seconds of frames during the reporting window.
        source_active = queued_frames >= max(3, self.frames_per_second * 2)
        unhealthy = lost > 0 or (source_active and receiver_fps < max(1.0, self.frames_per_second * 0.25))
        if not unhealthy:
            self.bad_stats_reports = 0
            return True
        self.bad_stats_reports += 1
        if self.bad_stats_reports == 1 and now - self.last_recovery >= 3.0:
            self.last_recovery = now
            self._request_recovery_keyframe()
        elif self.bad_stats_reports >= 3 and now - self.last_recovery >= 8.0:
            self.session_failed.set()
            return False
        return True

    def _handle_message(self, message: dict[str, Any]) -> bool:
        kind = str(message.get("type", ""))
        if kind == "ping":
            self._send_control({"type": "pong", "t": message.get("t", 0), "mt": int(time.time() * 1000)})
        elif kind == "kf":
            self._request_recovery_keyframe(prime_cached=True)
        elif kind == "stats":
            print("PHONE-STATS " + json.dumps(message, separators=(",", ":")), file=sys.stderr, flush=True)
            if not self._handle_stats(message):
                return False
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
        receiver_version = hello.get("pv", 1)
        if isinstance(receiver_version, bool) or not isinstance(receiver_version, int):
            raise ConnectionError("OpenDisplay hello has an invalid protocol version")
        if receiver_version < MIN_PROTOCOL_VERSION:
            raise ConnectionError(f"OpenDisplay protocol {receiver_version} is too old")
        self.session_failed.clear()
        self.bad_stats_reports = 0
        with self.video_state_lock:
            self.queued_video_since_stats = 0
        self._reset_video_stream(prime_cached=True)
        with self.connection_lock:
            self.connection = connection
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
        self.on_connected(True, serial)
        print("TuxDisplay OpenDisplay USB connected", file=sys.stderr, flush=True)
        self.on_control(hello)
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
                    if time.monotonic() - last_received > 6.0:
                        raise ConnectionError("OpenDisplay receiver stopped responding")
                    continue
                try:
                    message = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(message, dict):
                    continue
                last_received = time.monotonic()
                if not self._handle_message(message):
                    return
        finally:
            self.session_failed.set()
            writer.join(timeout=2)
            print("TuxDisplay OpenDisplay USB disconnected", file=sys.stderr, flush=True)

    def _run(self) -> None:
        last_status = ""
        retry_delay = 0.5
        while not self.stop_event.is_set():
            try:
                devices = list_usb_devices()
            except Exception as error:
                devices = []
                status = f"usbmuxd error: {error}"
                if status != last_status:
                    self.on_connected(False, status)
                    last_status = status
                self.stop_event.wait(min(4.0, retry_delay))
                retry_delay = min(4.0, retry_delay * 2)
                continue
            if not devices:
                status = "Waiting for a trusted iPad USB cable"
                if status != last_status:
                    self.on_connected(False, status)
                    last_status = status
                retry_delay = 0.5
                self.stop_event.wait(1.0)
                continue

            errors: list[str] = []
            session_ran = False
            for device in devices:
                if self.stop_event.is_set():
                    break
                connection: socket.socket | None = None
                properties = device.get("Properties", {})
                serial = str(properties.get("SerialNumber", "iPad"))
                try:
                    connection = connect_usb_device(int(device["DeviceID"]))
                    self._run_session(connection, serial)
                    session_ran = True
                    retry_delay = 0.5
                    break
                except Exception as error:
                    errors.append(str(error))
                finally:
                    with self.connection_lock:
                        if self.connection is connection:
                            self.connection = None
                    if connection is not None:
                        try:
                            connection.close()
                        except OSError:
                            pass
                    if session_ran and not self.stop_event.is_set():
                        self.on_connected(False, "Waiting for OpenDisplay")

            if self.stop_event.is_set():
                break
            if session_ran:
                last_status = "Waiting for OpenDisplay"
                self.stop_event.wait(0.5)
                continue
            detail = "; ".join(errors[:2]) or "receiver unavailable"
            status = f"Open OpenDisplay on the iPad ({detail})"
            if status != last_status:
                self.on_connected(False, status)
                last_status = status
            self.stop_event.wait(retry_delay)
            retry_delay = min(4.0, retry_delay * 2)
