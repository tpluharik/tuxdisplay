#!/usr/bin/python3
"""Focused tests for bounded Wayland video-pipeline recovery."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

from gi_stub import ensure_gi


ensure_gi()

MODULE_DIR = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay"
sys.path.insert(0, str(MODULE_DIR))
LOADER = importlib.machinery.SourceFileLoader("tuxdisplay_wayland", str(MODULE_DIR / "tuxdisplay-wayland"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


class WaylandPipelineRecoveryTests(unittest.TestCase):
    def make_display(self, directory: Path) -> object:
        display = MODULE.WaylandDisplay.__new__(MODULE.WaylandDisplay)
        display.pipeline_recovery_requested = False
        display.stopping = False
        display.pipeline = object()
        display.pipeline_started_monotonic = 90.0
        display.last_video_monotonic = 100.0
        display.last_source_monotonic = 100.0
        display.pacing_active = True
        display.pacing_started_monotonic = 90.0
        display.pipeline_health = {}
        display.receiver_stats = {"fps": 15, "stale": False}
        display.client_lock = threading.Lock()
        display.video_encoder = "hardware"
        display.encoder_preference = "auto"
        display.state_directory = directory
        display.pipeline_recovery_path = directory / "pipeline-recovery.json"
        display.write_client_state = mock.Mock()
        return display

    def test_intentionally_idle_pipeline_does_not_request_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.pacing_active = False
            display.last_source_monotonic = 150.0
            display.request_pipeline_service_recovery = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=200.0):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_service_recovery.assert_not_called()

    def test_pipeline_that_never_encodes_while_activity_continues_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.pacing_active = True
            display.last_video_monotonic = 0.0
            display.last_source_monotonic = 100.0
            display.pacing_started_monotonic = 100.0
            display.request_pipeline_service_recovery = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=112.1):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_service_recovery.assert_called_once_with(mock.ANY)

    def test_new_activity_after_long_idle_gets_a_fresh_watchdog_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.last_video_monotonic = 100.0
            display.pacing_started_monotonic = 200.0
            display.request_pipeline_service_recovery = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=202.0):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_service_recovery.assert_not_called()

    def test_adaptive_pacing_closes_after_the_activity_tail(self) -> None:
        display = MODULE.WaylandDisplay.__new__(MODULE.WaylandDisplay)
        display.stopping = False
        display.pacing_lock = threading.Lock()
        display.pacing_active = False
        display.pacing_started_monotonic = 0.0
        display.last_pacing_activity_monotonic = 0.0
        display.activity_valve = mock.Mock()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.activate_adaptive_pacing()
        display.activity_valve.set_property.assert_called_once_with("drop", False)

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.4):
            display.refresh_adaptive_pacing()
        self.assertTrue(display.pacing_active)

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.5):
            result = display.refresh_adaptive_pacing()
        self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
        self.assertFalse(display.pacing_active)
        display.activity_valve.set_property.assert_called_with("drop", True)

    def test_stalled_encoded_frame_callback_requests_service_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.request_pipeline_service_recovery = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=108.1):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_service_recovery.assert_called_once_with(mock.ANY)
            self.assertAlmostEqual(display.request_pipeline_service_recovery.call_args.args[0], 8.1)

    def test_hardware_stall_persists_software_fallback_and_restarts_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            display = self.make_display(directory)
            with mock.patch.dict(MODULE.os.environ, {"TUXDISPLAY_MANAGED_SERVICE": "1"}), mock.patch.object(
                MODULE.time, "time", return_value=1000.0
            ), mock.patch.object(MODULE.subprocess, "Popen") as popen:
                display.request_pipeline_service_recovery(8.5)

            recovery = json.loads(display.pipeline_recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(recovery["restarts"], [1000.0])
            self.assertEqual(recovery["force_software_until"], 1000.0 + MODULE.HARDWARE_FALLBACK_SECONDS)
            self.assertTrue(display.receiver_stats["stale"])
            self.assertEqual(display.pipeline_health["recovery"], "service restart")
            popen.assert_called_once()
            self.assertEqual(
                popen.call_args.args[0],
                ["/usr/bin/systemctl", "--user", "--no-block", "restart", "tuxdisplay.service"],
            )

    def test_recovery_budget_suppresses_a_restart_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            display = self.make_display(directory)
            directory.mkdir(parents=True, exist_ok=True)
            display.pipeline_recovery_path.write_text(
                json.dumps({"restarts": [950.0, 975.0]}) + "\n",
                encoding="utf-8",
            )
            with mock.patch.dict(MODULE.os.environ, {"TUXDISPLAY_MANAGED_SERVICE": "1"}), mock.patch.object(
                MODULE.time, "time", return_value=1000.0
            ), mock.patch.object(MODULE.subprocess, "Popen") as popen:
                display.request_pipeline_service_recovery(9.0)

            popen.assert_not_called()
            self.assertEqual(display.pipeline_health["recovery"], "suppressed")
            display.write_client_state.assert_called_once()

    def test_standalone_diagnostic_cannot_restart_the_managed_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            with mock.patch.dict(MODULE.os.environ, {}, clear=True), mock.patch.object(
                MODULE.subprocess, "Popen"
            ) as popen:
                display.request_pipeline_service_recovery(8.5)

            popen.assert_not_called()
            self.assertFalse(display.pipeline_recovery_path.exists())
            self.assertEqual(display.pipeline_health["recovery"], "manual restart required")


if __name__ == "__main__":
    unittest.main()
