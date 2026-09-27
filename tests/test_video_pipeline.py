#!/usr/bin/python3
"""Tests for the bounded, low-latency GStreamer graph."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "video_pipeline.py"
SPEC = importlib.util.spec_from_file_location("video_pipeline", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VideoPipelineTests(unittest.TestCase):
    def test_keepalive_interval_sustains_requested_rate(self) -> None:
        self.assertEqual(MODULE.keepalive_interval_ms(60), 16)
        self.assertEqual(MODULE.keepalive_interval_ms(30), 33)
        self.assertEqual(MODULE.keepalive_interval_ms(15), 66)

    def test_auto_prefers_vaapi_but_keeps_software_fallback(self) -> None:
        available = {"vah264enc", "vapostproc"}
        self.assertEqual(MODULE.encoder_candidates("auto", available), ["hardware", "software"])
        self.assertEqual(MODULE.encoder_candidates("auto", {"vah264enc"}), ["software"])
        self.assertEqual(MODULE.encoder_candidates("software", available), ["software"])

    def test_bitrate_tracks_pixel_rate_with_safe_bounds(self) -> None:
        self.assertEqual(MODULE.target_bitrate_kbps(1024, 768, 15), 4000)
        self.assertEqual(MODULE.target_bitrate_kbps(1920, 1080, 30), 4977)
        self.assertEqual(MODULE.target_bitrate_kbps(2048, 1536, 60), 15099)
        self.assertEqual(MODULE.target_bitrate_kbps(8192, 8192, 60), 20000)

    def test_hardware_graph_uses_paced_frames_and_gpu_postprocessing(self) -> None:
        graph = MODULE.pipeline_description(42, 2048, 1536, 60, "hardware")
        self.assertIn("path=42", graph)
        self.assertIn("keepalive-time=16", graph)
        self.assertIn("imagefreeze name=frame_pacer is-live=true allow-replace=true", graph)
        self.assertIn("framerate=60/1", graph)
        self.assertIn("vapostproc add-borders=true", graph)
        self.assertIn("vah264enc name=h264_encoder", graph)
        self.assertIn("bitrate=15099", graph)
        self.assertIn("profile=constrained-baseline", graph)
        self.assertNotIn("x264enc", graph)

    def test_software_graph_parallelizes_conversion_and_drops_only_raw_frames(self) -> None:
        graph = MODULE.pipeline_description(42, 1920, 1080, 30, "software")
        self.assertIn("videoconvert n-threads=4", graph)
        self.assertIn("videoscale n-threads=4", graph)
        self.assertIn("x264enc name=h264_encoder", graph)
        self.assertIn("threads=0", graph)
        self.assertIn("sliced-threads=true", graph)
        self.assertIn("bitrate=4977", graph)
        self.assertIn("appsink name=h264_sink emit-signals=true max-buffers=1 drop=false", graph)
        self.assertIn("queue max-size-buffers=1", graph)
        self.assertIn("valve name=jpeg_valve drop=false", graph)
        self.assertNotIn("videorate", graph)

    def test_unknown_encoder_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.pipeline_description(42, 1920, 1080, 30, "mystery")


if __name__ == "__main__":
    unittest.main()
