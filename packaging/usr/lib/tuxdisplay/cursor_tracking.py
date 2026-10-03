#!/usr/bin/python3
"""Low-overhead XWayland cursor tracking for a GNOME screen-cast output."""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
import re
import subprocess


@dataclass(frozen=True)
class MonitorGeometry:
    width: int
    height: int
    x: int
    y: int

    def normalized_pointer(self, pointer_x: int, pointer_y: int) -> tuple[float, float] | None:
        if not (self.x <= pointer_x < self.x + self.width and self.y <= pointer_y < self.y + self.height):
            return None
        return (
            (pointer_x - self.x) / max(1, self.width),
            (pointer_y - self.y) / max(1, self.height),
        )


MONITOR_LINE = re.compile(
    r"^\s*\d+:\s+\S+\s+(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)\s+(\S+)\s*$"
)


def parse_xrandr_monitors(output: str) -> dict[str, MonitorGeometry]:
    monitors: dict[str, MonitorGeometry] = {}
    for line in output.splitlines():
        match = MONITOR_LINE.match(line)
        if match is None:
            continue
        width, height, x, y, connector = match.groups()
        geometry = MonitorGeometry(int(width), int(height), int(x), int(y))
        if geometry.width > 0 and geometry.height > 0:
            monitors[connector] = geometry
    return monitors


def monitor_geometry(connector: str) -> MonitorGeometry | None:
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return parse_xrandr_monitors(result.stdout).get(connector)


class X11PointerTracker:
    """Read the compositor pointer through XWayland without injecting input."""

    def __init__(self) -> None:
        library_name = ctypes.util.find_library("X11")
        if not library_name:
            raise RuntimeError("libX11 is unavailable")
        self.library = ctypes.CDLL(library_name)
        self.library.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.library.XOpenDisplay.restype = ctypes.c_void_p
        self.library.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.library.XDefaultRootWindow.restype = ctypes.c_ulong
        self.library.XQueryPointer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.library.XQueryPointer.restype = ctypes.c_int
        self.library.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = self.library.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("XWayland display is unavailable")
        self.root = self.library.XDefaultRootWindow(self.display)

    def position(self) -> tuple[int, int] | None:
        root = ctypes.c_ulong()
        child = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        window_x = ctypes.c_int()
        window_y = ctypes.c_int()
        mask = ctypes.c_uint()
        result = self.library.XQueryPointer(
            self.display,
            self.root,
            ctypes.byref(root),
            ctypes.byref(child),
            ctypes.byref(root_x),
            ctypes.byref(root_y),
            ctypes.byref(window_x),
            ctypes.byref(window_y),
            ctypes.byref(mask),
        )
        if not result:
            return None
        return root_x.value, root_y.value

    def close(self) -> None:
        if self.display:
            self.library.XCloseDisplay(self.display)
            self.display = None
