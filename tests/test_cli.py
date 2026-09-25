#!/usr/bin/python3
"""Dependency-free smoke tests for TuxDisplay's configuration and URL logic."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "packaging" / "usr" / "bin" / "tuxdisplay"
LOADER = importlib.machinery.SourceFileLoader("tuxdisplay_cli", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


class TuxDisplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(Path(self.temporary.name) / "config"),
                "XDG_STATE_HOME": str(Path(self.temporary.name) / "state"),
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_default_config_is_created_privately(self) -> None:
        config = MODULE.ensure_config()
        self.assertEqual(config["RESOLUTION"], "1920x1080")
        self.assertEqual(config["FPS"], "30")
        path = MODULE.config_file()
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_config_values_fall_back(self) -> None:
        values = {
            "RESOLUTION": "bad;command",
            "FPS": "144",
            "DISPLAY_NUMBER": "9999",
            "WEB_PORT": "80",
            "VNC_PORT": "5900",
        }
        validated = MODULE.validate_config(values)
        self.assertEqual(validated["RESOLUTION"], "1920x1080")
        self.assertEqual(validated["FPS"], "30")
        self.assertEqual(validated["DISPLAY_NUMBER"], "48")
        self.assertEqual(validated["WEB_PORT"], "6080")
        self.assertEqual(validated["VNC_PORT"], "5900")

    def test_usb_gadget_url_is_preferred(self) -> None:
        with mock.patch.object(MODULE, "network_addresses", return_value=[("usb0", "10.55.0.1"), ("wlan0", "192.0.2.5")]):
            url = MODULE.preferred_url()
        self.assertEqual(url, "http://10.55.0.1:6080/")

    def test_ipad_login_has_touch_keypad_and_does_not_capture_pin_keys(self) -> None:
        viewer = SCRIPT.parents[1] / 'share' / 'tuxdisplay' / 'wayland-viewer.html'
        html = viewer.read_text(encoding='utf-8')
        self.assertIn('id=' + chr(34) + 'keypad' + chr(34), html)
        self.assertIn('keypad.addEventListener', html)
        self.assertIn('viewerActive() && event.target !== keyboard', html)
        self.assertIn('webkitRequestFullscreen', html)
        self.assertIn("classList.toggle('immersive'", html)

    def test_wayland_input_uses_screencast_object_path(self) -> None:
        daemon = SCRIPT.parents[1] / 'lib' / 'tuxdisplay' / 'tuxdisplay-wayland'
        text = daemon.read_text(encoding='utf-8')
        self.assertIn('(self.stream_path, x, y)', text)
        self.assertNotIn('NotifyPointerMotionAbsolute"' + ', "(sdd)", (self.mapping_id', text)

    def test_wayland_virtual_monitor_pins_the_requested_mode(self) -> None:
        daemon = SCRIPT.parents[1] / 'lib' / 'tuxdisplay' / 'tuxdisplay-wayland'
        text = daemon.read_text(encoding='utf-8')
        self.assertIn('"modes": GLib.Variant("aa{sv}", [mode])', text)
        self.assertIn('"size": GLib.Variant("(uu)", (self.width, self.height))', text)
        self.assertIn('"refresh-rate": GLib.Variant("d", float(self.frames_per_second))', text)

    def test_wayland_pipeline_does_not_hold_a_damage_driven_first_frame(self) -> None:
        daemon = SCRIPT.parents[1] / 'lib' / 'tuxdisplay' / 'tuxdisplay-wayland'
        text = daemon.read_text(encoding='utf-8')
        self.assertIn('pipewiresrc path={self.node_id}', text)
        self.assertNotIn('videorate', text)
        self.assertIn('framerate={self.frames_per_second}/1', text)
        self.assertIn('valve name=jpeg_valve drop=false', text)
        self.assertIn('key-int-max={self.frames_per_second}', text)

    def test_browser_recovers_or_reauthenticates_after_service_restart(self) -> None:
        viewer = SCRIPT.parents[1] / "share" / "tuxdisplay" / "wayland-viewer.html"
        html = viewer.read_text(encoding="utf-8")
        self.assertIn("function scheduleReconnect()", html)
        self.assertIn("response.status === 401", html)
        self.assertIn("The display restarted. Enter the PIN", html)
        self.assertIn("type:'release_all'", html)

    def test_dead_client_state_is_not_reported_connected(self) -> None:
        with mock.patch.object(MODULE, "is_active", return_value=True), mock.patch.object(
            MODULE.os, "kill", side_effect=ProcessLookupError
        ):
            path = MODULE.client_state_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"pid":999999,"active_streams":1,"opendisplay_usb":true}\n', encoding="utf-8")
            self.assertEqual(MODULE.connection_state(), "running")
            self.assertFalse(MODULE.opendisplay_connected())

    def test_shutdown_stops_pipeline_before_mutter_session(self) -> None:
        daemon = SCRIPT.parents[1] / "lib" / "tuxdisplay" / "tuxdisplay-wayland"
        text = daemon.read_text(encoding="utf-8")
        stop = text[text.index("    def stop(self) -> None:") :]
        self.assertLess(stop.index("self.pipeline.set_state(Gst.State.NULL)"), stop.index('REMOTE_SESSION_IFACE, "Stop"'))
        self.assertIn("timeout_ms=2_000", stop)

    def test_ipheth_usb_address_is_preferred(self) -> None:
        addresses = [("wlan0", "192.0.2.5"), ("enxipad", "172.20.10.2")]
        with mock.patch.object(MODULE, "network_addresses", return_value=addresses), mock.patch.object(
            MODULE, "interface_driver", side_effect=lambda name: "ipheth" if name == "enxipad" else ""
        ):
            url = MODULE.preferred_url()
        self.assertEqual(url, "http://172.20.10.2:6080/")

    def test_connection_state_distinguishes_waiting_and_connected(self) -> None:
        with mock.patch.object(MODULE, "is_active", return_value=False):
            self.assertEqual(MODULE.connection_state(), "disconnected")
        with mock.patch.object(MODULE, "is_active", return_value=True):
            self.assertEqual(MODULE.connection_state(), "running")
            path = MODULE.client_state_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"active_streams": 1}\n', encoding="utf-8")
            self.assertEqual(MODULE.connection_state(), "connected")

    def test_usb_status_reports_a_trusted_cable_without_tethering(self) -> None:
        with mock.patch.object(MODULE, "usb_network_addresses", return_value=[]), mock.patch.object(
            MODULE, "usb_device_ids", return_value=["test-ipad"]
        ), mock.patch.object(
            MODULE, "opendisplay_connected", return_value=False
        ):
            status, message, url = MODULE.usb_status()
        self.assertEqual(status, "cable")
        self.assertIn("open OpenDisplay", message)
        self.assertNotIn("Personal Hotspot", message)
        self.assertIsNone(url)

    def test_usb_status_reports_direct_opendisplay_connection(self) -> None:
        with mock.patch.object(MODULE, "usb_device_ids", return_value=["test-ipad"]), mock.patch.object(
            MODULE, "opendisplay_connected", return_value=True
        ):
            status, message, url = MODULE.usb_status()
        self.assertEqual(status, "ready")
        self.assertIn("OpenDisplay connected", message)
        self.assertIsNone(url)

    def test_tray_autostart_and_state_icons_are_packaged(self) -> None:
        package_root = SCRIPT.parents[2]
        autostart = package_root / "etc" / "xdg" / "autostart" / "tuxdisplay-tray.desktop"
        self.assertIn("Exec=tuxdisplay tray", autostart.read_text(encoding="utf-8"))
        icon_root = package_root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        for state in ("disconnected", "running", "connected"):
            self.assertTrue((icon_root / f"tuxdisplay-{state}.svg").exists())
        self.assertIn("AyatanaAppIndicator3", SCRIPT.read_text(encoding="utf-8"))

    def test_launch_rejects_empty_command(self) -> None:
        self.assertEqual(MODULE.launch([]), 2)


if __name__ == "__main__":
    unittest.main()
