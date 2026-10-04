#!/usr/bin/python3
"""Stop TuxDisplay cleanly when the laptop lid closes or sleep begins."""

from __future__ import annotations

import glob
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


LOGIND_NAME = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_INTERFACE = "org.freedesktop.login1.Manager"
UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
UPOWER_INTERFACE = "org.freedesktop.UPower"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DEFAULT_STOP_TIMEOUT = 8.0


def unpack(value: Any) -> Any:
    while hasattr(value, "unpack"):
        value = value.unpack()
    return value


def parse_lid_state(text: str) -> bool | None:
    """Return True for closed, False for open, or None for unknown text."""
    state = text.strip().lower()
    if "closed" in state:
        return True
    if "open" in state:
        return False
    return None


def proc_lid_closed(paths: Sequence[str] | None = None) -> bool | None:
    """Read the kernel ACPI lid state when the interface is available."""
    candidates = tuple(paths) if paths is not None else tuple(glob.glob("/proc/acpi/button/lid/*/state"))
    observed_open = False
    for candidate in candidates:
        try:
            state = parse_lid_state(Path(candidate).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if state is True:
            return True
        if state is False:
            observed_open = True
    return False if observed_open else None


class SleepSignals:
    """Watch logind and UPower while holding a short sleep delay inhibitor."""

    def __init__(self) -> None:
        self.bus: Gio.DBusConnection | None = None
        self.inhibitor_fd = -1
        self.subscriptions: list[int] = []
        self._reason: str | None = None
        self._reason_lock = threading.Lock()

    @property
    def reason(self) -> str | None:
        with self._reason_lock:
            return self._reason

    def request_disconnect(self, reason: str) -> None:
        with self._reason_lock:
            if self._reason is None:
                self._reason = reason

    def connect(self) -> None:
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as error:
            print(f"TuxDisplay lid monitor could not connect to the system bus: {error}", file=sys.stderr, flush=True)
            return
        self._acquire_delay_inhibitor()
        self.subscriptions.append(
            self.bus.signal_subscribe(
                LOGIND_NAME,
                LOGIND_INTERFACE,
                "PrepareForSleep",
                LOGIND_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._prepare_for_sleep,
            )
        )
        self.subscriptions.append(
            self.bus.signal_subscribe(
                UPOWER_NAME,
                PROPERTIES_INTERFACE,
                "PropertiesChanged",
                UPOWER_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._upower_properties_changed,
            )
        )
        self._read_upower_lid_state()

    def _acquire_delay_inhibitor(self) -> None:
        assert self.bus is not None
        try:
            result, fd_list = self.bus.call_with_unix_fd_list_sync(
                LOGIND_NAME,
                LOGIND_PATH,
                LOGIND_INTERFACE,
                "Inhibit",
                GLib.Variant(
                    "(ssss)",
                    (
                        "sleep",
                        "TuxDisplay",
                        "Disconnect the tablet display before system sleep",
                        "delay",
                    ),
                ),
                GLib.VariantType.new("(h)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
            index = int(unpack(result)[0])
            descriptors = list(fd_list.steal_fds())
            if not 0 <= index < len(descriptors):
                raise RuntimeError("logind returned an invalid inhibitor descriptor")
            self.inhibitor_fd = descriptors[index]
            for descriptor_index, descriptor in enumerate(descriptors):
                if descriptor_index != index:
                    os.close(descriptor)
        except (AttributeError, GLib.Error, IndexError, OSError, RuntimeError, TypeError, ValueError) as error:
            print(
                f"TuxDisplay lid monitor could not delay system sleep for cleanup: {error}",
                file=sys.stderr,
                flush=True,
            )

    def _read_upower_lid_state(self) -> None:
        assert self.bus is not None
        try:
            result = self.bus.call_sync(
                UPOWER_NAME,
                UPOWER_PATH,
                PROPERTIES_INTERFACE,
                "Get",
                GLib.Variant("(ss)", (UPOWER_INTERFACE, "LidIsClosed")),
                GLib.VariantType.new("(v)"),
                Gio.DBusCallFlags.NONE,
                3_000,
                None,
            )
            if bool(unpack(result)[0]):
                self.request_disconnect("laptop lid closed")
        except (GLib.Error, TypeError, ValueError):
            # UPower is optional because the kernel ACPI state and logind
            # PrepareForSleep signal provide independent fallbacks.
            pass

    def _prepare_for_sleep(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        _signal: str,
        parameters: GLib.Variant,
    ) -> None:
        values = unpack(parameters)
        if values and bool(values[0]):
            self.request_disconnect("system sleep requested")

    def _upower_properties_changed(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        _signal: str,
        parameters: GLib.Variant,
    ) -> None:
        values = unpack(parameters)
        if len(values) < 2 or values[0] != UPOWER_INTERFACE or not isinstance(values[1], dict):
            return
        lid_closed = unpack(values[1].get("LidIsClosed"))
        if lid_closed is True:
            self.request_disconnect("laptop lid closed")

    def dispatch(self) -> None:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def close(self) -> None:
        if self.bus is not None:
            for subscription in self.subscriptions:
                self.bus.signal_unsubscribe(subscription)
        self.subscriptions.clear()
        if self.inhibitor_fd >= 0:
            try:
                os.close(self.inhibitor_fd)
            except OSError:
                pass
            self.inhibitor_fd = -1
        self.bus = None


def stop_child(child: subprocess.Popen[Any], signum: int, timeout: float = DEFAULT_STOP_TIMEOUT) -> int:
    """Relay shutdown to the display process and bound a wedged teardown."""
    if child.poll() is not None:
        return int(child.returncode or 0)
    try:
        child.send_signal(signum)
        return int(child.wait(timeout=timeout))
    except ProcessLookupError:
        return int(child.poll() or 0)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            return int(child.wait(timeout=2))
        except subprocess.TimeoutExpired:
            child.kill()
            try:
                return int(child.wait(timeout=2))
            except subprocess.TimeoutExpired:
                return -signal.SIGKILL


def run(
    command: Sequence[str],
    lid_reader: Callable[[], bool | None] = proc_lid_closed,
    poll_interval: float = 0.2,
) -> int:
    watcher = SleepSignals()
    watcher.connect()
    if lid_reader() is True:
        watcher.request_disconnect("laptop lid closed")
    if watcher.reason is not None:
        print(f"TuxDisplay not starting: {watcher.reason}", file=sys.stderr, flush=True)
        watcher.close()
        return 0
    try:
        child = subprocess.Popen(list(command))
    except Exception:
        watcher.close()
        raise
    forwarded_signal = signal.SIGINT

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        watcher.request_disconnect("service stop requested")

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    }
    try:
        while child.poll() is None:
            watcher.dispatch()
            if lid_reader() is True:
                watcher.request_disconnect("laptop lid closed")
            reason = watcher.reason
            if reason is not None:
                print(f"TuxDisplay disconnecting automatically: {reason}", file=sys.stderr, flush=True)
                result = stop_child(child, forwarded_signal)
                return result if reason == "service stop requested" else 0
            time.sleep(poll_interval)
        return int(child.returncode or 0)
    finally:
        if child.poll() is None:
            stop_child(child, signal.SIGINT)
        watcher.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main(arguments: Sequence[str] | None = None) -> int:
    command = list(sys.argv[1:] if arguments is None else arguments)
    if not command:
        print("usage: sleep_monitor.py COMMAND [ARGUMENT ...]", file=sys.stderr)
        return 2
    return run(command)


if __name__ == "__main__":
    raise SystemExit(main())
