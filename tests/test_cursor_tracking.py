#!/usr/bin/python3
"""Tests for XWayland monitor geometry and cursor normalization."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "cursor_tracking.py"
SPEC = importlib.util.spec_from_file_location("cursor_tracking", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CursorTrackingTests(unittest.TestCase):
    def test_xrandr_monitors_are_parsed_with_scaled_geometry(self) -> None:
        output = """Monitors: 2
 0: +*eDP-1 3456/300x2160/190+5504+2880  eDP-1
 1: +Meta-0 4096/1084x3072/813+8960+0  Meta-0
"""
        monitors = MODULE.parse_xrandr_monitors(output)

        self.assertEqual(monitors["Meta-0"], MODULE.MonitorGeometry(4096, 3072, 8960, 0))
        self.assertEqual(monitors["eDP-1"], MODULE.MonitorGeometry(3456, 2160, 5504, 2880))

    def test_pointer_is_normalized_only_inside_the_selected_monitor(self) -> None:
        geometry = MODULE.MonitorGeometry(4000, 3000, 9000, 100)

        self.assertEqual(geometry.normalized_pointer(9000, 100), (0.0, 0.0))
        self.assertEqual(geometry.normalized_pointer(11000, 1600), (0.5, 0.5))
        self.assertIsNone(geometry.normalized_pointer(8999, 100))
        self.assertIsNone(geometry.normalized_pointer(13000, 100))


if __name__ == "__main__":
    unittest.main()
