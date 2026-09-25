#!/usr/bin/python3
"""Dependency-free smoke tests for TuxDisplay's configuration and URL logic."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import hashlib
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
        self.assertEqual(config["KEEP_AWAKE_WITH_LID_CLOSED"], "0")
        path = MODULE.config_file()
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_config_values_fall_back(self) -> None:
        values = {
            "RESOLUTION": "bad;command",
            "FPS": "144",
            "KEEP_AWAKE_WITH_LID_CLOSED": "yes",
            "DISPLAY_NUMBER": "9999",
            "WEB_PORT": "80",
            "VNC_PORT": "5900",
        }
        validated = MODULE.validate_config(values)
        self.assertEqual(validated["RESOLUTION"], "1920x1080")
        self.assertEqual(validated["FPS"], "30")
        self.assertEqual(validated["KEEP_AWAKE_WITH_LID_CLOSED"], "0")
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
        self.assertNotIn('framerate={self.frames_per_second}/1', text)
        self.assertIn('queue name=capture_queue', text)
        self.assertIn('capture_pad.add_probe(Gst.PadProbeType.BUFFER, self.limit_frame_rate)', text)
        self.assertIn('return Gst.PadProbeReturn.DROP', text)
        self.assertIn('valve name=jpeg_valve drop=false', text)
        self.assertIn('key-int-max={self.frames_per_second}', text)

    def test_wayland_pipeline_starts_before_usb_transport(self) -> None:
        daemon = SCRIPT.parents[1] / 'lib' / 'tuxdisplay' / 'tuxdisplay-wayland'
        text = daemon.read_text(encoding='utf-8')
        run = text[text.index('    def run(self) -> None:') :]
        self.assertLess(run.index('self.prepare_opendisplay()'), run.index('self.start_pipeline()'))
        self.assertLess(run.index('self.start_pipeline()'), run.index('self.start_opendisplay()'))

    def test_lid_close_sleep_inhibitor_is_opt_in_and_scoped_to_service(self) -> None:
        session = SCRIPT.parents[1] / "lib" / "tuxdisplay" / "tuxdisplay-session"
        text = session.read_text(encoding="utf-8")
        self.assertIn("KEEP_AWAKE_WITH_LID_CLOSED 0", text)
        self.assertIn("${TUXDISPLAY_INHIBITED:-0}", text)
        self.assertIn("--what=handle-lid-switch:sleep", text)
        self.assertIn("--mode=block", text)
        self.assertIn('exec systemd-inhibit', text)
        manager = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('Gtk.Label(label="Keep awake with lid closed")', manager)
        self.assertIn('configuration["KEEP_AWAKE_WITH_LID_CLOSED"] = selected', manager)

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

    def test_single_graphical_application_and_state_icons_are_packaged(self) -> None:
        package_root = SCRIPT.parents[2]
        autostart = package_root / "etc" / "xdg" / "autostart" / "tuxdisplay-tray.desktop"
        self.assertIn("Exec=tuxdisplay gui --background", autostart.read_text(encoding="utf-8"))
        desktop = package_root / "usr" / "share" / "applications" / "io.github.tuxdisplay.Manager.desktop"
        desktop_text = desktop.read_text(encoding="utf-8")
        self.assertIn("Exec=tuxdisplay gui", desktop_text)
        self.assertIn("Icon=tuxdisplay", desktop_text)
        icon_root = package_root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        for state in ("disconnected", "running", "connected"):
            self.assertTrue((icon_root / f"tuxdisplay-{state}.svg").exists())
        manager = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('gi.require_version("Gtk", "3.0")', manager)
        self.assertNotIn('gi.require_version("Gtk", "4.0")', manager)
        self.assertIn("AyatanaAppIndicator3", manager)
        arguments = MODULE.build_parser().parse_args(["gui", "--background"])
        self.assertTrue(arguments.background)

    def test_release_update_requires_exact_assets_and_safe_urls(self) -> None:
        payload = {
            "tag_name": "v9.9.9",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/tpluharik/tuxdisplay/releases/tag/v9.9.9",
            "assets": [
                {
                    "name": "tuxdisplay_9.9.9_all.deb",
                    "browser_download_url": (
                        "https://github.com/tpluharik/tuxdisplay/releases/download/v9.9.9/"
                        "tuxdisplay_9.9.9_all.deb"
                    ),
                    "digest": "sha256:" + "0" * 64,
                },
                {
                    "name": "SHA256SUMS",
                    "browser_download_url": (
                        "https://github.com/tpluharik/tuxdisplay/releases/download/v9.9.9/SHA256SUMS"
                    ),
                },
            ],
        }
        update = MODULE.release_update_from_payload(payload)
        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update["version"], "9.9.9")
        payload["assets"][0]["browser_download_url"] = "https://example.invalid/tuxdisplay.deb"
        with self.assertRaises(RuntimeError):
            MODULE.release_update_from_payload(payload)

    def test_update_checksum_and_github_digest_are_verified(self) -> None:
        package_data = b"test Debian package bytes"
        digest = hashlib.sha256(package_data).hexdigest()
        update = {
            "package_name": "tuxdisplay_9.9.9_all.deb",
            "package_digest": f"sha256:{digest}",
        }
        checksums = f"{digest}  tuxdisplay_9.9.9_all.deb\n".encode()
        self.assertEqual(MODULE.verify_update_assets(update, package_data, checksums), digest)
        with self.assertRaises(RuntimeError):
            MODULE.verify_update_assets(update, package_data + b"tampered", checksums)

    def test_update_installer_validates_package_metadata_before_authentication(self) -> None:
        package_data = b"test Debian package bytes"
        digest = hashlib.sha256(package_data).hexdigest()
        update = {
            "version": "9.9.9",
            "package_name": "tuxdisplay_9.9.9_all.deb",
            "package_url": "https://github.com/example/package",
            "checksum_url": "https://github.com/example/checksums",
            "package_digest": f"sha256:{digest}",
        }
        checksums = f"{digest}  tuxdisplay_9.9.9_all.deb\n".encode()
        metadata = mock.Mock(returncode=0, stdout="tuxdisplay\n9.9.9\nall\n", stderr="")
        installed = mock.Mock(returncode=0)
        with mock.patch.object(MODULE, "download_url", side_effect=[package_data, checksums]), mock.patch.object(
            MODULE.subprocess, "run", side_effect=[metadata, installed]
        ) as run:
            success, _message = MODULE.install_update(update)
        self.assertTrue(success)
        install_command = run.call_args_list[1].args[0]
        self.assertEqual(install_command[:4], ["pkexec", "/usr/bin/apt-get", "install", "--yes"])
        self.assertTrue(install_command[4].endswith("tuxdisplay_9.9.9_all.deb"))

        unexpected = mock.Mock(returncode=0, stdout="not-tuxdisplay\n9.9.9\nall\n", stderr="")
        with mock.patch.object(MODULE, "download_url", side_effect=[package_data, checksums]), mock.patch.object(
            MODULE.subprocess, "run", return_value=unexpected
        ) as run:
            success, message = MODULE.install_update(update)
        self.assertFalse(success)
        self.assertIn("unexpected metadata", message)
        self.assertEqual(run.call_count, 1)

    def test_launch_rejects_empty_command(self) -> None:
        self.assertEqual(MODULE.launch([]), 2)


if __name__ == "__main__":
    unittest.main()
