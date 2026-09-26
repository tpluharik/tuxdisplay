#!/usr/bin/python3
"""Tests for mirrored-monitor selection and touch-coordinate mapping."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "display_source.py"
SPEC = importlib.util.spec_from_file_location("display_source", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def logical(primary: bool, *connectors: str):
    specs = [(connector, "vendor", "product", connector + "-serial") for connector in connectors]
    return (0, 0, 1.0, 0, primary, specs, {})


class DisplaySourceTests(unittest.TestCase):
    def test_primary_physical_monitor_is_selected(self) -> None:
        monitors = [
            logical(False, "HDMI-1"),
            logical(True, "eDP-1"),
        ]
        self.assertEqual(MODULE.primary_monitor_connector(monitors), "eDP-1")

    def test_virtual_connector_is_never_selected_for_mirroring(self) -> None:
        monitors = [
            logical(True, "Meta-0"),
            logical(False, "DP-2"),
        ]
        self.assertEqual(MODULE.primary_monitor_connector(monitors), "DP-2")

    def test_first_active_physical_monitor_is_the_non_primary_fallback(self) -> None:
        self.assertEqual(MODULE.primary_monitor_connector([logical(False, "DP-4")]), "DP-4")
        self.assertIsNone(MODULE.primary_monitor_connector([logical(True, "Meta-0")]))

    def test_letterbox_mapping_tracks_the_visible_monitor_area(self) -> None:
        # A 16:10 laptop screen inside a 4:3 tablet stream has vertical bars.
        self.assertEqual(
            MODULE.map_letterboxed_point(1024, 768, (2048, 1536), (1920, 1200)),
            (960.0, 600.0),
        )
        self.assertEqual(
            MODULE.map_letterboxed_point(0, 768, (2048, 1536), (1920, 1200)),
            (0.0, 600.0),
        )
        self.assertEqual(
            MODULE.map_letterboxed_point(2048, 768, (2048, 1536), (1920, 1200)),
            (1920.0, 600.0),
        )

    def test_stream_size_rejects_invalid_parameters(self) -> None:
        self.assertEqual(MODULE.stream_size({"size": (2560, 1440)}, (1920, 1080)), (2560, 1440))
        self.assertEqual(MODULE.stream_size({"size": (0, 1440)}, (1920, 1080)), (1920, 1080))
        self.assertEqual(MODULE.stream_size({}, (1920, 1080)), (1920, 1080))


if __name__ == "__main__":
    unittest.main()
