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
        display.loop = mock.Mock()
        display.fatal_error = None
        display.safe_disconnect_reason = ""
        return display

    def make_pacing_display(self) -> object:
        display = MODULE.WaylandDisplay.__new__(MODULE.WaylandDisplay)
        display.stopping = False
        display.pacing_lock = threading.Lock()
        display.pacing_active = False
        display.pacing_started_monotonic = 0.0
        display.last_pacing_activity_monotonic = 0.0
        display.pacing_tail_ms = MODULE.SPARSE_PACING_TAIL_MS
        display.wake_started_monotonic = 0.0
        display.wake_stage = ""
        display.wake_reason = ""
        display.wake_requires_fresh_source = False
        display.wake_fresh_source_seen = False
        display.wake_keyframe_requests = 0
        display.wake_safe_disconnects = 0
        display.pipeline = object()
        display.pipeline_health = {}
        display.pipewire_frame_times = MODULE.deque()
        display.capture_frame_times = MODULE.deque()
        display.capture_frame_lock = threading.Lock()
        display.last_source_monotonic = 0.0
        display.last_pipewire_sequence = None
        display.last_capture_sequence = None
        display.pipewire_keepalive_buffers = 0
        display._send_force_keyframe = mock.Mock()
        display.request_safe_disconnect = mock.Mock()
        display.write_client_state = mock.Mock()
        return display

    @staticmethod
    def buffer_info(sequence: int, size: int = 1) -> object:
        buffer = mock.Mock()
        buffer.offset = sequence
        buffer.get_size.return_value = size
        info = mock.Mock()
        info.get_buffer.return_value = buffer
        return info

    def test_pipewire_keepalive_does_not_wake_encoder_or_inflate_source_rate(self) -> None:
        display = self.make_pacing_display()
        display.activate_adaptive_pacing = mock.Mock()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.on_source_buffer(None, self.buffer_info(42))
        with mock.patch.object(MODULE.time, "monotonic", return_value=10.1):
            display.on_source_buffer(None, self.buffer_info(42))

        self.assertEqual(len(display.pipewire_frame_times), 1)
        self.assertEqual(display.pipewire_keepalive_buffers, 1)
        display.activate_adaptive_pacing.assert_called_once_with(sustained=False)

    def test_new_pipewire_sequence_still_wakes_encoder(self) -> None:
        display = self.make_pacing_display()
        display.activate_adaptive_pacing = mock.Mock()

        display.on_source_buffer(None, self.buffer_info(42))
        display.on_source_buffer(None, self.buffer_info(43))

        self.assertEqual(len(display.pipewire_frame_times), 2)
        self.assertEqual(display.pipewire_keepalive_buffers, 0)
        self.assertEqual(display.activate_adaptive_pacing.call_args_list, [
            mock.call(sustained=False),
            mock.call(sustained=True),
        ])

    def test_intentionally_idle_pipeline_does_not_request_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.pacing_active = False
            display.last_source_monotonic = 150.0
            display.request_pipeline_safe_disconnect = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=200.0):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_safe_disconnect.assert_not_called()

    def test_pipeline_that_never_encodes_while_activity_continues_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.pacing_active = True
            display.last_video_monotonic = 0.0
            display.last_source_monotonic = 100.0
            display.pacing_started_monotonic = 100.0
            display.request_pipeline_safe_disconnect = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=112.1):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_safe_disconnect.assert_called_once_with(mock.ANY)

    def test_new_activity_after_long_idle_gets_a_fresh_watchdog_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.last_video_monotonic = 100.0
            display.pacing_started_monotonic = 200.0
            display.request_pipeline_safe_disconnect = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=202.0):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_safe_disconnect.assert_not_called()

    def test_adaptive_pacing_closes_after_the_activity_tail(self) -> None:
        display = self.make_pacing_display()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.activate_adaptive_pacing(sustained=True)

        # A frame proves that opening the gate succeeded. Only then may the
        # ordinary quiet tail close it again.
        display.complete_adaptive_wake()

        with mock.patch.object(MODULE.time, "monotonic", return_value=11.24):
            display.refresh_adaptive_pacing()
        self.assertTrue(display.pacing_active)

        with mock.patch.object(MODULE.time, "monotonic", return_value=11.25):
            result = display.refresh_adaptive_pacing()
        self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
        self.assertFalse(display.pacing_active)
        self.assertEqual(display.pacing_tail_ms, MODULE.SPARSE_PACING_TAIL_MS)

    def test_isolated_frame_uses_short_tail_until_motion_is_sustained(self) -> None:
        display = self.make_pacing_display()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.activate_adaptive_pacing()
        display.complete_adaptive_wake()
        self.assertEqual(display.pacing_tail_ms, MODULE.SPARSE_PACING_TAIL_MS)

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.25):
            display.refresh_adaptive_pacing()
        self.assertFalse(display.pacing_active)

        with mock.patch.object(MODULE.time, "monotonic", return_value=11.0):
            display.activate_adaptive_pacing(sustained=True)
        display.complete_adaptive_wake()
        self.assertEqual(display.pacing_tail_ms, MODULE.ACTIVE_PACING_TAIL_MS)

    def test_failed_idle_wake_requests_keyframe_without_closing_gate(self) -> None:
        display = self.make_pacing_display()
        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.activate_adaptive_pacing()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.5):
            result = display.refresh_adaptive_pacing()

        self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
        self.assertTrue(display.pacing_active)
        self.assertEqual(display.wake_stage, "keyframe")
        self.assertEqual(display.wake_keyframe_requests, 1)
        display._send_force_keyframe.assert_called_once_with()

    def test_receiver_keyframe_request_does_not_arm_capture_recovery(self) -> None:
        display = self.make_pacing_display()

        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.force_keyframe()

        self.assertTrue(display.pacing_active)
        self.assertEqual(display.wake_stage, "")
        display._send_force_keyframe.assert_called_once_with()

        with mock.patch.object(MODULE.time, "monotonic", return_value=11.25):
            display.refresh_adaptive_pacing()
        self.assertFalse(display.pacing_active)
        display.request_safe_disconnect.assert_not_called()

    def test_failed_keyframe_wake_disconnects_without_rebuilding_capture(self) -> None:
        display = self.make_pacing_display()
        with mock.patch.object(MODULE.time, "monotonic", return_value=10.0):
            display.activate_adaptive_pacing()
        with mock.patch.object(MODULE.time, "monotonic", return_value=10.5):
            display.refresh_adaptive_pacing()

        with mock.patch.object(MODULE.time, "monotonic", return_value=14.0):
            display.refresh_adaptive_pacing()

        display.request_safe_disconnect.assert_called_once_with(
            "video did not resume after adaptive idle",
            {"stale": True, "wake_age_seconds": 4.0, "wake_reason": "adaptive idle"},
        )
        self.assertEqual(display.wake_safe_disconnects, 1)
        self.assertEqual(display.wake_stage, "disconnecting")

    def test_pending_wake_never_rebuilds_the_capture_pipeline(self) -> None:
        display = self.make_pacing_display()
        display.pacing_active = True
        display.last_pacing_activity_monotonic = 10.0
        display.wake_started_monotonic = 10.0
        display.wake_stage = "keyframe"

        with mock.patch.object(MODULE.time, "monotonic", return_value=11.5):
            display.refresh_adaptive_pacing()

        display.request_safe_disconnect.assert_not_called()
        self.assertEqual(display.wake_stage, "keyframe")
        self.assertTrue(display.pacing_active)

    def test_encoded_frame_completes_pending_wake(self) -> None:
        display = self.make_pacing_display()
        display.wake_stage = "keyframe"
        display.wake_reason = "monitor layout change"
        display.pipeline_health = {"wake_recovery": "capture refreshed", "fallback": "software"}

        display.complete_adaptive_wake()

        self.assertEqual(display.wake_stage, "")
        self.assertEqual(display.wake_reason, "")
        self.assertEqual(display.pipeline_health, {"fallback": "software"})

    def test_layout_change_verifies_capture_even_if_pacing_is_active(self) -> None:
        display = self.make_pacing_display()
        display.remote_session_alive = True
        display.pacing_active = True
        display.opendisp = mock.Mock()
        display.refresh_cursor_tracking_geometry = mock.Mock()

        with mock.patch.object(MODULE.time, "monotonic", return_value=20.0):
            display.refresh_capture_after_layout_change()

        self.assertTrue(display.pacing_active)
        self.assertEqual(display.wake_stage, "waiting")
        self.assertEqual(display.wake_reason, "monitor layout change")
        self.assertTrue(display.wake_requires_fresh_source)
        self.assertFalse(display.wake_fresh_source_seen)
        display.opendisp.recover_video.assert_called_once_with()

    def test_cached_encoded_frame_cannot_satisfy_layout_verification(self) -> None:
        display = self.make_pacing_display()
        display.wake_stage = "waiting"
        display.wake_reason = "monitor layout change"
        display.wake_requires_fresh_source = True
        display.wake_fresh_source_seen = False

        display.complete_adaptive_wake()

        self.assertEqual(display.wake_stage, "waiting")
        self.assertEqual(display.wake_reason, "monitor layout change")

    def test_fresh_pipewire_sequence_allows_layout_verification_to_complete(self) -> None:
        display = self.make_pacing_display()
        display.pacing_active = True
        display.wake_stage = "waiting"
        display.wake_reason = "monitor layout change"
        display.wake_requires_fresh_source = True
        display.wake_fresh_source_seen = False

        with mock.patch.object(MODULE.time, "monotonic", return_value=20.1):
            display.on_source_buffer(None, self.buffer_info(99))
        display.complete_adaptive_wake()

        self.assertEqual(display.wake_stage, "")
        self.assertEqual(display.wake_reason, "")
        self.assertFalse(display.wake_requires_fresh_source)

    def test_missing_pipewire_sequence_cannot_satisfy_layout_verification(self) -> None:
        display = self.make_pacing_display()
        display.pacing_active = True
        display.wake_stage = "waiting"
        display.wake_reason = "monitor layout change"
        display.wake_requires_fresh_source = True
        display.wake_fresh_source_seen = False

        display.on_source_buffer(None, self.buffer_info((1 << 64) - 1))
        display.complete_adaptive_wake()

        self.assertEqual(display.wake_stage, "waiting")
        self.assertFalse(display.wake_fresh_source_seen)

    def test_failed_layout_change_wake_disconnects_without_restart(self) -> None:
        display = self.make_pacing_display()
        display.remote_session_alive = True
        display.opendisp = mock.Mock()
        display.refresh_cursor_tracking_geometry = mock.Mock()

        with mock.patch.object(MODULE.time, "monotonic", return_value=20.0):
            display.refresh_capture_after_layout_change()
        with mock.patch.object(MODULE.time, "monotonic", return_value=20.5):
            display.refresh_adaptive_pacing()
        with mock.patch.object(MODULE.time, "monotonic", return_value=24.0):
            display.refresh_adaptive_pacing()

        display.request_safe_disconnect.assert_called_once_with(
            "video did not resume after monitor layout change",
            {"stale": True, "wake_age_seconds": 4.0, "wake_reason": "monitor layout change"},
        )

    def test_start_waits_until_previous_virtual_monitor_is_removed(self) -> None:
        display = self.make_pacing_display()
        display.display_mode = "extend"
        virtual = [(('Meta-0', 'MetaVendor', 'Virtual remote monitor', '0x1'), [], {})]
        display.get_display_state = mock.Mock(side_effect=[(1, virtual, [], {}), (2, [], [], {})])

        with mock.patch.object(MODULE.time, "monotonic", side_effect=[10.0, 10.1]), mock.patch.object(
            MODULE.time, "sleep"
        ) as sleep:
            display.wait_for_previous_virtual_monitor()

        self.assertEqual(display.get_display_state.call_count, 2)
        sleep.assert_called_once_with(MODULE.VIRTUAL_MONITOR_POLL_SECONDS)

    def test_start_refuses_to_overlap_a_stale_virtual_monitor(self) -> None:
        display = self.make_pacing_display()
        display.display_mode = "extend"
        virtual = [(('Meta-0', 'MetaVendor', 'Virtual remote monitor', '0x1'), [], {})]
        display.get_display_state = mock.Mock(return_value=(1, virtual, [], {}))

        with mock.patch.object(MODULE.time, "monotonic", side_effect=[10.0, 15.1]):
            with self.assertRaisesRegex(RuntimeError, "previous virtual monitor"):
                display.wait_for_previous_virtual_monitor()

    def test_stalled_encoded_frame_callback_requests_safe_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            display = self.make_display(Path(temporary))
            display.request_pipeline_safe_disconnect = mock.Mock()

            with mock.patch.object(MODULE.time, "monotonic", return_value=108.1):
                result = display.check_video_pipeline_liveness()

            self.assertEqual(result, MODULE.GLib.SOURCE_CONTINUE)
            display.request_pipeline_safe_disconnect.assert_called_once_with(mock.ANY)
            self.assertAlmostEqual(display.request_pipeline_safe_disconnect.call_args.args[0], 8.1)

    def test_hardware_stall_persists_software_fallback_and_disconnects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            display = self.make_display(directory)
            with mock.patch.object(MODULE.time, "time", return_value=1000.0):
                display.request_pipeline_safe_disconnect(8.5)

            recovery = json.loads(display.pipeline_recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(recovery["force_software_until"], 1000.0 + MODULE.HARDWARE_FALLBACK_SECONDS)
            self.assertTrue(display.receiver_stats["stale"])
            self.assertEqual(display.pipeline_health["recovery"], "safe disconnect")
            self.assertIn("encoded video stopped", display.safe_disconnect_reason)
            display.loop.quit.assert_called_once_with()

    def test_remote_session_closed_disconnects_once(self) -> None:
        display = self.make_pacing_display()
        display.remote_session_alive = True
        display.request_safe_disconnect = mock.Mock()

        display.handle_remote_session_closed(None, "", "", "", "", None)

        self.assertFalse(display.remote_session_alive)
        display.request_safe_disconnect.assert_called_once_with(
            "GNOME closed the virtual display session",
            {"session": "closed", "stale": True},
        )

    def test_expected_remote_session_close_during_stop_is_ignored(self) -> None:
        display = self.make_pacing_display()
        display.remote_session_alive = True
        display.stopping = True
        display.request_safe_disconnect = mock.Mock()

        display.handle_remote_session_closed(None, "", "", "", "", None)

        self.assertFalse(display.remote_session_alive)
        display.request_safe_disconnect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
