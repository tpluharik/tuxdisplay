#!/usr/bin/python3
"""Tests for GNOME virtual-monitor layout persistence."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "display_layout.py"
SPEC = importlib.util.spec_from_file_location("display_layout", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def monitor(spec: tuple[str, str, str, str], mode_id: str, width: int, height: int):
    return (
        spec,
        [
            (
                mode_id,
                width,
                height,
                60.0,
                1.0,
                [1.0],
                {"is-current": True, "is-preferred": True},
            )
        ],
        {},
    )


def logical(x: int, y: int, scale: float, primary: bool, spec: tuple[str, str, str, str]):
    return (x, y, scale, 0, primary, [spec], {})


class DisplayLayoutTests(unittest.TestCase):
    laptop = ("eDP-1", "BOE", "Internal Panel", "internal")
    external = ("HDMI-1", "DEL", "U2720Q", "ABC123")
    old_virtual = ("Meta-0", "MetaVendor", "Virtual remote monitor", "0x000005")
    new_virtual = ("Meta-0", "MetaVendor", "Virtual remote monitor", "0x000006")

    def monitors(self, virtual_spec=None):
        virtual_spec = virtual_spec or self.old_virtual
        return [
            monitor(self.laptop, "2880x1800@60", 2880, 1800),
            monitor(self.external, "3840x2160@60", 3840, 2160),
            monitor(virtual_spec, "2048x1536@30", 2048, 1536),
        ]

    def test_captures_nearest_anchor_and_right_side(self) -> None:
        layout = [
            logical(0, 1440, 1.5, True, self.laptop),
            logical(0, 0, 1.5, False, self.external),
            logical(2560, 0, 1.0, False, self.old_virtual),
        ]

        placement = MODULE.capture_placement(self.monitors(), layout)

        self.assertEqual(
            placement,
            {
                "version": 1,
                "anchor": list(self.external),
                "side": "right",
                "offset": 0,
            },
        )

    def test_restores_position_after_mutter_changes_virtual_serial(self) -> None:
        saved = {
            "version": 1,
            "anchor": list(self.external),
            "side": "right",
            "offset": 120,
        }
        default_layout = [
            logical(0, 1440, 1.5, True, self.laptop),
            logical(0, 0, 1.5, False, self.external),
            logical(1920, 2640, 1.0, False, self.new_virtual),
        ]

        restored = MODULE.restore_placement(self.monitors(self.new_virtual), default_layout, saved)

        self.assertIsNotNone(restored)
        self.assertEqual(restored[2][:2], (2560, 120))
        self.assertEqual(restored[0][:2], default_layout[0][:2])
        self.assertEqual(restored[1][:2], default_layout[1][:2])

    def test_left_side_normalizes_all_monitors_without_changing_relative_layout(self) -> None:
        saved = {
            "version": 1,
            "anchor": list(self.external),
            "side": "left",
            "offset": 100,
        }
        default_layout = [
            logical(0, 1440, 1.5, True, self.laptop),
            logical(0, 0, 1.5, False, self.external),
            logical(2560, 0, 1.0, False, self.new_virtual),
        ]

        restored = MODULE.restore_placement(self.monitors(self.new_virtual), default_layout, saved)

        self.assertIsNotNone(restored)
        self.assertEqual(restored[2][:2], (0, 100))
        self.assertEqual(restored[1][:2], (2048, 0))
        self.assertEqual(restored[0][:2], (2048, 1440))

    def test_missing_anchor_does_not_rewrite_current_layout(self) -> None:
        saved = {
            "version": 1,
            "anchor": ["DP-99", "ACME", "Missing", "serial"],
            "side": "right",
            "offset": 0,
        }
        default_layout = [
            logical(0, 0, 1.5, True, self.laptop),
            logical(1920, 0, 1.0, False, self.new_virtual),
        ]

        restored = MODULE.restore_placement(self.monitors(self.new_virtual), default_layout, saved)

        self.assertIsNone(restored)

    def test_stable_monitor_serial_wins_if_connector_changes_at_a_dock(self) -> None:
        moved_external = ("DP-2", "DEL", "U2720Q", "ABC123")
        replacement_on_old_connector = ("HDMI-1", "ACME", "Projector", "NEW")
        monitors = [
            monitor(moved_external, "3840x2160@60", 3840, 2160),
            monitor(replacement_on_old_connector, "1920x1080@60", 1920, 1080),
            monitor(self.new_virtual, "2048x1536@30", 2048, 1536),
        ]
        layout = [
            logical(0, 0, 1.0, True, moved_external),
            logical(3840, 0, 1.0, False, replacement_on_old_connector),
            logical(5760, 0, 1.0, False, self.new_virtual),
        ]
        saved = {
            "version": 1,
            "anchor": list(self.external),
            "side": "below",
            "offset": 50,
        }

        restored = MODULE.restore_placement(monitors, layout, saved)

        self.assertIsNotNone(restored)
        self.assertEqual(restored[2][:2], (50, 2160))

    def test_mirrored_virtual_monitor_is_not_saved(self) -> None:
        mirrored = [(0, 0, 1.0, 0, True, [self.laptop, self.old_virtual], {})]
        self.assertIsNone(MODULE.capture_placement(self.monitors(), mirrored))


if __name__ == "__main__":
    unittest.main()
