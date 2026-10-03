#!/usr/bin/python3
"""Small loopback-only Tight/JPEG VNC server for Android USB viewers.

The server intentionally exposes no LAN socket.  Android reaches it through a
device-scoped ``adb reverse`` mapping, so an AVNC client can connect to
127.0.0.1 on the tablet without Wi-Fi or Internet access.
"""

from __future__ import annotations

from collections.abc import Callable
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
from typing import Any


RFB_VERSION = b"RFB 003.008\n"
SECURITY_NONE = 1
ENCODING_TIGHT = 7
JPEG_QUALITY_ENCODINGS = frozenset(range(-32, -22))
MAX_TIGHT_RECTANGLE_WIDTH = 2048
MAX_ENCODINGS = 4096
MAX_CUT_TEXT = 1 << 20


class RFBError(ConnectionError):
    """Raised when a VNC peer violates the supported RFB subset."""


def recv_exact(connection: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RFBError("VNC client disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def tight_length(length: int) -> bytes:
    """Encode TightVNC's one-to-three-byte compact payload length."""
    if not 0 <= length <= 0x3FFFFF:
        raise ValueError("TightVNC payload is too large")
    first = length & 0x7F
    length >>= 7
    if not length:
        return bytes((first,))
    second = length & 0x7F
    length >>= 7
    if not length:
        return bytes((first | 0x80, second))
    return bytes((first | 0x80, second | 0x80, length & 0xFF))


def create_android_reverse(serial: str, port: int) -> None:
    """Map Android localhost:port to this host's loopback-only VNC socket."""
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except FileNotFoundError as error:
        raise RFBError("adb is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise RFBError("adb reverse timed out") from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown adb error"
        raise RFBError(f"adb reverse failed: {detail}")


def remove_android_reverse(serial: str, port: int) -> None:
    try:
        subprocess.run(
            ["adb", "-s", serial, "reverse", "--remove", f"tcp:{port}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


class AndroidReverseManager:
    """Maintain AVNC reverse mappings for currently authorized USB devices."""

    def __init__(
        self,
        port: int,
        discover: Callable[[], list[dict[str, str]]],
        on_status: Callable[[str], None],
    ) -> None:
        self.port = port
        self.discover = discover
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.mapped: dict[str, str] = {}
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="tuxdisplay-avnc-adb", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        for serial in tuple(self.mapped):
            remove_android_reverse(serial, self.port)
        self.mapped.clear()

    def _run(self) -> None:
        last_status = ""
        while not self.stop_event.is_set():
            try:
                devices = self.discover()
            except Exception as error:  # Device discovery must not stop the display service.
                devices = []
                status = f"AVNC USB unavailable: {error}"
            else:
                authorized = {
                    device.get("serial", ""): device.get("model", "Android device").replace("_", " ")
                    for device in devices
                    if device.get("state") == "device" and device.get("serial")
                }
                for serial in tuple(self.mapped):
                    if serial not in authorized:
                        self.mapped.pop(serial, None)
                errors: list[str] = []
                for serial, model in authorized.items():
                    if self.stop_event.is_set():
                        break
                    if serial in self.mapped:
                        continue
                    try:
                        create_android_reverse(serial, self.port)
                    except RFBError as error:
                        errors.append(str(error))
                    else:
                        if self.stop_event.is_set():
                            remove_android_reverse(serial, self.port)
                        else:
                            self.mapped[serial] = model
                if self.mapped:
                    models = ", ".join(sorted(set(self.mapped.values())))
                    status = f"AVNC USB ready on {models}; connect to 127.0.0.1:{self.port}"
                elif errors:
                    status = errors[0]
                elif any(device.get("state") == "unauthorized" for device in devices):
                    status = "Unlock Android and allow USB debugging for AVNC"
                else:
                    status = "Waiting for an authorized Android device for AVNC"
            if status != last_status:
                self.on_status(status)
                last_status = status
            self.stop_event.wait(2)


class TightVNCServer:
    """Serve the existing JPEG frame branch through a minimal RFB 3.8 server."""

    def __init__(
        self,
        width: int,
        height: int,
        port: int,
        frame_ready: threading.Condition,
        frame_snapshot: Callable[[], tuple[int, bytes]],
        on_client: Callable[[bool], None],
        on_input: Callable[[dict[str, Any]], None],
    ) -> None:
        if width > MAX_TIGHT_RECTANGLE_WIDTH:
            raise ValueError(
                f"Tight/JPEG supports widths up to {MAX_TIGHT_RECTANGLE_WIDTH}; "
                "select a smaller TuxDisplay resolution for AVNC"
            )
        self.width = width
        self.height = height
        self.port = port
        self.frame_ready = frame_ready
        self.frame_snapshot = frame_snapshot
        self.on_client = on_client
        self.on_input = on_input
        self.stop_event = threading.Event()
        self.listener: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.connections: set[socket.socket] = set()
        self.connection_lock = threading.Lock()

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen(4)
        listener.settimeout(1)
        self.listener = listener
        self.thread = threading.Thread(target=self._serve, name="tuxdisplay-tightvnc", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
        with self.connection_lock:
            connections = tuple(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass
        with self.frame_ready:
            self.frame_ready.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def _serve(self) -> None:
        assert self.listener is not None
        while not self.stop_event.is_set():
            try:
                connection, _address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.connection_lock:
                self.connections.add(connection)
            threading.Thread(
                target=self._client,
                args=(connection,),
                name="tuxdisplay-tightvnc-client",
                daemon=True,
            ).start()

    def _handshake(self, connection: socket.socket) -> None:
        connection.sendall(RFB_VERSION)
        version = recv_exact(connection, 12)
        if not version.startswith(b"RFB 003."):
            raise RFBError("unsupported RFB version")
        try:
            minor = int(version[8:11])
        except ValueError as error:
            raise RFBError("invalid RFB version") from error
        if minor <= 3:
            connection.sendall(struct.pack("!I", SECURITY_NONE))
        else:
            connection.sendall(bytes((1, SECURITY_NONE)))
            if recv_exact(connection, 1) != bytes((SECURITY_NONE,)):
                raise RFBError("AVNC did not accept the USB-local security mode")
            connection.sendall(struct.pack("!I", 0))
        recv_exact(connection, 1)  # ClientInit shared-flag
        pixel_format = struct.pack("!BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        name = b"TuxDisplay Android USB"
        connection.sendall(struct.pack("!HH", self.width, self.height) + pixel_format + struct.pack("!I", len(name)) + name)

    def _send_frame(self, connection: socket.socket, jpeg: bytes) -> None:
        header = struct.pack("!BBH", 0, 0, 1)
        rectangle = struct.pack("!HHHHi", 0, 0, self.width, self.height, ENCODING_TIGHT)
        connection.sendall(header + rectangle + b"\x90" + tight_length(len(jpeg)) + jpeg)

    def _pointer_events(self, old_mask: int, new_mask: int, x: int, y: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [{"type": "motion", "x": x, "y": y}]
        for bit, button in ((1, 0), (2, 1), (4, 2)):
            if bool(old_mask & bit) != bool(new_mask & bit):
                events.append({"type": "button", "button": button, "down": bool(new_mask & bit), "x": x, "y": y})
        dx = (-120 if new_mask & 32 else 0) + (120 if new_mask & 64 else 0)
        dy = (-120 if new_mask & 8 else 0) + (120 if new_mask & 16 else 0)
        if dx or dy:
            events.append({"type": "wheel", "dx": dx, "dy": dy, "x": x, "y": y})
        return events

    def _client(self, connection: socket.socket) -> None:
        connected = False
        encodings: set[int] = set()
        update_pending = False
        last_generation = -1
        button_mask = 0
        pressed_keys: set[int] = set()
        try:
            connection.settimeout(5)
            self._handshake(connection)
            connection.settimeout(None)
            connected = True
            self.on_client(True)
            print("TuxDisplay AVNC connected through ADB USB", file=sys.stderr, flush=True)
            while not self.stop_event.is_set():
                readable, _writable, _errors = select.select([connection], [], [], 0.05)
                if readable:
                    message_type = recv_exact(connection, 1)[0]
                    if message_type == 0:  # SetPixelFormat
                        recv_exact(connection, 19)
                    elif message_type == 2:  # SetEncodings
                        count = struct.unpack("!H", recv_exact(connection, 3)[1:])[0]
                        if count > MAX_ENCODINGS:
                            raise RFBError("too many requested VNC encodings")
                        raw = recv_exact(connection, count * 4)
                        encodings = set(struct.unpack(f"!{count}i", raw)) if count else set()
                    elif message_type == 3:  # FramebufferUpdateRequest
                        recv_exact(connection, 9)
                        update_pending = True
                    elif message_type == 4:  # KeyEvent
                        body = recv_exact(connection, 7)
                        down = bool(body[0])
                        keysym = struct.unpack("!I", body[3:])[0]
                        if down:
                            pressed_keys.add(keysym)
                        else:
                            pressed_keys.discard(keysym)
                        self.on_input({"type": "key", "keysym": keysym, "down": down})
                    elif message_type == 5:  # PointerEvent
                        body = recv_exact(connection, 5)
                        new_mask = body[0]
                        x, y = struct.unpack("!HH", body[1:])
                        for event in self._pointer_events(button_mask, new_mask, x, y):
                            self.on_input(event)
                        button_mask = new_mask & 7
                    elif message_type == 6:  # ClientCutText
                        length = struct.unpack("!I", recv_exact(connection, 7)[3:])[0]
                        if length > MAX_CUT_TEXT:
                            raise RFBError("VNC clipboard text is too large")
                        recv_exact(connection, length)
                    else:
                        raise RFBError(f"unsupported VNC client message {message_type}")
                if update_pending and ENCODING_TIGHT in encodings and encodings.isdisjoint(JPEG_QUALITY_ENCODINGS):
                    raise RFBError("VNC client did not advertise Tight/JPEG quality support")
                if not update_pending or ENCODING_TIGHT not in encodings:
                    continue
                with self.frame_ready:
                    generation, jpeg = self.frame_snapshot()
                if jpeg and generation != last_generation:
                    self._send_frame(connection, jpeg)
                    last_generation = generation
                    update_pending = False
        except (OSError, RFBError, ValueError, struct.error) as error:
            if not self.stop_event.is_set():
                print(f"TuxDisplay AVNC disconnected: {error}", file=sys.stderr, flush=True)
        finally:
            for bit, button in ((1, 0), (2, 1), (4, 2)):
                if button_mask & bit:
                    try:
                        self.on_input({"type": "button", "button": button, "down": False, "x": 0, "y": 0})
                    except Exception:
                        pass
            for keysym in pressed_keys:
                try:
                    self.on_input({"type": "key", "keysym": keysym, "down": False})
                except Exception:
                    pass
            if connected:
                self.on_client(False)
            with self.connection_lock:
                self.connections.discard(connection)
            try:
                connection.close()
            except OSError:
                pass


def reverse_only_main(arguments: list[str]) -> int:
    """Maintain an ADB reverse for the packaged X11/x11vnc fallback."""
    if len(arguments) != 2 or arguments[0] != "--reverse-only":
        print("usage: tightvnc_usb.py --reverse-only PORT", file=sys.stderr)
        return 2
    try:
        port = int(arguments[1])
    except ValueError:
        print("invalid VNC port", file=sys.stderr)
        return 2
    if not 1024 <= port <= 65535:
        print("invalid VNC port", file=sys.stderr)
        return 2
    from opendisplay_usb import list_android_devices

    finished = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        finished.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    manager = AndroidReverseManager(port, list_android_devices, lambda status: print(status, flush=True))
    manager.start()
    try:
        finished.wait()
    finally:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(reverse_only_main(sys.argv[1:]))
