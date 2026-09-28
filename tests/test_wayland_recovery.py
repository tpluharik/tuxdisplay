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
        display.pipeline_health = {}
        display.receiver_stats = {"fps": 15, "stale": False}
        display.client_lock = threading.Lock()
        display.video_encoder = "hardware"
        display.encoder_preference = "auto"
        display.state_directory = directory
        display.pipeline_recovery_path = directory / "pipeline-recovery.json"
        display.write_client_state = mock.Mock()
        return display

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
            with mock.patch.object(MODULE.time, "time", return_value=1000.0), mock.patch.object(
                MODULE.subprocess, "Popen"
            ) as popen:
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
            with mock.patch.object(MODULE.time, "time", return_value=1000.0), mock.patch.object(
                MODULE.subprocess, "Popen"
            ) as popen:
                display.request_pipeline_service_recovery(9.0)

            popen.assert_not_called()
            self.assertEqual(display.pipeline_health["recovery"], "suppressed")
            display.write_client_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
